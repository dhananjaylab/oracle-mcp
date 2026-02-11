"""
Generate and store semantic embeddings for products using Google's Generative AI.
Updated for google-genai SDK and Oracle 21c XE.
"""

import os
import sys
from dotenv import load_dotenv
import oracledb
import numpy as np
from google import genai
from google.genai import types

load_dotenv()

# === GOOGLE AI CONFIGURATION ===
GOOGLE_API_KEY = "AIzaSyAynyiGr2cRDsV4SAr9F-IILZnAit-4xSY"
print(GOOGLE_API_KEY)

if not GOOGLE_API_KEY:
    print("❌ ERROR: GOOGLE_API_KEY environment variable is required")
    sys.exit(1)

# Initialize the modern Gemini Client
client = genai.Client(api_key=GOOGLE_API_KEY)

# === ORACLE CONFIGURATION ===
DB_DSN = os.getenv("ORACLE_DSN", "localhost:1522/xepdb1")
USERNAME = os.getenv("ORACLE_USER", "system")
PASSWORD = os.getenv("ORACLE_PASSWORD", "oracle")
EMBEDDING_MODEL = "gemini-embedding-001" # Using the latest, more accurate model

print("="*60)
print("📊 Product Vector Embedding Generator (Modern SDK)")
print("="*60)
print(f"🔌 Database: {DB_DSN}")
print(f"👤 User: {USERNAME}")
print(f"🤖 Embedding Model: {EMBEDDING_MODEL}")
print("="*60)

# === CONNECTING TO ORACLE ===
try:
    connection = oracledb.connect(
        user=USERNAME,
        password=PASSWORD,
        dsn=DB_DSN
    )
    cursor = connection.cursor()
    # Ensure we are working in the BOOKSTORE schema
    cursor.execute("ALTER SESSION SET CURRENT_SCHEMA = BOOKSTORE")
    print(f"✅ Connected and switched to BOOKSTORE schema")

except Exception as e:
    print(f"❌ Failed to connect to Oracle: {e}")
    sys.exit(1)

# === FETCH PRODUCTS FROM DATABASE ===
try:
    # Fetching from the PRODUCTS table
    cursor.execute("SELECT id, code, description FROM products ORDER BY id")
    rows = cursor.fetchall()
    print(f"✅ Retrieved {len(rows)} products from BOOKSTORE.PRODUCTS")
except Exception as e:
    print(f"❌ Error fetching products: {e}")
    cursor.close()
    connection.close()
    sys.exit(1)

if not rows:
    print("⚠️ No products found in 'products' table.")
    cursor.close()
    connection.close()
    sys.exit(1)

ids_codes = [(row[0], row[1]) for row in rows]
descriptions = [row[2] for row in rows]

# === GENERATE EMBEDDINGS USING GOOGLE API ===

print("\n📈 Generating embeddings via Google Gemini...")
embeddings = []

try:
    # We loop to handle potential individual errors, but the SDK also supports batching
    for i, description in enumerate(descriptions, 1):
        try:
            # Modern SDK Call
            response = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=description,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
            )

            # Extract the vector values from the first embedding object
            # Note: response.embeddings[0].values returns a list of floats
            embedding_list = response.embeddings[0].values
            embedding_np = np.array(embedding_list, dtype=np.float32)
            embeddings.append(embedding_np)
            
            if i % 10 == 0 or i == len(descriptions):
                print(f"   ✓ Embedded {i}/{len(descriptions)} products")
        except Exception as e:
            print(f"❌ Error embedding product {i}: {e}")
            # Use 768 for embedding-001 or 768 for text-embedding-004 (configurable)
            embeddings.append(np.zeros(768, dtype=np.float32)) 

    print(f"✅ Generated embeddings for {len(embeddings)} products")
except Exception as e:
    print(f"❌ Error during embedding generation: {e}")
    cursor.close()
    connection.close()
    sys.exit(1)

# === CREATE EMBEDDINGS TABLE IF NOT EXISTS ===
print("\n📋 Creating 'embeddings_products' table...")
try:
    cursor.execute("""
        BEGIN
            EXECUTE IMMEDIATE '
                CREATE TABLE embeddings_products (
                    id NUMBER PRIMARY KEY,
                    code VARCHAR2(100),
                    description VARCHAR2(4000),
                    vector BLOB
                )
            ';
        EXCEPTION
            WHEN OTHERS THEN
                IF SQLCODE != -955 THEN
                    RAISE;
                END IF;
        END;
    """)
    print("✅ Table ready.")
except Exception as e:
    print(f"⚠️ Table operation: {e}")

# === INSERT OR UPDATE EMBEDDINGS ===
print("\n💾 Storing embeddings in database...")
try:
    for i, (id_code, vector) in enumerate(zip(ids_codes, embeddings)):
        id_, code = id_code
        description = descriptions[i]
        
        # Convert the float32 numpy array to raw bytes for BLOB storage
        vector_bytes = vector.tobytes()
        
        cursor.execute("""
            MERGE INTO embeddings_products tgt
            USING (SELECT :id AS id FROM dual) src
            ON (tgt.id = src.id)
            WHEN MATCHED THEN
                UPDATE SET code = :code, description = :description, vector = :vector
            WHEN NOT MATCHED THEN
                INSERT (id, code, description, vector)
                VALUES (:id, :code, :description, :vector)
        """, {
            "id": id_,
            "code": code,
            "description": description,
            "vector": vector_bytes
        })

    connection.commit()
    print(f"✅ Stored {len(embeddings)} embeddings successfully.")
except Exception as e:
    print(f"❌ Error storing embeddings: {e}")
    connection.rollback()
finally:
    cursor.close()
    connection.close()

print("\n" + "="*60)
print("✅ Vector embedding process completed successfully!")
print("="*60)