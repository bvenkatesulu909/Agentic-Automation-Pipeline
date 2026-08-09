"""PDF Q&A with citations using LangGraph + SQLite-vec + cross-encoder."""

from .models import Document, Chunk, RetrievalResult, QAResponse
from .pdf_loader import PDFLoader
from .chunking import DocumentChunker
from .vector_store import SQLiteVecStore
from .retriever import HybridRetriever
from .llm_chain import AnswerGenerator
from .graph import create_qa_graph, PDFQAGraph

__all__ = [
    "Document",
    "Chunk",
    "RetrievalResult",
    "QAResponse",
    "PDFLoader",
    "DocumentChunker",
    "SQLiteVecStore",
    "HybridRetriever",
    "AnswerGenerator",
    "create_qa_graph",
    "PDFQAGraph",
]
