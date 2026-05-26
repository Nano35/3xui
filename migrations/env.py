import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Add project root directory to path so we can import app modules
sys.path.append(str(Path(__file__).parent.parent))

from app.config import settings
from app.database import Base
# Make sure models are imported so metadata is populated
from app.models import Base

config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = settings.get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    
    Creates an AsyncEngine and associates a connection with the context.
    """
    configuration = config.get_section(config.config_ini_section, {})
    # Inject the database connection URL from Settings
    configuration["sqlalchemy.url"] = settings.get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    try:
        asyncio.run(run_migrations_online())
    except RuntimeError:
        # If there is already an event loop running, we use it (e.g. inside test environments)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(run_migrations_online())
        else:
            loop.run_until_complete(run_migrations_online())
