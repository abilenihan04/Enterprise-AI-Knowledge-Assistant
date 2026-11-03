"""
Create embeddings for documents that don't have any yet (e.g. documents added
before semantic search existed, or copied in by migrate_chroma_to_postgres.py).

Usage:
    python embed_existing_documents.py

Safe to re-run: documents that already have chunks are skipped.
"""

from app import build_chunks, save_chunks
from db import pool


def main():
    with pool.connection() as conn:
        documents = conn.execute(
            """
            SELECT id, name, content FROM documents d
            WHERE NOT EXISTS (SELECT 1 FROM document_chunks c WHERE c.document_id = d.id)
            ORDER BY id
            """
        ).fetchall()

    for doc in documents:
        chunks = build_chunks(doc["content"])
        with pool.connection() as conn:
            save_chunks(conn, doc["id"], chunks)
        print(f"  {doc['name']}: {len(chunks)} chunks")

    print(f"Embedded {len(documents)} documents.")


if __name__ == "__main__":
    main()
