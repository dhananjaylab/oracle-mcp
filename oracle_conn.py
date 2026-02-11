# import oracledb
# import os
# from dotenv import load_dotenv

# load_dotenv()

# # Load credentials from environment variables
# user = os.getenv("DB_USER")
# print(user)
# password = os.getenv("DB_PASSWORD")
# print(password)
# host = os.getenv("DB_HOST", "db.freesql.com")
# print(host)
# port = os.getenv("DB_PORT", "1521")
# print(port)
# service = os.getenv("DB_SERVICE", "23ai_34ui2")
# print(service)

# if not user or not password:
#     raise ValueError("DB_USER and DB_PASSWORD environment variables are required")

# oracledb.init_oracle_client(
#     lib_dir=r"C:\oracle\instantclient_23_0"
# )

# local_dsn = f"{host}:{port}/{service}"

# try:

#     connection = oracledb.connect(
#         user=user,
#         password=password,
#         dsn=local_dsn)
    
#     print("Successfully connected to Oracle Database")
    
#     cursor = connection.cursor()
#     for result in cursor.execute("SELECT * FROM EMBEDDINGS_PRODUCTS"):
#         print(result)
    
#     cursor.close()
#     connection.close()
    
# except oracledb.DatabaseError as e:
#     print(f"Connection failed: {e}")
#     print("Verify your credentials and DSN are correct")
import oracledb

# Port 1522 (verified by lsnrctl) 
# Service xepdb1 (verified by lsnrctl)
DSN = "localhost:1522/xepdb1" 

print("🔌 Connecting to Local Oracle 21c XE...")

try:
    connection = oracledb.connect(
        user="system",
        password="oracle",
        dsn=DSN
    )
    print("✅ Connected successfully to XEPDB1!")
    
    # Optional: Check if the products table is there
    cursor = connection.cursor()
    cursor.execute("SELECT table_name FROM user_tables WHERE table_name = 'PRODUCTS'")
    cursor.execute("SELECT * FROM TABLE(fn_advanced_search('harry poter'))")
    for row in cursor.fetchall():
        print(f"Match Found: {row}")
    row = cursor.fetchone()
    if row:
        print("📦 Table 'PRODUCTS' found!")
    else:
        print("⚠️ 'PRODUCTS' table not found in this schema.")
        
except oracledb.Error as e:
    print(f"❌ Oracle Error: {e}")