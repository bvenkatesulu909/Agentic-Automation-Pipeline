"""Data models for PDF Q&A system."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Document:
    """A PDF document with metadata."""
    id: str
    path: str
    name: str
    text: str
    total_pages: int


@dataclass
class Chunk:
    """A chunk of text with document and page metadata."""
    id: str
    document_id: str
    text: str
    start_page: int
    end_page: int
    chunk_index: int
    embedding: Optional[list[float]] = None


@dataclass
class RetrievalResult:
    """A retrieved chunk with relevance score and citation info."""
    chunk: Chunk
    semantic_score: float
    rerank_score: Optional[float] = None
    keyword_score: Optional[float] = None

    @property
    def final_score(self) -> float:
        """Final score combining all signals."""
        scores = [self.semantic_score]
        if self.rerank_score is not None:
            scores.append(self.rerank_score)
        if self.keyword_score is not None:
            scores.append(self.keyword_score * 0.5)  # keyword score is secondary
        return sum(scores) / len(scores)

    @property
    def citation(self) -> str:
        """Formatted citation with page numbers."""
        if self.chunk.start_page == self.chunk.end_page:
            return f"Page {self.chunk.start_page}"
        return f"Pages {self.chunk.start_page}-{self.chunk.end_page}"


@dataclass
class QAResponse:
    """A response to a question with citations."""
    question: str
    answer: str
    sources: list[RetrievalResult] = field(default_factory=list)
    reasoning: Optional[str] = None

    @property
    def citations_text(self) -> str:
        """Formatted citations."""
        if not self.sources:
            return "No sources cited."
        citations = []
        for i, result in enumerate(self.sources, 1):
            citations.append(f"[{i}] {result.citation} (score: {result.final_score:.2f})")
        return "\n".join(citations)
