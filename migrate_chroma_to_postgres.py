"""
One-off migration: copy documents from the old ChromaDB store (chroma_data_v2/,
which uses SQLite) into the PostgreSQL "documents" table.

Usage (chromadb is only needed for this script, not for the app):
    pip install chromadb==1.5.9
    python migrate_chroma_to_postgres.py

Safe to re-run: documents whose ID is already in PostgreSQL are skipped.
"""

from datetime import datetime

import chromadb

from db import pool, init_db

CHROMA_PATH = "./chroma_data_v2"
COLLECTION_NAME = "synthetic_docs_v2"


def parse_timestamp(value):
    # Old timestamps were saved without a timezone, in this computer's local time.
    return datetime.fromisoformat(value).astimezone() if value else None


def main():
    collection = chromadb.PersistentClient(path=CHROMA_PATH).get_collection(COLLECTION_NAME)
    results = collection.get(include=["documents", "metadatas"])
    init_db()

    inserted, skipped = 0, 0
    with pool.connection() as conn:
        taken_names = {row["name"] for row in conn.execute("SELECT name FROM documents")}
        existing_ids = {row["id"] for row in conn.execute("SELECT id FROM documents")}

        for doc_id, content, metadata in zip(results["ids"], results["documents"], results["metadatas"]):
            if doc_id in existing_ids:
                skipped += 1
                continue

            # Names must be unique in PostgreSQL; ChromaDB allowed duplicates.
            name = metadata.get("name") or doc_id
            if name in taken_names:
                print(f"  Duplicate name '{name}' for {doc_id} - renamed to '{name} ({doc_id})'")
                name = f"{name} ({doc_id})"
            taken_names.add(name)

            conn.execute(
                """
                INSERT INTO documents (id, name, category, confidentiality, source, content, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    doc_id,
                    name,
                    metadata.get("category") or "Uncategorized",
                    metadata.get("confidentiality") or "Internal",
                    metadata.get("source") or "Unknown",
                    (content or "").replace("\x00", ""),
                    parse_timestamp(metadata.get("created_at")),
                    parse_timestamp(metadata.get("updated_at")),
                ),
            )
            inserted += 1

    print(f"Migrated {inserted} documents ({skipped} already in PostgreSQL).")


if __name__ == "__main__":
    main()
