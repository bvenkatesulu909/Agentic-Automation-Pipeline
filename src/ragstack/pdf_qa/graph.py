"""LangGraph workflow for PDF Q&A with citations."""

from typing import Any

from langgraph.graph import StateGraph, START, END

from .chunking import DocumentChunker
from .llm_chain import AnswerGenerator
from .models import Document, QAResponse
from .pdf_loader import PDFLoader
from .retriever import HybridRetriever
from .vector_store import SQLiteVecStore


class QAGraphState:
    """State container for the Q&A workflow."""

    def __init__(self):
        self.query: str = ""
        self.documents: list[Document] = []
        self.retrieved_chunks: list[Any] = []
        self.response: QAResponse | None = None
        self.error: str | None = None


class PDFQAGraph:
    """LangGraph-based PDF Q&A orchestrator."""

    def __init__(self, db_path: str = ":memory:"):
        """Initialize Q&A graph.

        Args:
            db_path: Path to SQLite database
        """
        self.vector_store = SQLiteVecStore(db_path)
        self.chunker = DocumentChunker()
        self.retriever = HybridRetriever(self.vector_store)
        self.answer_gen = AnswerGenerator()
        self.graph = self._build_graph()

    def _build_graph(self):
        """Build the LangGraph workflow."""
        workflow = StateGraph(dict)

        # Define nodes
        workflow.add_node("load_documents", self._load_documents_node)
        workflow.add_node("index_documents", self._index_documents_node)
        workflow.add_node("retrieve", self._retrieve_node)
        workflow.add_node("generate_answer", self._generate_answer_node)
        workflow.add_node("format_response", self._format_response_node)

        # Define edges
        workflow.add_edge(START, "load_documents")
        workflow.add_edge("load_documents", "index_documents")
        workflow.add_edge("index_documents", "retrieve")
        workflow.add_edge("retrieve", "generate_answer")
        workflow.add_edge("generate_answer", "format_response")
        workflow.add_edge("format_response", END)

        return workflow.compile()

    def _load_documents_node(self, state: dict) -> dict:
        """Load PDF documents."""
        try:
            if "pdf_path" in state:
                doc = PDFLoader.load(state["pdf_path"])
                state["documents"] = [doc]
            elif "pdf_dir" in state:
                docs = PDFLoader.batch_load(state["pdf_dir"])
                state["documents"] = docs
            else:
                state["error"] = "No pdf_path or pdf_dir provided"
        except Exception as e:
            state["error"] = f"Failed to load documents: {str(e)}"

        return state

    def _index_documents_node(self, state: dict) -> dict:
        """Chunk and embed documents."""
        try:
            for doc in state.get("documents", []):
                chunks = self.chunker.chunk(doc)

                for chunk in chunks:
                    # Add chunk to vector store
                    self.vector_store.add_chunk(chunk)

                    # Generate embedding if embeddings model is available
                    if self.retriever.embeddings:
                        embedding = self.retriever.embeddings.encode(chunk.text, convert_to_list=True)
                        self.vector_store.add_embedding(chunk.id, embedding)

                state["indexed_count"] = state.get("indexed_count", 0) + len(chunks)
        except Exception as e:
            state["error"] = f"Failed to index documents: {str(e)}"

        return state

    def _retrieve_node(self, state: dict) -> dict:
        """Retrieve relevant chunks for the query."""
        try:
            query = state.get("query", "")
            if not query:
                state["error"] = "No query provided"
                return state

            k = state.get("retrieve_k", 5)
            results = self.retriever.retrieve(
                query,
                k=k,
                use_keyword=True,
                use_semantic=True,
                use_rerank=True,
            )
            state["retrieved_chunks"] = results
        except Exception as e:
            state["error"] = f"Failed to retrieve chunks: {str(e)}"

        return state

    def _generate_answer_node(self, state: dict) -> dict:
        """Generate answer from retrieved chunks."""
        try:
            query = state.get("query", "")
            chunks = state.get("retrieved_chunks", [])

            response = self.answer_gen.generate_answer(
                query,
                chunks,
                include_reasoning=state.get("include_reasoning", False),
            )
            state["response"] = response
        except Exception as e:
            state["error"] = f"Failed to generate answer: {str(e)}"

        return state

    def _format_response_node(self, state: dict) -> dict:
        """Format the final response."""
        if state.get("error"):
            state["formatted_response"] = f"Error: {state['error']}"
        else:
            response = state.get("response")
            if response:
                formatted = f"""Question: {response.question}

Answer: {response.answer}

Citations:
{response.citations_text}"""
                if response.reasoning:
                    formatted += f"\n\nReasoning:\n{response.reasoning}"
                state["formatted_response"] = formatted
            else:
                state["formatted_response"] = "No response generated"

        return state

    def process_query(
        self,
        query: str,
        pdf_path: str | None = None,
        pdf_dir: str | None = None,
        retrieve_k: int = 5,
        include_reasoning: bool = False,
    ) -> dict:
        """Process a query end-to-end.

        Args:
            query: Query text
            pdf_path: Path to single PDF
            pdf_dir: Path to directory of PDFs
            retrieve_k: Number of chunks to retrieve
            include_reasoning: Include reasoning in response

        Returns:
            Final state with response
        """
        initial_state = {
            "query": query,
            "pdf_path": pdf_path,
            "pdf_dir": pdf_dir,
            "retrieve_k": retrieve_k,
            "include_reasoning": include_reasoning,
            "documents": [],
            "retrieved_chunks": [],
            "response": None,
            "error": None,
        }

        return self.graph.invoke(initial_state)

    def close(self):
        """Clean up resources."""
        self.vector_store.close()


def create_qa_graph(db_path: str = ":memory:") -> PDFQAGraph:
    """Factory function to create a Q&A graph.

    Args:
        db_path: Path to SQLite database

    Returns:
        Initialized PDFQAGraph instance
    """
    return PDFQAGraph(db_path)
