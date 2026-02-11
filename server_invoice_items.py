# -*- coding: utf-8 -*-
import os
import sys
import oracledb
from mcp.server.fastmcp import FastMCP
from product_search import SearchSimilarProduct
from dotenv import load_dotenv
from contextlib import contextmanager

load_dotenv()

# === DB CONFIGURATION ===
# Priority: .env ORACLE_DSN > individual components
host = os.getenv("DB_HOST", "localhost")
port = os.getenv("DB_PORT", "1522")
service = os.getenv("DB_SERVICE", "xepdb1")
local_dsn = f"{host}:{port}/{service}"

DB_DSN = os.getenv("ORACLE_DSN", local_dsn)
USERNAME = os.getenv("ORACLE_USER", "system")
PASSWORD = os.getenv("ORACLE_PASSWORD", "oracle")

# === DATABASE CONTEXT MANAGER ===
@contextmanager
def get_db_connection():
    """Context manager for clean Oracle connection handling"""
    conn = None
    try:
        conn = oracledb.connect(
            user=USERNAME,
            password=PASSWORD,
            dsn=DB_DSN
        )
        # Automatically switch to the correct schema
        with conn.cursor() as cursor:
            cursor.execute_query(query="ALTER SESSION SET CURRENT_SCHEMA = BOOKSTORE")
        
        yield conn
    except Exception as e:
        print(f"❌ Database error: {e}", file=sys.stderr)
        raise
    finally:
        if conn:
            conn.close()

# === INITIALIZATION ===
mcp = FastMCP("InvoiceItemResolver")

try:
    searcher = SearchSimilarProduct()
    # Use file=sys.stderr
    print("✅ Product search service initialized", file=sys.stderr)
except Exception as e:
    print(f"⚠️  Product search service failed: {e}", file=sys.stderr)
    searcher = None

# === HELPER FUNCTIONS ===

def execute_query(query: str, params: dict = None):
    """Execute a query and return all results"""
    if params is None: params = {}
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
    except Exception:
        return []

# === MCP TOOLS ===

@mcp.tool()
def search_vectorized_product(description: str) -> dict:
    """Searches for a product using semantic embeddings for similarity."""
    if searcher is None:
        return {"error": "Product search service not available"}
    try:
        return searcher.search_similar_products(description)
    except Exception as e:
        return {"error": f"Search failed: {str(e)}"}

@mcp.tool()
def resolve_ean(description: str) -> dict:
    """Resolves EAN via advanced scoring (Direct/Phonetic/Similarity)."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                query = "SELECT * FROM TABLE(fn_advanced_search(:1)) ORDER BY similarity DESC"
                cursor.execute(query, [description])
                row = cursor.fetchone()
                
                if row:
                    return {"code": row[0], "description": row[1], "similarity": row[2]}
                return {"error": "No matching EAN found"}
    except Exception as e:
        return {"error": f"EAN resolution failed: {str(e)}"}

@mcp.tool()
def search_invoices_by_criteria(
    customer: str = None,
    state: str = None,
    price: float = None,
    ean: str = None,
    margin: float = 0.05
) -> list:
    """Searches for A/R invoices based on multiple criteria."""
    try:
        query = """
            SELECT nf.no_invoice, nf.name_customer, nf.state, nf.date_print,
                   inf.no_item, inf.code_ean, inf.description_product, inf.value_unitary
            FROM invoice nf
            JOIN item_invoice inf ON nf.no_invoice = inf.no_invoice
            WHERE 1=1
        """
        params = {}

        if customer:
            query += " AND LOWER(nf.name_customer) LIKE LOWER(:customer)"
            params["customer"] = f"%{customer}%"
        if state:
            query += " AND LOWER(nf.state) = LOWER(:state)"
            params["state"] = state
        if ean:
            query += " AND inf.code_ean = :ean"
            params["ean"] = ean
        if price is not None and price > 0:
            query += " AND inf.value_unitary BETWEEN :price_min AND :price_max"
            params["price_min"] = price * (1 - margin)
            params["price_max"] = price * (1 + margin)

        results = execute_query(query, params)
        cols = ["no_invoice", "name_customer", "state", "date_print", 
                "no_item", "code_ean", "description_product", "value_unitary"]
        
        return [dict(zip(cols, row)) for row in results]
    except Exception as e:
        return [{"error": f"Invoice search failed: {str(e)}"}]

# === SERVER START ===

if __name__ == "__main__":
    print(f"🔌 MCP Server starting for Oracle at {DB_DSN}...", file=sys.stderr)
    mcp.run(transport="stdio")