# Enterprise-AI-Knowledge-Assistant
Final Year Project

## Running locally

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000.

## Project structure

- `app.py` – Flask backend
- `templates/` – HTML pages rendered by Flask
- `chroma_data_v2/` – ChromaDB database used by the app
