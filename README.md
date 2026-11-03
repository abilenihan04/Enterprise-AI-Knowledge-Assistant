# Enterprise-AI-Knowledge-Assistant
Final Year Project

## Database

Documents are stored in **PostgreSQL** with the `pgvector` extension, which stores the
embeddings used for natural language search in the same database. The app connects using the
`DATABASE_URL` setting and creates the tables on startup (see `schema.sql`).

You need one PostgreSQL database - either:

- **Hosted (for going live):** create a free PostgreSQL database on a provider that supports
  `pgvector` (e.g. [Neon](https://neon.tech) or [Supabase](https://supabase.com)) and copy its
  connection string; or
- **Local (for development):** with Docker installed, run `docker compose up -d`.

## Running locally

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # Windows: copy .env.example .env
# edit .env and set DATABASE_URL to your database's connection string
python app.py
```

Then open http://localhost:5000. The first start downloads the search model (~90 MB) and takes
a little longer.

On Linux servers, install the CPU-only PyTorch first to avoid a multi-GB GPU download:
`pip install torch --index-url https://download.pytorch.org/whl/cpu`.

## Natural language search

The **Ask a Question** page (`/search`, API `GET /query?q=...`) finds documents by meaning
rather than exact keywords. Each document is split into ~200-word chunks, and each chunk is
turned into an embedding by the open-source `all-MiniLM-L6-v2` model, which runs locally inside
the app, so document text is never sent to an external AI service. pgvector then returns the
chunks closest in meaning to the question (cosine similarity) and the app shows the best
match per document.

Embeddings are created automatically when a document is added or updated. For documents
that existed before search was added, run once:

```bash
python embed_existing_documents.py
```

## Moving existing documents from ChromaDB

The app previously stored documents in ChromaDB (`chroma_data_v2/`, an SQLite file). To copy
them into PostgreSQL once:

```bash
pip install chromadb==1.5.9
python migrate_chroma_to_postgres.py
```

Document names must be unique in PostgreSQL, so any duplicate names are renamed to
`<name> (<id>)` and printed. Then run `python embed_existing_documents.py` so they are
searchable. After checking the documents page, `chroma_data_v2/` can be deleted.

## Project structure

- `app.py` – Flask backend (routes)
- `db.py` – PostgreSQL connection pool and table creation
- `schema.sql` – `documents` and `document_chunks` table definitions
- `embeddings.py` – local embedding model and document chunking
- `templates/` – HTML pages rendered by Flask
- `embed_existing_documents.py` – creates embeddings for documents that don't have any
- `migrate_chroma_to_postgres.py` – one-off copy of old ChromaDB documents into PostgreSQL
- `docker-compose.yml` – local PostgreSQL for development
