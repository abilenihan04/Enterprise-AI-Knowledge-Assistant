# Enterprise-AI-Knowledge-Assistant
Final Year Project

## Database

Documents are stored in **PostgreSQL** (with the `pgvector` extension, so embeddings can be
stored in the same database when semantic search is added). The app connects using the
`DATABASE_URL` setting and creates the `documents` table on startup (see `schema.sql`).

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

Then open http://localhost:5000.

## Moving existing documents from ChromaDB

The app previously stored documents in ChromaDB (`chroma_data_v2/`, an SQLite file). To copy
them into PostgreSQL once:

```bash
pip install chromadb==1.5.9
python migrate_chroma_to_postgres.py
```

Document names must be unique in PostgreSQL, so any duplicate names are renamed to
`<name> (<id>)` and printed. After checking the documents page, `chroma_data_v2/` can be deleted.

## Project structure

- `app.py` – Flask backend (routes)
- `db.py` – PostgreSQL connection pool and table creation
- `schema.sql` – `documents` table definition
- `templates/` – HTML pages rendered by Flask
- `migrate_chroma_to_postgres.py` – one-off copy of old ChromaDB documents into PostgreSQL
- `docker-compose.yml` – local PostgreSQL for development
