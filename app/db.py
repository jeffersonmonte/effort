from sqlmodel import SQLModel # create_engine is for sync
from sqlmodel.ext.asyncio.session import AsyncSession, AsyncEngine
from sqlalchemy.ext.asyncio import create_async_engine # Use this for async engine creation
from typing import AsyncGenerator

# Import models to ensure they are registered with SQLModel.metadata when Alembic runs or tables are created.
from app.models import User, Interview, AnswerBlock, BpmnDiagram

# SQLite specific: For async, SQLite needs `aiosqlite`. Poetry should have installed it.
# Add `aiosqlite` to dependencies if not already transitively included.
# `poetry add aiosqlite`
DATABASE_URL = "sqlite+aiosqlite:///./interview_bpmn.db"  # Use aiosqlite driver for async

# Create the async database engine.
# echo=True is for logging SQL statements, useful for debugging.
# For SQLite with aiosqlite, `connect_args` like `check_same_thread` is not needed/used.
async_engine = AsyncEngine(create_async_engine(DATABASE_URL, echo=True))


async def init_db():
    """
    Initializes the database. For Alembic-managed schemas, this function
    might not be needed to create tables, but it's a good place for other
    DB-related startup logic if any.
    Alembic handles table creation via migrations.
    """
    # SQLModel.metadata.create_all(async_engine) # This would create tables
    # This is normally NOT called if using Alembic. Alembic handles schema creation.
    # We call this in main.py's lifespan only if NOT using Alembic for initial setup.
    # Since we ARE using Alembic, this function might be empty or do other init tasks.
    # For now, let's keep it as a placeholder for potential async engine related initializations
    # if any were needed beyond what Alembic does.
    # Example: ensure the DB file exists or basic connection check.
    # With Alembic, `alembic upgrade head` is the primary way to ensure schema.
    pass


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency to get an async database session.
    """
    async with AsyncSession(async_engine) as session:
        yield session

# The create_db_and_tables function (sync) is no longer needed as we are moving to async
# and Alembic handles table creation.
# The synchronous `engine` is also replaced by `async_engine`.
# If any part of the app strictly needs a sync engine for some reason (e.g. a script not using asyncio),
# a separate sync engine setup could co-exist, but for the main FastAPI app, async is preferred.
