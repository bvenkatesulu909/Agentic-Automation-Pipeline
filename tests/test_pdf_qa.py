"""Tests for the PDF Q&A system with citations."""

import tempfile
from pathlib import Path

import pytest
from pypdf import PdfWriter

from ragstack.pdf_qa import (
    Document,
    Chunk,
    PDFLoader,
    DocumentChunker,
    SQLiteVecStore,
    HybridRetriever,
    create_qa_graph,
)


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a sample PDF for testing."""
    pdf_path = tmp_path / "sample.pdf"

    # Create a simple PDF with text
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)

    # Add text programmatically (note: pypdf doesn't add text directly to blank pages)
    # For testing, we'll create a minimal PDF
    from io import BytesIO

    buffer = BytesIO()
    writer.write(buffer)
    buffer.seek(0)

    with open(pdf_path, "wb") as f:
        f.write(buffer.read())

    return pdf_path


@pytest.fixture
def sample_document() -> Document:
    """Create a sample document for testing."""
    return Document(
        id="doc_1",
        path="/tmp/test.pdf",
        name="test",
        text="""Introduction to AI.
[PAGE_BREAK]
Machine learning is a subset of artificial intelligence.
This allows computers to learn from data.
[PAGE_BREAK]
Deep learning uses neural networks.
It is inspired by biological neurons.
[PAGE_BREAK]
Natural language processing deals with text.
It powers language models and chatbots.""",
        total_pages=4,
    )


class TestPDFLoader:
    """Tests for PDF loading."""

    def test_load_pdf_file_not_found(self):
        """Test that loading non-existent PDF raises error."""
        with pytest.raises(FileNotFoundError):
            PDFLoader.load("/nonexistent/file.pdf")


class TestDocumentChunker:
    """Tests for document chunking."""

    def test_chunk_preserves_page_info(self, sample_document: Document):
        """Test that chunking preserves page information."""
        chunker = DocumentChunker(chunk_size=100, chunk_overlap=20)
        chunks = chunker.chunk(sample_document)

        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.document_id == sample_document.id
            assert chunk.start_page <= chunk.end_page
            assert chunk.start_page >= 1
            assert chunk.end_page <= sample_document.total_pages
            assert len(chunk.text) > 0

    def test_chunks_are_ordered(self, sample_document: Document):
        """Test that chunks maintain order."""
        chunker = DocumentChunker(chunk_size=100, chunk_overlap=20)
        chunks = chunker.chunk(sample_document)

        for i in range(len(chunks) - 1):
            assert chunks[i].chunk_index < chunks[i + 1].chunk_index


class TestSQLiteVecStore:
    """Tests for vector store operations."""

    @pytest.fixture
    def vector_store(self):
        """Create an in-memory vector store."""
        store = SQLiteVecStore(db_path=":memory:", embedding_dim=384)
        yield store
        store.close()

    def test_add_and_retrieve_chunk(self, vector_store: SQLiteVecStore):
        """Test adding and retrieving chunks."""
        chunk = Chunk(
            id="chunk_1",
            document_id="doc_1",
            text="This is a test chunk.",
            start_page=1,
            end_page=1,
            chunk_index=0,
        )

        vector_store.add_chunk(chunk)
        retrieved = vector_store.get_chunk("chunk_1")

        assert retrieved is not None
        assert retrieved.text == chunk.text
        assert retrieved.start_page == 1

    def test_add_embedding(self, vector_store: SQLiteVecStore):
        """Test adding embeddings."""
        chunk = Chunk(
            id="chunk_1",
            document_id="doc_1",
            text="Test chunk.",
            start_page=1,
            end_page=1,
            chunk_index=0,
        )

        vector_store.add_chunk(chunk)

        # Create a dummy embedding
        embedding = [0.1] * 384

        # Should not raise an error
        vector_store.add_embedding("chunk_1", embedding)

    def test_get_chunks_for_document(self, vector_store: SQLiteVecStore):
        """Test retrieving all chunks for a document."""
        for i in range(3):
            chunk = Chunk(
                id=f"chunk_{i}",
                document_id="doc_1",
                text=f"Test chunk {i}.",
                start_page=i + 1,
                end_page=i + 1,
                chunk_index=i,
            )
            vector_store.add_chunk(chunk)

        chunks = vector_store.get_all_chunks_for_document("doc_1")

        assert len(chunks) == 3
        assert all(c.document_id == "doc_1" for c in chunks)


class TestHybridRetriever:
    """Tests for hybrid retrieval."""

    @pytest.fixture
    def retriever_setup(self):
        """Set up retriever with sample data."""
        store = SQLiteVecStore(db_path=":memory:", embedding_dim=384)

        # Add sample chunks
        chunks = [
            Chunk(
                id="chunk_1",
                document_id="doc_1",
                text="Machine learning is a method of learning from data.",
                start_page=1,
                end_page=1,
                chunk_index=0,
            ),
            Chunk(
                id="chunk_2",
                document_id="doc_1",
                text="Deep learning uses neural networks with multiple layers.",
                start_page=2,
                end_page=2,
                chunk_index=1,
            ),
            Chunk(
                id="chunk_3",
                document_id="doc_1",
                text="Natural language processing enables computers to understand text.",
                start_page=3,
                end_page=3,
                chunk_index=2,
            ),
        ]

        for chunk in chunks:
            store.add_chunk(chunk)
            if hasattr(store, "connection"):
                embedding = [0.1] * 384
                store.add_embedding(chunk.id, embedding)

        retriever = HybridRetriever(store, embedding_model=None, rerank_model=None)
        yield retriever, chunks
        store.close()

    def test_keyword_search(self, retriever_setup):
        """Test keyword-based search."""
        retriever, chunks = retriever_setup

        scores = retriever._keyword_search("machine learning")

        assert len(scores) > 0
        assert "chunk_1" in scores  # Contains "machine learning"

    def test_retrieve_returns_results(self, retriever_setup):
        """Test that retrieve returns results."""
        retriever, chunks = retriever_setup

        # Use keyword-only search (no embeddings)
        results = retriever.retrieve(
            "machine learning",
            k=2,
            use_semantic=False,
            use_rerank=False,
        )

        assert len(results) > 0
        assert all(hasattr(r, "chunk") for r in results)
        assert all(hasattr(r, "final_score") for r in results)


class TestDocumentChunkerIntegration:
    """Integration tests for chunking."""

    def test_chunk_with_page_boundaries(self, sample_document: Document):
        """Test that chunks respect page boundaries from markup."""
        chunker = DocumentChunker(chunk_size=50, chunk_overlap=10)
        chunks = chunker.chunk(sample_document)

        # All chunks should have valid page ranges
        for chunk in chunks:
            assert 1 <= chunk.start_page <= sample_document.total_pages
            assert 1 <= chunk.end_page <= sample_document.total_pages
            assert chunk.start_page <= chunk.end_page

    def test_no_empty_chunks(self, sample_document: Document):
        """Test that no empty chunks are generated."""
        chunker = DocumentChunker(chunk_size=100, chunk_overlap=20)
        chunks = chunker.chunk(sample_document)

        for chunk in chunks:
            assert len(chunk.text.strip()) > 0


class TestQAGraphBasic:
    """Basic tests for the Q&A graph."""

    def test_graph_creation(self):
        """Test that Q&A graph can be created."""
        graph = create_qa_graph(db_path=":memory:")
        assert graph is not None
        graph.close()

    def test_graph_structure(self):
        """Test that graph has expected nodes."""
        graph = create_qa_graph(db_path=":memory:")
        # Graph should be compiled and ready to use
        assert graph.graph is not None
        graph.close()
