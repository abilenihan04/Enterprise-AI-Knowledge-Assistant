"""
Create embeddings for documents that don't have any yet (e.g. documents added
before semantic search existed, or inserted directly into the database).

Usage:
    python embed_existing_documents.py

Safe to re-run: documents that already have chunks are skipped.
"""

from db import pool, init_db
from search import build_chunks, save_chunks


def main():
    """Find documents with no chunks and create (embed) their chunks one document at a time."""
    # Only fetch documents that have no rows in document_chunks yet
    with pool.connection() as conn:
        documents = conn.execute(
            """
            SELECT id, name, content FROM documents d
            WHERE NOT EXISTS (SELECT 1 FROM document_chunks c WHERE c.document_id = d.id)
            ORDER BY id
            """
        ).fetchall()

    for doc in documents:
        # Embedding happens before taking a connection, so the slow model work doesn't
        # hold a database connection open. Each document is saved in its own transaction,
        # so if the script stops part way, the finished documents are kept.
        chunks = build_chunks(doc["content"])
        with pool.connection() as conn:
            save_chunks(conn, doc["id"], chunks)
        print(f"  {doc['name']}: {len(chunks)} chunks")

    print(f"Embedded {len(documents)} documents.")


if __name__ == "__main__":
    init_db()
    main()
