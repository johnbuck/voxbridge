"""
VoxBridge 2.0 - Database Session Management

Async SQLAlchemy session factory with connection pooling.

Usage:
    from src.database.session import get_db_session, init_db

    # Initialize on startup
    await init_db()

    # Use in async context
    async with get_db_session() as session:
        result = await session.execute(select(Agent))
        agents = result.scalars().all()
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from src.database.models import Base

# Database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://voxbridge:voxbridge_dev_password@postgres:5432/voxbridge",
)

# Async engine with connection pooling
# pool_size: Number of connections to maintain
# max_overflow: Additional connections allowed above pool_size
# pool_pre_ping: Verify connections before using (prevents stale connections)
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging
    pool_size=5,  # Adjust based on expected concurrent users
    max_overflow=10,  # Allow up to 15 total connections (5 + 10)
    pool_pre_ping=True,  # Test connections before use
    pool_recycle=3600,  # Recycle connections after 1 hour
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit
    autoflush=False,  # Manual control of flush operations
    autocommit=False,  # Manual control of commits
)


async def init_db():
    """
    Initialize database schema.

    Creates all tables defined in models.py if they don't exist.
    Should be called on application startup.

    Note: For production, use Alembic migrations instead of create_all().
    """
    async with engine.begin() as conn:
        # Create all tables (development only - use Alembic in production)
        await conn.run_sync(Base.metadata.create_all)


async def drop_db():
    """
    Drop all database tables.

    WARNING: Destructive operation! Only use in development/testing.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions.

    Yields:
        AsyncSession: SQLAlchemy async session

    Usage:
        async with get_db_session() as session:
            result = await session.execute(select(Agent))
            agents = result.scalars().all()

    Automatically commits on success, rolls back on exception.
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db_session_dependency() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.

    Usage in FastAPI routes:
        @app.get("/agents")
        async def list_agents(db: AsyncSession = Depends(get_db_session_dependency)):
            result = await db.execute(select(Agent))
            return result.scalars().all()
    """
    async with get_db_session() as session:
        yield session


# Health check function
async def check_db_connection() -> bool:
    """
    Check database connectivity.

    Returns:
        bool: True if database is reachable, False otherwise

    Usage:
        if await check_db_connection():
            print("Database connection OK")
    """
    try:
        async with get_db_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False
