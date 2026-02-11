# -*- coding: utf-8 -*-
import os
import oracledb
import numpy as np
import difflib
from rapidfuzz import fuzz
from dotenv import load_dotenv
# NEW: Unified Google Gen AI SDK
from google import genai
from google.genai import types

load_dotenv()

class SearchSimilarProduct:
    def __init__(
            self,
            top_k=5,
            minimal_distance=1.0,
            embedding_model="gemini-embedding-001", # Updated to the latest stable model
            db_dsn=None,
            username=None,
            password=None
    ):
        # NEW: Google Gen AI Client Initialization
        api_key = "AIzaSyAynyiGr2cRDsV4SAr9F-IILZnAit-4xSY"
        if not api_key:
            raise ValueError("❌ GOOGLE_API_KEY environment variable is required")
        
        # Initialize the unified client
        self.client = genai.Client(api_key=api_key)

        # Oracle Configuration
        self.db_dsn = db_dsn or os.getenv("ORACLE_DSN", "localhost:1522/XEPDB1")
        self.username = username or os.getenv("ORACLE_USER", "system")
        self.password = password or os.getenv("ORACLE_PASSWORD", "oracle")

        self.top_k = top_k
        self.minimal_distance = minimal_distance
        self.embedding_model = embedding_model

        # Connect to Oracle using Thin Mode (Standard for 2.x+)
        try:
            self.conn = oracledb.connect(
                user=self.username,
                password=self.password,
                dsn=self.db_dsn
            )
            self.conn.execute("ALTER SESSION SET CURRENT_SCHEMA = BOOKSTORE")
            print(f"✅ Connected and switched to BOOKSTORE schema")
        except Exception as e:
            print(f"❌ Failed to connect to Oracle: {e}")
            raise

        print("📦 Loading Oracle Vectors...")
        self._load_embeddings()

    def _load_embeddings(self):
        """Load pre-computed embeddings from Oracle database"""
        try:
            with self.conn.cursor() as cursor:
                # Ensure the correct schema if needed
                cursor.execute("ALTER SESSION SET CURRENT_SCHEMA = BOOKSTORE")
                cursor.execute("SELECT id, code, description, vector FROM embeddings_products")
                
                self.vectors = []
                self.products = []
                
                for row in cursor.fetchall():
                    id_, code, description, blob = row
                    if blob:
                        # Convert BLOB to numpy array
                        vector = np.frombuffer(blob.read(), dtype=np.float32)
                        self.vectors.append(vector)
                        self.products.append({
                            "id": id_,
                            "code": code,
                            "description": description
                        })
                
                self.vectors = np.array(self.vectors)
                print(f"✅ Loaded {len(self.products)} products with vectors")
        except Exception as e:
            print(f"❌ Error loading embeddings: {e}")
            self.vectors = np.array([])
            self.products = []

    def _embed_text(self, text):
        """Generate embedding using the new Gen AI SDK Client"""
        try:
            # NEW: SDK call structure for embeddings
            response = self.client.models.embed_content(
                model=self.embedding_model,
                contents=text,
                config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY")
            )
            # The new SDK returns a list of embeddings; we take the first one
            return np.array(response.embeddings[0].values)
        except Exception as e:
            print(f"❌ Error generating embedding: {e}")
            return None

    def _correct_input(self, input_user):
        """Fuzzy correction for input search terms"""
        if not self.products:
            return input_user
        descriptions = [p["description"] for p in self.products]
        suggestions = difflib.get_close_matches(input_user, descriptions, n=1, cutoff=0.6)
        return suggestions[0] if suggestions else input_user

    def search_similar_products(self, description_input):
        """Perform semantic search with fuzzy fallback"""
        description_input = description_input.strip()
        description_corrected = self._correct_input(description_input)

        results = {
            "consult_original": description_input,
            "consult_used": description_corrected,
            "semantics": [],
            "fallback_fuzzy": []
        }

        if len(self.vectors) == 0:
            results["fallback_fuzzy"] = self._fuzzy_fallback(description_corrected)
            return results

        consult_emb = self._embed_text(description_corrected)
        if consult_emb is None:
            results["fallback_fuzzy"] = self._fuzzy_fallback(description_corrected)
            return results

        # Vector similarity (Euclidean)
        dists = np.linalg.norm(self.vectors - consult_emb, axis=1)
        top_indices = np.argsort(dists)[:self.top_k]

        for idx in top_indices:
            dist = dists[idx]
            if dist < self.minimal_distance:
                match = self.products[idx]
                similarity = 1 / (1 + dist)
                results["semantics"].append({
                    "id": match["id"],
                    "code": match["code"],
                    "description": match["description"],
                    "similarity": round(similarity * 100, 2),
                    "distance": round(dist, 4)
                })

        if not results["semantics"]:
            results["fallback_fuzzy"] = self._fuzzy_fallback(description_corrected)

        return results

    def _fuzzy_fallback(self, description_corrected):
        """RapidFuzz fallback for when vector search yields no close matches"""
        better_fuzz = []
        for product in self.products:
            score = fuzz.token_sort_ratio(description_corrected, product["description"])
            better_fuzz.append((product, score))
        
        better_fuzz.sort(key=lambda x: x[1], reverse=True)
        return [
            {
                "id": p["id"], 
                "code": p["code"], 
                "description": p["description"], 
                "score_fuzzy": round(s, 2)
            } for p, s in better_fuzz[:self.top_k]
        ]