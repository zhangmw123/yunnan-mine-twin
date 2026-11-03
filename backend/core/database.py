import asyncpg

from core.config import DATABASE_URL

_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        dsn = DATABASE_URL.replace("postgresql://", "postgres://")
        _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
    return _pool


async def fetch(sql, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(sql, *args)


async def fetchrow(sql, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(sql, *args)


async def execute(sql, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(sql, *args)
