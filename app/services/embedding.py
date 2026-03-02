"""
Embedding Service - Generates vector embeddings from text using Gemini text-embedding-004.

Produces 768-dimensional dense embeddings suitable for cosine similarity search in Milvus.
The model is trained on diverse multilingual text including geographical and travel content,
so it can distinguish semantically similar but geographically distinct locations
(e.g. "Kiri Vehera, Polonnaruwa" vs "Mihintale, Anuradhapura").

Uses the same google.genai SDK as the rest of the app (google-genai >= 1.0).
"""
import os
from typing import List

import google.genai as genai
from google.genai import types as genai_types

# Dimension of our embeddings (must match Milvus schema)
EMBEDDING_DIM = 768

_EMBED_MODEL = "models/gemini-embedding-001"


def _get_client() -> genai.Client:
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def generate_embedding(text: str) -> List[float]:
    """
    Generate a 768-dim document embedding using Gemini gemini-embedding-001.

    RETRIEVAL_DOCUMENT task type — optimised for indexing (upload time).
    outputDimensionality=768 truncates from the native 3072-dim output while
    preserving strong retrieval quality (Matryoshka Representation Learning).
    """
    client = _get_client()
    response = client.models.embed_content(
        model=_EMBED_MODEL,
        contents=text,
        config=genai_types.EmbedContentConfig(
            taskType="RETRIEVAL_DOCUMENT",
            outputDimensionality=EMBEDDING_DIM,
        ),
    )
    return response.embeddings[0].values


def generate_query_embedding(text: str) -> List[float]:
    """
    Generate a 768-dim query embedding using Gemini gemini-embedding-001.

    RETRIEVAL_QUERY task type — optimised for search queries (match time).
    Using the correct task type improves retrieval accuracy for asymmetric
    queries (short activity description searching longer image descriptions).
    """
    client = _get_client()
    response = client.models.embed_content(
        model=_EMBED_MODEL,
        contents=text,
        config=genai_types.EmbedContentConfig(
            taskType="RETRIEVAL_QUERY",
            outputDimensionality=EMBEDDING_DIM,
        ),
    )
    return response.embeddings[0].values
