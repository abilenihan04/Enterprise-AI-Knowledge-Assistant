"""
Write a short answer to a question using only the most relevant document passages
(retrieval-augmented generation, RAG).

The answer is written by an open-source language model running locally in Ollama
(https://ollama.com), so document text is never sent to an external AI service.
The model is told to use only the passages it is given. Small models often cite the
wrong passage number, so instead the sources shown with the answer are the passages
whose meaning is closest to the answer (compared with the same embedding model used
for search), so every answer can be checked against its source documents.
"""

import json
import os
import re
import urllib.error
import urllib.request

from embeddings import embed

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")
SOURCES_FOR_ANSWER = 3
ANSWER_TIMEOUT_SECONDS = 180

# A passage counts as a source if the answer is at least this similar to it
SOURCE_SIMILARITY = 0.5

NOT_FOUND = "I couldn't find the answer to that in the documents."

INSTRUCTIONS = f"""You are an assistant that answers employees' questions using company documents.
Answer using ONLY the sources below. Do not use any other knowledge.
Keep the answer short: one to four sentences, or a short list of steps.
If the sources do not contain the answer, reply exactly: {NOT_FOUND}"""


class AnswerUnavailable(Exception):
    """Raised when the local language model can't be reached."""


def build_prompt(question, sources):
    passages = "\n\n".join(f"Document: {source['name']}\n{source['snippet']}" for source in sources)
    return f"Sources:\n\n{passages}\n\nQuestion: {question}"


def find_sources(answer, passages):
    """Return the passages the answer is based on: those closest in meaning to the answer."""
    vectors = embed([answer] + [p["snippet"] for p in passages])
    answer_vector = vectors[0]
    # Embeddings are normalised, so the dot product is the cosine similarity
    scores = [sum(a * b for a, b in zip(answer_vector, v)) for v in vectors[1:]]
    best = max(range(len(passages)), key=lambda i: scores[i])
    return [p for i, p in enumerate(passages) if scores[i] >= SOURCE_SIMILARITY or i == best]


def generate_answer(question, search_results):
    """
    Return {"answer": ..., "sources": [...]} for a question, given its search results.
    The sources are the documents the answer was based on.
    """
    sources = search_results[:SOURCES_FOR_ANSWER]
    if not sources:
        return {"answer": NOT_FOUND, "sources": []}

    request_body = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": build_prompt(question, sources)},
        ],
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": 0.1, "num_ctx": 4096, "num_predict": 300},
    }
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(request_body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=ANSWER_TIMEOUT_SECONDS) as response:
            reply = json.loads(response.read())
    except urllib.error.HTTPError as e:
        raise AnswerUnavailable(f"The answer model returned an error: {e.read().decode('utf-8', 'replace')}")
    except (urllib.error.URLError, OSError) as e:
        raise AnswerUnavailable(
            f"The answer model isn't available ({e}). Make sure Ollama is running and "
            f"the model is downloaded: ollama pull {OLLAMA_MODEL}"
        )

    # Remove any [1]-style citations the model added anyway
    answer = re.sub(r"\s*\[\d+\]", "", reply["message"]["content"]).strip()
    if NOT_FOUND.rstrip(".") in answer:
        return {"answer": NOT_FOUND, "sources": []}
    return {"answer": answer, "sources": find_sources(answer, sources)}
