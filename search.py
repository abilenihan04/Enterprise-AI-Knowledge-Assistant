"""
Indexing and searching documents.

Search is "hybrid": it combines two ways of finding matching chunks.
- Semantic search (pgvector): finds chunks whose meaning is closest to the question,
  even when they use different words.
- Keyword search (PostgreSQL full-text search): finds chunks that contain all of the
  question's words (in the text or the document name). This helps with exact terms
  such as codes, names and product names, which embeddings often miss.

The two ranked lists are merged with Reciprocal Rank Fusion (RRF): each chunk scores
1 / (RRF_K + rank) for every list it appears in, so chunks ranked highly by both win.
"""

from db import pool
from embeddings import split_into_chunks, embed, to_pgvector

MAX_SEARCH_RESULTS = 5
CANDIDATES_PER_METHOD = 50
RRF_K = 60

# Results below this similarity are hidden unless they contain every keyword in the question.
# Chosen by running evaluate_search.py --sweep.
MIN_SIMILARITY = 0.30


def build_chunks(content):
    """Split a document into chunks and create an embedding for each (runs locally)."""
    chunks = split_into_chunks(content)
    vectors = embed(chunks) if chunks else []
    # Each item is (chunk number, chunk text, vector as a pgvector string), ready for save_chunks()
    return [(i, chunk, to_pgvector(vector)) for i, (chunk, vector) in enumerate(zip(chunks, vectors))]


def save_chunks(conn, doc_id, chunks):
    """Replace a document's chunks in the document_chunks table."""
    # Delete the old chunks first so an updated document never keeps stale passages.
    # This runs on the caller's connection, so it is part of the same transaction as the
    # document insert/update: either everything is saved or nothing is.
    conn.execute("DELETE FROM document_chunks WHERE document_id = %s", (doc_id,))
    # executemany inserts all chunks in one batch instead of one round trip per chunk
    conn.cursor().executemany(
        """
        INSERT INTO document_chunks (document_id, chunk_index, content, embedding)
        VALUES (%s, %s, %s, %s::vector)
        """,
        [(doc_id, index, chunk, vector) for index, chunk, vector in chunks]
    )


SEARCH_SQL = """
WITH keywords AS (
    -- The question's words, stemmed, with stop words like "how" and "the" removed
    SELECT plainto_tsquery('english', %(question)s) AS query
),
semantic AS (
    -- The chunks closest in meaning to the question, ranked 1, 2, 3...
    -- (<=> is cosine distance: 0 = identical meaning)
    SELECT id, ROW_NUMBER() OVER (ORDER BY distance) AS rank
    FROM (
        SELECT c.id, c.embedding <=> %(vector)s::vector AS distance
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE %(category)s::text IS NULL OR d.category = %(category)s
        ORDER BY distance
        LIMIT %(candidates)s
    ) nearest
),
keyword AS (
    -- Chunks containing every keyword, in the chunk text or the document's name
    SELECT id, ROW_NUMBER() OVER (ORDER BY score DESC) AS rank
    FROM (
        SELECT c.id, ts_rank_cd(c.search_vector || setweight(to_tsvector('english', d.name), 'A'), k.query) AS score
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        CROSS JOIN keywords k
        WHERE %(use_keywords)s
          AND (c.search_vector || to_tsvector('english', d.name)) @@ k.query
          AND (%(category)s::text IS NULL OR d.category = %(category)s)
        ORDER BY score DESC
        LIMIT %(candidates)s
    ) matches
)
-- Merge both lists. FULL OUTER JOIN keeps chunks found by only one method; a chunk found
-- by both gets both RRF scores added together, so it rises to the top.
SELECT d.id, d.name, d.category, d.source, c.content AS snippet,
       1 - (c.embedding <=> %(vector)s::vector) AS similarity,
       kw.rank IS NOT NULL AS all_keywords_match,
       COALESCE(1.0 / (%(rrf_k)s + s.rank), 0) + COALESCE(1.0 / (%(rrf_k)s + kw.rank), 0) AS score
FROM semantic s
FULL OUTER JOIN keyword kw ON kw.id = s.id
JOIN document_chunks c ON c.id = COALESCE(s.id, kw.id)
JOIN documents d ON d.id = c.document_id
ORDER BY score DESC
"""


def is_relevant(result, min_similarity):
    """A result is shown if its meaning is close enough, or it contains every keyword in the question."""
    return result["similarity"] >= min_similarity or result["all_keywords_match"]


def search_documents(question, category=None, mode="hybrid",
                     limit=MAX_SEARCH_RESULTS, min_similarity=MIN_SIMILARITY):
    """
    Return the best-matching documents for a plain-English question.

    mode: "hybrid" (semantic + keyword) or "semantic" (meaning only, used for comparison).
    Each document appears once, using its best-scoring chunk as the snippet.
    """
    # Turn the question into a vector with the same model used for the documents,
    # so their meanings can be compared
    query_vector = to_pgvector(embed([question])[0])

    with pool.connection() as conn:
        # Let the HNSW index return more candidates than its default of 40
        conn.execute("SET LOCAL hnsw.ef_search = 200")
        rows = conn.execute(SEARCH_SQL, {
            "question": question,
            "vector": query_vector,
            "category": category or None,
            "use_keywords": mode == "hybrid",
            "candidates": CANDIDATES_PER_METHOD,
            "rrf_k": RRF_K,
        }).fetchall()

    # Group chunks by document. Rows arrive best score first, so the first chunk seen
    # for a document is its snippet; its similarity is the best of any of its chunks.
    documents = {}
    for row in rows:
        doc = documents.setdefault(row["id"], {
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "source": row["source"],
            "snippet": row["snippet"],
            "similarity": 0.0,
            "all_keywords_match": False,
        })
        doc["similarity"] = max(doc["similarity"], round(float(row["similarity"]), 3))
        doc["all_keywords_match"] = doc["all_keywords_match"] or row["all_keywords_match"]

    # Drop weak matches so the user (and the answer model) only see relevant documents
    results = [doc for doc in documents.values() if is_relevant(doc, min_similarity)]
    return results[:limit] if limit else results
