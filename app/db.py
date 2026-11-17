from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str, *, null_pool: bool = False) -> AsyncEngine:
    """Create the global engine. Tests call this with their own database URL."""
    global _engine, _sessionmaker
    kwargs: dict = {"poolclass": NullPool} if null_pool else {"pool_pre_ping": True}
    _engine = create_async_engine(url, **kwargs)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("Database engine is not initialised")
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session
