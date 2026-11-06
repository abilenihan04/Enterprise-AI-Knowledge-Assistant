"""
Local embeddings for semantic (natural language) search.

Uses the open-source all-MiniLM-L6-v2 model (Apache 2.0) via sentence-transformers.
The model runs inside this app, so document text is never sent to an external AI service.
It turns text into 384 numbers (a vector); texts with similar meaning get similar vectors.
"""

from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"

# The model only reads ~256 tokens at a time, so long documents are split into
# overlapping chunks of words and each chunk gets its own vector.
CHUNK_WORDS = 200
CHUNK_OVERLAP_WORDS = 40

# The loaded model is kept here so it is only loaded once per process (loading takes a few seconds).
_model = None


def get_model():
    """Load the model on first use (downloaded once, ~90 MB, then cached locally)."""
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def split_into_chunks(text):
    """Split text into overlapping chunks of CHUNK_WORDS words."""
    words = text.split()
    if not words:
        return []
    # Each chunk starts 160 words after the previous one, so neighbouring chunks share 40 words
    # and a sentence that falls on a boundary still appears whole in one of them.
    step = CHUNK_WORDS - CHUNK_OVERLAP_WORDS
    # Stop early enough that the last chunk isn't just the overlap of the one before it;
    # max(..., 1) makes sure short documents still produce one chunk.
    return [" ".join(words[i:i + CHUNK_WORDS]) for i in range(0, max(len(words) - CHUNK_OVERLAP_WORDS, 1), step)]


def embed(texts):
    """Return one 384-number vector (list of floats) per text."""
    # normalize_embeddings makes every vector length 1, so cosine similarity is just a dot product.
    # Texts are processed 64 at a time to keep memory use low for large documents.
    vectors = get_model().encode(texts, batch_size=64, normalize_embeddings=True)
    return [vector.tolist() for vector in vectors]


def to_pgvector(vector):
    """Format a vector the way pgvector expects it, e.g. '[0.12,-0.03,...]'."""
    return "[" + ",".join(str(x) for x in vector) + "]"
