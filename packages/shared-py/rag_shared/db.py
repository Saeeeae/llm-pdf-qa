from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from .config import get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().POSTGRES_URL,
            pool_size=20,
            max_overflow=40,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    return _engine


async def get_db() -> AsyncSession:
    factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with factory() as session:
        yield session
