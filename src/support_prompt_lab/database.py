from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from support_prompt_lab.config import get_settings


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models and Alembic metadata."""


def create_engine() -> AsyncEngine:
    """Create the application database engine from runtime settings."""

    return create_async_engine(str(get_settings().database_url), pool_pre_ping=True)


engine = create_engine()
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_database_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped asynchronous database session."""

    async with session_factory() as session:
        yield session
