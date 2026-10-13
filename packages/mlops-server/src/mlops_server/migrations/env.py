from alembic import context
from mlops_server import models  # noqa: F401  (register tables)
from mlops_server.db import Base
from sqlalchemy import create_engine

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = create_engine(config.get_main_option("sqlalchemy.url"))
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
