# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an **Oracle Database + MCP + Gemini AI** invoice reconciliation agent that uses semantic search with vector embeddings to match customer returns to original outbound invoices. The agent handles typos, partial names, and price variances through fuzzy matching and semantic similarity.

## Architecture

### Three-Layer System

1. **Oracle Database Layer**
   - Oracle 21c XE running on `localhost:1522/xepdb1`
   - Schema: `BOOKSTORE`
   - Tables: `PRODUCTS`, `INVOICE`, `ITEM_INVOICE`, `embeddings_products`
   - PL/SQL function: `fn_advanced_search` for fuzzy text matching
   - Vector embeddings stored as BLOBs (768-dimension float32 arrays)

2. **MCP Server Layer** (`server_invoice_items.py`)
   - FastMCP server exposing database operations as MCP tools
   - Tools: `search_vectorized_product`, `resolve_ean`, `search_invoices_by_criteria`, `get_system_status`
   - Runs via stdio transport (stdout must remain clean for JSON-RPC)
   - Uses context manager for connection management

3. **Agent Layer** (`main.py`)
   - MCP client that orchestrates a Gemini 2.0 Flash agent
   - Implements ReAct pattern (reasoning + acting loop)
   - Maintains conversation history for multi-turn interactions
   - Calls MCP tools through stdio pipes

### Key Components

- **`database.py`**: Async connection pooling (feature branch - not yet in main)
  - Uses `oracledb.create_pool_async` for connection pooling
  - Configurable min/max connections via environment variables
  - Supports both Thin mode (pure Python) and Thick mode (with Oracle Instant Client)

- **`product_search.py`**: Semantic search implementation
  - Loads all product embeddings into memory at initialization
  - Computes Euclidean distance between query and product vectors
  - Provides fallback fuzzy matching using `rapidfuzz` and `difflib`
  - **Important**: Maintains a persistent Oracle connection; must be closed properly

- **`process_vector_products.py`**: Embedding generation
  - Fetches products from Oracle
  - Generates 768-dim embeddings via `gemini-embedding-001`
  - Stores embeddings as BLOB in `embeddings_products` table
  - Uses `MERGE` statement for upsert operation

- **`setup_database.py`**: Database initialization
  - Drops and recreates all tables and functions
  - Executes SQL scripts in order: tables → functions → products → invoices
  - Smart SQL parsing for PL/SQL blocks (handles BEGIN/END and `/` terminators)
  - Includes verification and test steps

## Development Workflow

### Initial Setup

1. **Environment Configuration**:
   ```bash
   # Create .env file with:
   GEMINI_API_KEY=your_key_here
   ORACLE_DSN=localhost:1522/xepdb1
   ORACLE_USER=system
   ORACLE_PASSWORD=oracle
   # Optional for connection pooling:
   DB_POOL_MIN=1
   DB_POOL_MAX=10
   DB_POOL_INC=1
   # Optional for Thick mode:
   ORACLE_LIB_DIR=C:\oracle\instantclient_23_0
   ```

2. **Install Dependencies**:
   ```bash
   python -m venv venv
   source venv/Scripts/activate  # Windows Git Bash
   pip install -r requirements.txt
   ```

3. **Database Setup**:
   ```bash
   # Initialize database schema and data
   python setup_database.py
   ```

4. **Generate Embeddings**:
   ```bash
   # Generate and store 768-dim embeddings for all products
   python process_vector_products.py
   ```

5. **Run the Agent**:
   ```bash
   # Start the MCP client + Gemini agent
   python main.py
   ```

### Testing Individual Components

- **Test database connection**: `python oracle_conn.py`
- **Test MCP server** (should produce no stdout output): `python server_invoice_items.py`
- **Query database directly**: Use SQL*Plus, SQL Developer, or Oracle SQL Developer Web

### Common Commands

```bash
# Activate virtual environment
source venv/Scripts/activate  # Windows Git Bash
. venv/bin/activate            # Linux/Mac

# Run full setup sequence
python setup_database.py && python process_vector_products.py && python main.py

# Check Python version (requires 3.8+)
python --version

# Install single package
pip install package_name

# Regenerate embeddings after product changes
python process_vector_products.py
```

## Important Constraints

### MCP Server Rules

- **No stdout pollution**: MCP servers communicate via JSON-RPC over stdout. Any debug output must go to `stderr` using `print(..., file=sys.stderr)`
- **Server startup**: The MCP client (main.py) launches the server as a subprocess with unbuffered output (`-u` flag)
- **Connection cleanup**: Always close Oracle connections in finally blocks or context managers

### Oracle Database Considerations

- **Schema switching**: Code sets `CURRENT_SCHEMA = BOOKSTORE` after connecting
- **Instant Client**: Optional for Thick mode; defaults to Thin mode (pure Python driver)
- **Connection pooling**: The new `database.py` module provides async pooling but is not yet integrated into the MCP server
- **BLOB storage**: Embeddings stored as raw bytes from `numpy.ndarray.tobytes()`; read back with `np.frombuffer(blob.read(), dtype=np.float32)`

### Gemini API Integration

- **Model versions**:
  - Agent: `gemini-2.0-flash` (main.py)
  - Embeddings: `gemini-embedding-001` (768 dimensions)
- **Task types**: Use `RETRIEVAL_DOCUMENT` for indexing, `SEMANTIC_SIMILARITY` for queries
- **Rate limits**: The modern SDK (`google-genai`) handles retries automatically

### Environment Variables

All configuration uses `python-decouple` for loading from `.env`:
- `GEMINI_API_KEY`: Required for all Gemini API calls
- `ORACLE_DSN`: Database connection string (default: `localhost:1521/xe`)
- `ORACLE_USER`: Database username (default: `admin`)
- `ORACLE_PASSWORD`: Database password (default: `password`)
- `ORACLE_LIB_DIR`: Path to Oracle Instant Client (optional, for Thick mode)
- `DB_POOL_MIN`, `DB_POOL_MAX`, `DB_POOL_INC`: Connection pool settings (optional)

## File Organization

```
oracle-mcp/
├── main.py                      # MCP client + Gemini agent (entry point)
├── server_invoice_items.py      # MCP server (FastMCP)
├── database.py                  # Async connection pooling module
├── product_search.py            # Semantic search implementation
├── process_vector_products.py   # Embedding generation script
├── setup_database.py            # Database initialization script
├── oracle_conn.py               # Simple connection test
├── database_sql_scripts/        # SQL files for schema and data
│   ├── script.sql               # Table definitions
│   ├── similarity_search.sql    # PL/SQL function for fuzzy search
│   ├── inserts_products_books.sql
│   └── invoice_data_insert.sql
├── requirements.txt
├── .env                         # Environment variables (not in git)
├── .gitignore
└── README.md
```

## Troubleshooting

### Oracle Connection Issues

- Verify Oracle is running: `lsnrctl status`
- Check port (1522 for XE, 1521 for standard)
- Confirm service name: `xepdb1` (pluggable DB) or `xe` (container)
- Test with `python oracle_conn.py`

### MCP Communication Failures

- Check for stdout pollution in server code (must use stderr for debug)
- Verify server script has no syntax errors
- Run server standalone: `python -u server_invoice_items.py`
- Check MCP initialization in main.py logs (stderr)

### Embedding/Search Issues

- Regenerate embeddings: `python process_vector_products.py`
- Verify table exists: `SELECT COUNT(*) FROM embeddings_products`
- Check vector dimensions match (768 for gemini-embedding-001)
- Ensure BOOKSTORE schema is set: `ALTER SESSION SET CURRENT_SCHEMA = BOOKSTORE`

### Gemini API Issues

- Verify API key: `echo $GEMINI_API_KEY`
- Check quota/rate limits in Google AI Studio
- Review model availability (gemini-2.0-flash requires allowlist access)

## Branch Context

Current branch: `feature/oracle-connection-pooling`
- Adds `database.py` with async connection pooling
- Not yet integrated into MCP server (still uses synchronous connections)
- To integrate: Update `server_invoice_items.py` to use `DatabasePool.execute_query()` instead of direct connections
