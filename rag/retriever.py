"""Search Chroma and format context for the RAG agent."""

from pathlib import Path
from typing import List

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever

from .vector_store import get_vector_store


def get_retriever(
    k: int = 4,
) -> VectorStoreRetriever:
    """Return a retriever configured to return top-k chunks."""

    if k < 1:
        raise ValueError("k must be at least 1")

    return get_vector_store().as_retriever(
        search_type="similarity",
        search_kwargs={"k": k},
    )


def retrieve_documents(
    question: str,
    k: int = 4,
) -> List[Document]:
    """Return the most relevant chunks for a question."""

    question = question.strip()

    if not question:
        raise ValueError("Question cannot be empty")

    return get_retriever(k=k).invoke(question)


def retrieve_context(
    question: str,
    k: int = 4,
) -> str:
    """Return relevant text with source labels for the LLM."""

    documents = retrieve_documents(question, k=k)

    if not documents:
        return (
            "No relevant information was found "
            "in the Ola knowledge base."
        )

    sections = []

    for index, document in enumerate(documents, start=1):
        source_value = document.metadata.get(
            "source", "Unknown source"
        )

        source_name = (
            Path(str(source_value)).name
            if source_value
            else "Unknown source"
        )

        # PyPDFLoader normally uses zero-based page numbers.
        page = document.metadata.get("page")

        page_label = (
            f", page {int(page) + 1}"
            if isinstance(page, int)
            else ""
        )

        sections.append(
            f"[Source {index}: {source_name}{page_label}]\n"
            f"{document.page_content.strip()}"
        )

    return "\n\n---\n\n".join(sections)


if __name__ == "__main__":
    question = input(
        "Enter an Ola knowledge-base question: "
    ).strip()

    if question:
        try:
            print("\nRetrieved context:\n")
            print(retrieve_context(question))
        except Exception as exc:
            print(f"Retrieval failed: {exc}")