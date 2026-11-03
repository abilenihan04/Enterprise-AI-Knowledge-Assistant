"""
Load the sample enterprise documents in sample_data/ into the database so search
can be tested and demonstrated with realistic company content.

The documents are synthetic: made-up policies for a fictional company, Brightwater
Solutions. Each sub-folder name is used as the document's category, and the first
"# " heading in each file is used as its name.

Usage:
    python load_sample_documents.py            # add them (skips names that already exist)
    python load_sample_documents.py --remove   # delete them again
"""

import sys
import uuid
from pathlib import Path

from db import pool, init_db
from search import build_chunks, save_chunks

SAMPLE_DIR = Path(__file__).parent / "sample_data"
SOURCE_PREFIX = "Sample data: "


def read_samples():
    for path in sorted(SAMPLE_DIR.glob("*/*.md")):
        content = path.read_text(encoding="utf-8").strip()
        name = content.splitlines()[0].lstrip("# ").strip()
        yield name, path.parent.name, f"{SOURCE_PREFIX}{path.name}", content


def load():
    added = 0
    for name, category, source, content in read_samples():
        with pool.connection() as conn:
            if conn.execute("SELECT 1 FROM documents WHERE name = %s", (name,)).fetchone():
                print(f"  skipped (already exists): {name}")
                continue
            doc_id = f"doc_{uuid.uuid4().hex[:6]}"
            conn.execute(
                """
                INSERT INTO documents (id, name, category, confidentiality, source, content)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (doc_id, name, category, "Internal", source, content)
            )
            save_chunks(conn, doc_id, build_chunks(content))
        print(f"  added: {name} ({category})")
        added += 1
    print(f"Added {added} sample documents.")


def remove():
    with pool.connection() as conn:
        deleted = conn.execute(
            "DELETE FROM documents WHERE source LIKE %s RETURNING name", (SOURCE_PREFIX + "%",)
        ).fetchall()
    print(f"Removed {len(deleted)} sample documents.")


if __name__ == "__main__":
    init_db()
    remove() if "--remove" in sys.argv else load()
