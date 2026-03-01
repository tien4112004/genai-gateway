from contextvars import ContextVar
from typing import Any, Dict, Optional

from langchain.tools import tool

from app.core.global_depends import Container

# Thread-safe storage for search filters
_filters_ctx: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "search_filters", default=None
)


def set_search_filters(filters: Optional[Dict[str, Any]] = None):
    """
    Set filters for document search in a thread-safe way.

    Args:
        filters: Dictionary with filter criteria (e.g., {"subject_code": "T", "grade": "5"})
    """
    _filters_ctx.set(filters)


def clear_search_filters():
    """Clear any active search filters for the current context."""
    _filters_ctx.set(None)


@tool
def search_mmr(query: str, k: int = 15) -> str:
    """
    Search for relevant educational documents and materials in the knowledge base.

    Use this tool to find accurate, fact-based information from the database
    to answer questions or create lesson content.

    The search can be filtered by metadata like subject and grade level.
    It retrieves multiple documents to ensure comprehensive coverage.

    Args:
        query: The topic or question to search for.
        k: Number of documents to retrieve (default: 10).

    Returns:
        A formatted string containing the content of relevant documents.
    """
    # Get repository from container
    document_embeddings_repository = Container.document_embeddings_repository()

    if document_embeddings_repository is None:
        return "Error: Knowledge base repository is not available."

    current_filters = _filters_ctx.get()

    # Build filter dict for PGVector metadata filtering
    filter_dict = None
    if current_filters:
        filter_dict = {}
        # Support both snake_case and camelCase or specific field names
        if current_filters.get("subject_code"):
            filter_dict["subject_code"] = current_filters["subject_code"]
        if current_filters.get("grade"):
            try:
                filter_dict["grade"] = int(current_filters["grade"])
            except (ValueError, TypeError):
                pass

    # Enforce reasonable k value
    k = max(min(k, 20), 5)

    # Perform similarity search with filters
    docs = document_embeddings_repository.mmr_search(
        query=query, k=k, filter=filter_dict if filter_dict else None
    )

    if not docs and filter_dict:
        docs = document_embeddings_repository.mmr_search(
            query=query, k=k, filter=None
        )

    if not docs:
        return "No relevant documents found in the knowledge base."

    result = []
    for i, doc in enumerate(docs, 1):
        result.append(f"--- Document {i} ---")
        result.append(f"Content: {doc.page_content}")
        if doc.metadata:
            # Only include useful metadata to save context tokens
            relevant_meta = {
                k: v
                for k, v in doc.metadata.items()
                if k in ["subject_name", "grade", "topic"]
            }
            if relevant_meta:
                result.append(f"Metadata: {relevant_meta}")
        result.append("")

    return "\n".join(result)


tools = [search_mmr]

__all__ = [
    "tools",
    "set_search_filters",
    "clear_search_filters",
    "search_mmr",
]
