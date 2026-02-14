# database.py
import os
import oracledb
import asyncio
from decouple import config

# Configuration
DB_DSN = config('ORACLE_DSN', default='localhost:1521/xe')
USERNAME = config('ORACLE_USER', default='admin')
PASSWORD = config('ORACLE_PASSWORD', default='password')
LIB_DIR = config('ORACLE_LIB_DIR', default=None) # Optional: For Thick mode

# Pool Configuration
MIN_CONN = int(config('DB_POOL_MIN', default=1))
MAX_CONN = int(config('DB_POOL_MAX', default=10))
INCREMENT = int(config('DB_POOL_INC', default=1))

class DatabasePool:
    _pool = None

    @classmethod
    async def initialize(cls):
        """Initializes the Async Connection Pool"""
        if cls._pool is not None:
            return

        print("🔌 Initializing Oracle Connection Pool...")
        
        # Initialize Instant Client only if specifically configured (Thick Mode)
        # Otherwise, defaults to Thin Mode (Pure Python) which is preferred for Containers/Cloud
        if LIB_DIR and os.path.exists(LIB_DIR):
            try:
                oracledb.init_oracle_client(lib_dir=LIB_DIR)
            except Exception as e:
                print(f"⚠️ Warning: Could not init Oracle Client (falling back to Thin mode): {e}")

        try:
            cls._pool = oracledb.create_pool_async(
                user=USERNAME,
                password=PASSWORD,
                dsn=DB_DSN,
                min=MIN_CONN,
                max=MAX_CONN,
                increment=INCREMENT,
                getmode=oracledb.POOL_GETMODE_WAIT
            )
            print(f"✅ Connection Pool created (Min: {MIN_CONN}, Max: {MAX_CONN})")
        except Exception as e:
            print(f"❌ Failed to create pool: {e}")
            raise

    @classmethod
    async def get_connection(cls):
        """Acquires a connection from the pool"""
        if cls._pool is None:
            await cls.initialize()
        return await cls._pool.acquire()

    @classmethod
    async def close(cls):
        """Closes the pool"""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
            print("🔒 Connection Pool closed")

    @classmethod
    async def execute_query(cls, sql, params=None, fetch_all=True):
        """Helper for executing queries efficiently"""
        conn = await cls.get_connection()
        result = None
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(sql, params or {})
                if fetch_all:
                    result = await cursor.fetchall()
                else:
                    result = await cursor.fetchone()
                await conn.commit()
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            # Important: Release connection back to pool
            await cls._pool.release(conn) 
        return result