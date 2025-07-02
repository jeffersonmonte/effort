from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from sqlmodel import SQLModel # Import SQLModel
# Import all your models here so Alembic knows about them
from app.models import User, Interview, AnswerBlock, BpmnDiagram

# target_metadata = mymodel.Base.metadata
# For SQLModel, all models share the same SQLModel.metadata
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # For async, we need to create an async engine from the config
    # and then run the migrations in an asyncio event loop.
    # The `config.get_main_option("sqlalchemy.url")` should provide the async URL.

    # Option 1: Use the engine from app.db if possible (ensures same config)
    # However, env.py should be self-contained or rely only on alembic.ini for URL.
    # from app.db import async_engine # This couples env.py too tightly with app structure for some tastes
    # connectable = async_engine

    # Option 2: Recreate an async engine here based on alembic.ini configuration
    # This is the more standard Alembic approach.
    from sqlalchemy.ext.asyncio import create_async_engine

    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"), # Get URL from alembic.ini
        poolclass=pool.NullPool, # As recommended for Alembic online mode
    )

    async def run_async_migrations():
        """Run migrations asynchronously."""
        async with connectable.connect() as connection:
            # Configure context with connection and metadata
            # For SQLModel, include_schemas=True might be useful for multi-schema setups,
            # but not typically needed for single default schema.
            await connection.run_sync(do_run_migrations)

        await connectable.dispose()

    def do_run_migrations(connection):
        """Helper function to run migrations within the sync callback of run_sync."""
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    import asyncio
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
