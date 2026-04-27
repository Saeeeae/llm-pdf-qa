import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

URL = os.getenv("POSTGRES_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/rag")

engine = create_async_engine(URL, pool_size=10, max_overflow=20, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as s:
        yield s
