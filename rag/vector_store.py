"""Shared configuration and factories for Gemini embeddings and Chroma."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings


# Resolve the project root and load its environment variables.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"
DOCUMENTS_DIR = KNOWLEDGE_BASE_DIR / "documents"
VECTOR_STORE_DIR = KNOWLEDGE_BASE_DIR / "chroma_db"

COLLECTION_NAME = os.getenv(
    "RAG_COLLECTION_NAME", "ola_knowledge"
)

EMBEDDING_MODEL = os.getenv(
    "GOOGLE_EMBEDDING_MODEL", "gemini-embedding-001"
)


@lru_cache(maxsize=1)
def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """Create one reusable Gemini embedding client."""

    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is missing. "
            "Add it to the .env file in your project root."
        )

    return GoogleGenerativeAIEmbeddings(
        model=os.getenv(
            "GOOGLE_EMBEDDING_MODEL", EMBEDDING_MODEL
        ),
        google_api_key=api_key,
    )


@lru_cache(maxsize=1)
def get_vector_store() -> Chroma:
    """Open or create the persistent Chroma collection."""

    VECTOR_STORE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    return Chroma(
        collection_name=os.getenv(
            "RAG_COLLECTION_NAME", COLLECTION_NAME
        ),
        embedding_function=get_embeddings(),
        persist_directory=str(VECTOR_STORE_DIR),
    )