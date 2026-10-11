"""Readiness checks schema compatibility, not merely a live DB connection."""
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from .common import Problem
from .db import Base


def schema_readiness(connection, require_migration=True):
    try:
        connection.execute(text("SELECT 1"))
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if not set(Base.metadata.tables) <= tables:
            raise Problem(503, "SCHEMA_NOT_READY", "Схема хранилища не готова. Оператору нужно завершить миграции.")
        columns = inspector.get_multi_columns(filter_names=list(Base.metadata.tables))
        for name, table in Base.metadata.tables.items():
            actual = {column["name"] for column in columns.get((None, name), [])}
            if not set(table.columns.keys()) <= actual:
                raise Problem(503, "SCHEMA_NOT_READY", "Схема хранилища несовместима. Оператору нужно завершить миграции.")
        if require_migration:
            expected = set(ScriptDirectory(str(Path(__file__).resolve().parents[1] / "migrations")).get_heads())
            current = set(MigrationContext.configure(connection).get_current_heads())
            if current != expected:
                raise Problem(503, "SCHEMA_NOT_READY", "Версия хранилища несовместима. Оператору нужно завершить миграции.")
        return {"schema": True, "migration": "checked" if require_migration else "explicit_local_create_all"}
    except SQLAlchemyError:
        raise Problem(503, "DATABASE_UNAVAILABLE", "Хранилище временно недоступно. Повторите действие позже.") from None
