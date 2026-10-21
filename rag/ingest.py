"""Load documents, split them into chunks, and index them in Chroma.

Run from the project root:
    uv run python -m rag.ingest
"""

import hashlib
from pathlib import Path
from typing import List

from langchain_community.document_loaders import (
    DirectoryLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .vector_store import (
    COLLECTION_NAME,
    DOCUMENTS_DIR,
    VECTOR_STORE_DIR,
    get_vector_store,
)


def load_documents() -> List[Document]:
    """Load supported files from the knowledge-base directory."""

    if not DOCUMENTS_DIR.is_dir():
        raise FileNotFoundError(
            f"Knowledge-base folder not found: {DOCUMENTS_DIR}\n"
            "Create knowledge_base/documents/ and add "
            "your .md, .txt, or .pdf files."
        )

    loaders = [
        DirectoryLoader(
            str(DOCUMENTS_DIR),
            glob="**/*.md",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
            show_progress=False,
            silent_errors=False,
        ),
        DirectoryLoader(
            str(DOCUMENTS_DIR),
            glob="**/*.txt",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
            show_progress=False,
            silent_errors=False,
        ),
        DirectoryLoader(
            str(DOCUMENTS_DIR),
            glob="**/*.pdf",
            loader_cls=PyPDFLoader,
            show_progress=False,
            silent_errors=False,
        ),
    ]

    documents: List[Document] = []

    for loader in loaders:
        documents.extend(loader.load())

    if not documents:
        raise RuntimeError(
            f"No .md, .txt, or .pdf files found in {DOCUMENTS_DIR}."
        )

    # Normalize source metadata for consistent citations.
    for document in documents:
        source = document.metadata.get("source")

        if source:
            document.metadata["source"] = str(
                Path(source).resolve()
            )

    return documents


def make_chunk_id(
    document: Document,
    chunk_index: int,
) -> str:
    """Create a reproducible ID for a chunk."""

    source = str(
        document.metadata.get("source", "unknown")
    )

    identity = (
        f"{source}|{chunk_index}|{document.page_content}"
    )

    return hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()


def ingest_documents() -> int:
    """Rebuild the Ola knowledge collection."""

    documents = load_documents()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        add_start_index=True,
    )

    chunks = splitter.split_documents(documents)

    if not chunks:
        raise RuntimeError(
            "Document loading succeeded, but no text chunks were created."
        )

    vector_store = get_vector_store()

    # Remove existing entries to prevent stale or duplicate chunks.
    existing = vector_store.get()
    old_ids = existing.get("ids", [])

    if old_ids:
        vector_store.delete(ids=old_ids)

    # Index the newly generated chunks.
    ids = [
        make_chunk_id(chunk, index)
        for index, chunk in enumerate(chunks)
    ]

    vector_store.add_documents(
        documents=chunks,
        ids=ids,
    )

    print("Ola RAG ingestion completed successfully.")
    print(f"Source documents: {len(documents)}")
    print(f"Text chunks indexed: {len(chunks)}")
    print(f"Chroma directory: {VECTOR_STORE_DIR}")
    print(f"Collection: {COLLECTION_NAME}")

    return len(chunks)


if __name__ == "__main__":
    ingest_documents()