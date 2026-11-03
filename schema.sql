-- Enterprise AI Knowledge Assistant - PostgreSQL schema
-- Run automatically by db.init_db() when the app starts (safe to run repeatedly).

-- pgvector adds a "vector" column type so document embeddings can be stored
-- alongside the documents for semantic search in later iterations.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    category        TEXT NOT NULL,
    confidentiality TEXT NOT NULL DEFAULT 'Internal',
    source          TEXT NOT NULL,
    content         TEXT NOT NULL,
    embedding       vector(384),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_documents_category ON documents (category);
