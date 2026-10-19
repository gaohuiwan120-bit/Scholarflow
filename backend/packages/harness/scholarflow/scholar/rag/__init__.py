"""ScholarFlow hybrid RAG over structured research artifacts."""

from scholarflow.scholar.rag.config import RagConfig
from scholarflow.scholar.rag.pipeline import index_artifacts_dir, rag_answer

__all__ = ["RagConfig", "index_artifacts_dir", "rag_answer"]


def __getattr__(name: str):
    if name == "retrieve_with_mcp_fallback":
        from scholarflow.scholar.rag.fallback import retrieve_with_mcp_fallback

        return retrieve_with_mcp_fallback
    if name == "verify_citations":
        from scholarflow.scholar.rag.citation import verify_citations

        return verify_citations
    raise AttributeError(name)
