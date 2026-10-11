"""A bounded SQLite SELECT over caller-provided synthetic data, never application data.

This is a data-only SQL assessment, NOT a sandbox for Python, JavaScript or shell.
SQLite authorizer denies writes, attachments, pragmas and unknown functions. Parsing
and VM instruction budgets are fixed. Every invocation owns a fresh memory DB.
"""

import json
import sqlite3
from typing import Any

MAX_QUERY_BYTES = 12_000
MAX_INPUT_ROWS = 200
MAX_RESULT_ROWS = 201
MAX_VM_STEPS = 100_000
ALLOWED_FUNCTIONS = {"sum", "count", "avg", "min", "max", "coalesce", "ifnull", "nullif", "round", "abs", "lower", "upper", "length", "row_number", "rank", "dense_rank", "lag", "lead", "total", "cast", "strftime", "date"}


def execute_select(query: Any, dataset: dict) -> dict:
    try:
        valid_query = isinstance(query, str) and bool(query.strip()) and len(query.encode("utf-8")) <= MAX_QUERY_BYTES
    except UnicodeEncodeError:
        valid_query = False
    if not valid_query:
        return {"ok": False, "error": "Введите один SELECT длиной не более 12 КБ."}
    connection = sqlite3.connect(":memory:")
    try:
        total_rows = 0
        for table_name, table in dataset.items():
            if not str(table_name).isidentifier():
                raise ValueError("Invalid trusted table name")
            columns = table["columns"]
            if not all(str(name).isidentifier() for name in columns):
                raise ValueError("Invalid trusted column name")
            rows = table["rows"]
            total_rows += len(rows)
            if total_rows > MAX_INPUT_ROWS:
                raise ValueError("Trusted dataset exceeds row limit")
            definition = ",".join(f'"{name}" {kind}' for name, kind in columns.items())
            if not all(kind in ("TEXT", "INTEGER", "REAL") for kind in columns.values()):
                raise ValueError("Invalid trusted column type")
            connection.execute(f'CREATE TABLE "{table_name}" ({definition})')
            marks = ",".join("?" for _ in columns)
            connection.executemany(f'INSERT INTO "{table_name}" VALUES ({marks})', rows)
        connection.commit()
        connection.execute("PRAGMA query_only=ON")
        allowed_actions = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE}

        def authorize(action, first, second, database, trigger):
            if action==sqlite3.SQLITE_READ and (str(first).startswith("sqlite_") or database not in (None,"main")):
                return sqlite3.SQLITE_DENY
            if action in allowed_actions:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_FUNCTION and str(second or first).casefold() in ALLOWED_FUNCTIONS:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        connection.set_authorizer(authorize)
        steps = 0

        def budget():
            nonlocal steps
            steps += 1000
            return int(steps >= MAX_VM_STEPS)

        connection.set_progress_handler(budget, 1000)
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 100_000)
        connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, MAX_QUERY_BYTES)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 32)
        cursor = connection.execute(query)
        if cursor.description is None:
            return {"ok": False, "error": "Разрешено только чтение результата SELECT."}
        rows = cursor.fetchmany(MAX_RESULT_ROWS)
        if len(rows) >= MAX_RESULT_ROWS:
            return {"ok": False, "error": "Результат превышает 200 строк."}
        return {"ok": True, "columns": [item[0] for item in cursor.description], "rows": [list(row) for row in rows]}
    except (sqlite3.Error, ValueError, TypeError, OverflowError):
        return {"ok": False, "error": "Запрос отклонён: проверьте синтаксис, ограничения и таблицы задания."}
    finally:
        connection.close()


def canonical_rows(rows: list) -> list[str]:
    """Compare result values as a multiset; result column labels are not scored."""
    normalized = []
    for row in rows:
        normalized.append(json.dumps([round(value, 6) if isinstance(value, float) else value for value in row], ensure_ascii=False, separators=(",", ":")))
    return sorted(normalized)
