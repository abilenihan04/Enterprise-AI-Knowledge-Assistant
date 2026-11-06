-- Enterprise AI Knowledge Assistant - PostgreSQL schema
-- Run automatically by db.init_db() when the app starts (safe to run repeatedly).

-- pgvector adds a "vector" column type and similarity search, so document
-- embeddings live in the same database as the documents.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    category        TEXT NOT NULL,
    confidentiality TEXT NOT NULL DEFAULT 'Internal',
    source          TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_documents_category ON documents (category);

-- Each document is split into chunks; each chunk has an embedding (384 numbers from
-- the all-MiniLM-L6-v2 model). Deleting a document deletes its chunks.
CREATE TABLE IF NOT EXISTS document_chunks (
    id          BIGSERIAL PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(384) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks (document_id);

-- HNSW index makes "find the most similar chunks" fast; <=> is cosine distance.
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
    ON document_chunks USING hnsw (embedding vector_cosine_ops);

-- Keyword search: each chunk's words, stemmed (e.g. "booking" -> "book") with stop words
-- removed. Kept up to date automatically by PostgreSQL. The GIN index makes word lookups fast.
ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

CREATE INDEX IF NOT EXISTS idx_document_chunks_search
    ON document_chunks USING gin (search_vector);
