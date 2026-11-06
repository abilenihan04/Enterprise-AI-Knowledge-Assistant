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

The **Ask a Question** page (`/search`, API `GET /query?q=...&category=...`) finds documents
from a plain-English question. Each document is split into ~200-word chunks, and each chunk is
turned into an embedding by the open-source `all-MiniLM-L6-v2` model, which runs locally inside
the app, so document text is never sent to an external AI service.

Search is hybrid (see `search.py`):

- **Semantic search:** pgvector finds the chunks closest in meaning to the question (cosine similarity).
- **Keyword search:** PostgreSQL full-text search finds chunks containing every word of the
  question, in the text or the document name. This catches exact terms such as form codes,
  error numbers and product names, which embeddings often miss.
- The two ranked lists are merged with Reciprocal Rank Fusion, and the best match per
  document is shown.
- Results below a minimum similarity (`MIN_SIMILARITY`) are hidden unless they contain all
  the keywords, so unrelated documents are not shown just to fill the list.
- An optional category filter limits the search to one category.

Embeddings are created automatically when a document is added or updated. For documents
that existed before search was added, run once:

```bash
python embed_existing_documents.py
```

### Measuring search quality

`evaluation/test_questions.json` lists test questions with the document that should be found
(or none). `python evaluate_search.py` runs them and reports Top-1, Top-5, MRR and the share of
no-answer questions correctly returning nothing, for semantic-only and hybrid search.
`python evaluate_search.py --sweep` shows how the scores change with `MIN_SIMILARITY`.

## Written answers (local language model)

After the search results appear, the page asks `GET /answer?q=...&category=...` for a short
written answer. `answers.py` gives the top 3 search passages to an open-source language model
running locally in [Ollama](https://ollama.com). The model is told to answer only from those
passages and to say if it couldn't find the answer. The passages closest in meaning to the answer are shown as its sources. No document
text is sent to an external AI service.

Set up Ollama once:

1. Install Ollama from https://ollama.com/download (Windows, macOS or Linux).
2. Download the model: `ollama pull qwen2.5:1.5b` (~1 GB, Apache 2.0 licence).
3. Ollama runs in the background on `http://localhost:11434`. Change `OLLAMA_URL` / `OLLAMA_MODEL`
   in `.env` to use a different server or model.

On a CPU an answer takes roughly 10-45 seconds; the first answer after starting is slower
while the model loads. If Ollama isn't running, search still works and the answer box shows an error.

## Project structure

- `app.py` – Flask backend (routes)
- `db.py` – PostgreSQL connection pool and table creation
- `schema.sql` – `documents` and `document_chunks` table definitions
- `embeddings.py` – local embedding model and document chunking
- `search.py` – saving chunks and hybrid search
- `answers.py` – written answers from a local Ollama language model
- `templates/` – HTML pages rendered by Flask
- `embed_existing_documents.py` – creates embeddings for documents that don't have any
- `evaluate_search.py`, `evaluation/` – test questions and search quality measurement
- `docker-compose.yml` – local PostgreSQL for development
