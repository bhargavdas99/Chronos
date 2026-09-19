import asyncpg
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgres://chronos_user:chronos_password@localhost:6432/chronos_db"
)

pool: asyncpg.Pool = None

async def init_db():
    global pool
    pool = await asyncpg.create_pool(
        dsn=DATABASE_URL,
        min_size=5,
        max_size=20,
        statement_cache_size=0,  # Disables prepared statements for PgBouncer
        ssl=False,
        server_settings={}       # Stops asyncpg from executing startup SET commands
    )
    print("✅ AsyncPG Connection Pool initialized (PgBouncer mode).")

async def close_db():
    global pool
    if pool:
        await pool.close()
        print("🛑 AsyncPG Connection Pool closed.")

def get_pool() -> asyncpg.Pool:
    return pool