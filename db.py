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

# Read settings from the .env file into environment variables
load_dotenv()

# Stop straight away with a clear message if the database isn't configured
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to .env and fill in your PostgreSQL connection string."
    )

SCHEMA_FILE = Path(__file__).with_name("schema.sql")

# A pool reuses open connections across requests instead of reconnecting each time.
# Rows are returned as dictionaries, e.g. row["name"].
pool = ConnectionPool(
    DATABASE_URL,
    kwargs={"row_factory": dict_row},
    # Don't connect when this file is imported; init_db() opens the pool when the app starts
    open=False,
    # Neon (and other hosted Postgres) drops idle connections; test each pooled
    # connection before use so a dropped one is replaced instead of erroring.
    check=ConnectionPool.check_connection,
)


def init_db():
    """Open the connection pool and create the tables if they don't exist yet."""
    # wait=True blocks until a connection succeeds, so a wrong DATABASE_URL fails at startup
    pool.open(wait=True)
    # schema.sql only uses "IF NOT EXISTS", so running it every startup is safe
    with pool.connection() as conn:
        conn.execute(SCHEMA_FILE.read_text())
