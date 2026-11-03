"""
Database connection for the Enterprise AI Knowledge Assistant.

Connects to PostgreSQL using the DATABASE_URL setting, which is read from the
environment or from a local .env file (never commit .env - it holds the password).
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to .env and fill in your PostgreSQL connection string."
    )

SCHEMA_FILE = Path(__file__).with_name("schema.sql")

# A pool reuses open connections across requests instead of reconnecting each time.
# Rows are returned as dictionaries, e.g. row["name"].
pool = ConnectionPool(DATABASE_URL, kwargs={"row_factory": dict_row}, open=False)


def init_db():
    """Open the connection pool and create the tables if they don't exist yet."""
    pool.open(wait=True)
    with pool.connection() as conn:
        conn.execute(SCHEMA_FILE.read_text())
