"""Example usage of the PDF Q&A system with citations."""

from pathlib import Path

from .chunking import DocumentChunker
from .graph import create_qa_graph
from .pdf_loader import PDFLoader
from .retriever import HybridRetriever
from .vector_store import SQLiteVecStore


def example_single_pdf():
    """Example: Query a single PDF file."""
    pdf_path = "/path/to/document.pdf"  # Replace with your PDF

    # Initialize the Q&A graph
    qa_graph = create_qa_graph(db_path="pdf_qa.db")

    try:
        # Process the query end-to-end
        result = qa_graph.process_query(
            query="What is the main topic of this document?",
            pdf_path=pdf_path,
            retrieve_k=5,
            include_reasoning=True,
        )

        # Print the formatted response
        print(result.get("formatted_response"))

        # Access structured response
        if result.get("response"):
            response = result["response"]
            print("\n--- Structured Response ---")
            print(f"Question: {response.question}")
            print(f"Answer: {response.answer}")
            print(f"\nCitations:\n{response.citations_text}")

    finally:
        qa_graph.close()


def example_document_directory():
    """Example: Query multiple PDFs from a directory."""
    pdf_dir = "/path/to/pdf/directory"  # Replace with your directory

    # Initialize the Q&A graph
    qa_graph = create_qa_graph(db_path="pdf_qa.db")

    try:
        # Process queries across all PDFs in the directory
        queries = [
            "What are the key findings?",
            "How does this relate to previous research?",
            "What are the limitations?",
        ]

        for query in queries:
            print(f"\n{'='*60}")
            print(f"Query: {query}")
            print(f"{'='*60}")

            result = qa_graph.process_query(
                query=query,
                pdf_dir=pdf_dir,
                retrieve_k=5,
            )

            print(result.get("formatted_response"))

    finally:
        qa_graph.close()


def example_manual_workflow():
    """Example: Step-by-step manual workflow for custom integration."""
    pdf_path = "/path/to/document.pdf"

    # Step 1: Load PDF
    print("Loading PDF...")
    document = PDFLoader.load(pdf_path)
    print(f"Loaded: {document.name} ({document.total_pages} pages)")

    # Step 2: Initialize vector store
    print("\nInitializing vector store...")
    vector_store = SQLiteVecStore(db_path="pdf_qa.db", embedding_dim=384)

    # Step 3: Chunk document
    print("Chunking document...")
    chunker = DocumentChunker(chunk_size=512, chunk_overlap=100)
    chunks = chunker.chunk(document)
    print(f"Created {len(chunks)} chunks")

    # Step 4: Index chunks
    print("Indexing chunks...")
    for chunk in chunks:
        vector_store.add_chunk(chunk)
        # Embeddings are generated during retrieval, but you could pre-compute here
        # embedding = embeddings_model.encode(chunk.text)
        # vector_store.add_embedding(chunk.id, embedding)

    # Step 5: Initialize retriever
    print("Initializing retriever...")
    retriever = HybridRetriever(
        vector_store,
        embedding_model="all-MiniLM-L6-v2",
        rerank_model="cross-encoder/ms-marco-MiniLM-L-6-v2",
    )

    # Step 6: Query
    query = "What is the main conclusion?"
    print(f"\nQuery: {query}")

    retrieved = retriever.retrieve(query, k=5, use_rerank=True)
    print(f"\nRetrieved {len(retrieved)} results:")

    for i, result in enumerate(retrieved, 1):
        print(f"\n[{i}] {result.citation}")
        print(f"    Score: {result.final_score:.3f}")
        print(f"    Text: {result.chunk.text[:100]}...")

    vector_store.close()


def example_batch_processing():
    """Example: Batch processing multiple documents and queries."""
    pdf_dir = "/path/to/pdf/directory"
    queries = ["What?", "Why?", "How?"]

    qa_graph = create_qa_graph(db_path="pdf_qa_batch.db")

    try:
        # Load all PDFs first
        print("Loading PDFs...")
        documents = PDFLoader.batch_load(pdf_dir)
        print(f"Loaded {len(documents)} documents")

        # Process each query
        results = {}
        for query in queries:
            print(f"\nProcessing: {query}")
            result = qa_graph.process_query(
                query=query,
                pdf_dir=pdf_dir,
                retrieve_k=3,
            )

            results[query] = result

        # Generate report
        print("\n" + "="*60)
        print("BATCH PROCESSING REPORT")
        print("="*60)

        for query, result in results.items():
            print(f"\nQuery: {query}")
            print(f"Status: {'Success' if not result.get('error') else 'Failed'}")
            if result.get("response"):
                print(f"Answer: {result['response'].answer[:200]}...")

    finally:
        qa_graph.close()


if __name__ == "__main__":
    print("PDF Q&A System Examples")
    print("="*60)
    print("\nAvailable examples:")
    print("1. example_single_pdf() - Query a single PDF")
    print("2. example_document_directory() - Query multiple PDFs")
    print("3. example_manual_workflow() - Step-by-step workflow")
    print("4. example_batch_processing() - Batch process multiple queries")
    print("\nNote: Update file paths before running examples")
