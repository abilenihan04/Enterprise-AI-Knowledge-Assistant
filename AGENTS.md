# Project notes

## Running
- `py app.py` (or the IDE Run button) -> http://127.0.0.1:5000
- `python` on PATH is the Microsoft Store stub; use `py` or `.venv\Scripts\python.exe`.
- `.venv` was created with `--system-site-packages`. All packages live in the system Python
  (`C:\Users\abiga\AppData\Local\Programs\Python\Python314`). Do NOT `pip install` torch into
  `.venv`: Windows Application Control blocks torch's DLL when it is loaded from inside OneDrive.
- `.env` holds `DATABASE_URL` (Neon PostgreSQL) and Ollama settings; it is git-ignored.
- `/answer` needs Ollama running (starts with Windows, or run `ollama serve`) with `qwen2.5:1.5b` pulled.

## Verification
- `py -m py_compile app.py db.py search.py answers.py embeddings.py`
- `py evaluate_search.py` for search accuracy.
- Jinja parses `{% %}` even inside HTML comments in templates - don't write template tags in comments.
