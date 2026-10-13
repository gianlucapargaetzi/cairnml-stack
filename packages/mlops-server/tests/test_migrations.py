from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from mlops_server.db import Base
from mlops_server.migrate import upgrade
from sqlalchemy import create_engine, inspect


def test_migrations_produce_exactly_the_model_schema(pg_url):
    engine = create_engine(pg_url)
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    upgrade(pg_url)
    tables = set(inspect(engine).get_table_names())
    assert {"users", "clients", "agents", "jobs", "log_chunks"} <= tables
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], diff
    upgrade(pg_url)  # idempotent
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
