from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator
from urllib.parse import quote_plus

import psycopg
from psycopg.rows import dict_row

DEFAULT_PG_USER = "salescrm"
DEFAULT_PG_PASSWORD = "salescrm"
DEFAULT_PG_DB = "salescrm"
DEFAULT_PG_HOST = "localhost"
DEFAULT_PG_PORT = "5432"


def database_url() -> str:
    configured = os.getenv("DATABASE_URL", "").strip()
    if configured:
        return configured
    user = os.getenv("POSTGRES_USER", DEFAULT_PG_USER)
    password = os.getenv("POSTGRES_PASSWORD", DEFAULT_PG_PASSWORD)
    host = os.getenv("POSTGRES_HOST", DEFAULT_PG_HOST)
    port = os.getenv("POSTGRES_PORT", DEFAULT_PG_PORT)
    db = os.getenv("POSTGRES_DB", DEFAULT_PG_DB)
    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{quote_plus(db)}"
    )


def db_path() -> str:
    """Legacy helper — returns DATABASE_URL for logging/diagnostics."""
    return database_url()


@contextmanager
def get_conn() -> Iterator[Any]:
    with psycopg.connect(database_url(), row_factory=dict_row) as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
