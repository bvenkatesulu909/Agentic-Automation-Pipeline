# PDF Q&A System - Quick Start Guide

A production-grade RAG system for PDF question-answering with page-level citations.

## Setup

### 1. Install Dependencies

The required dependencies are already in `pyproject.toml`. Install the project:

```bash
pip install -e .
```

This installs:
- **LangGraph** — Orchestration framework
- **SQLite-vec** — Vector search
- **Sentence-Transformers** — Embeddings and cross-encoder reranking
- **Anthropic** — Claude API for answer generation
- **pypdf** — PDF text extraction

### 2. Verify Installation

```bash
python -c "from ragstack.pdf_qa import create_qa_graph; print('✓ Ready')"
```

## Quick Example (30 seconds)

```python
from ragstack.pdf_qa import create_qa_graph

# Create Q&A graph
qa_graph = create_qa_graph(db_path="qa.db")

# Query a PDF
result = qa_graph.process_query(
    query="What are the main conclusions?",
    pdf_path="research_paper.pdf",
    retrieve_k=5,
    include_reasoning=True
)

# Print formatted response with citations
print(result["formatted_response"])

# Access structured components
response = result["response"]
print(f"\nAnswer: {response.answer}")
print(f"\nPage Citations:\n{response.citations_text}")

qa_graph.close()
```

## System Components

### PDFLoader
Load PDFs with page tracking:

```python
from ragstack.pdf_qa import PDFLoader

doc = PDFLoader.load("document.pdf")
print(f"{doc.name}: {doc.total_pages} pages")

# Batch load
docs = PDFLoader.batch_load("./pdfs/")
```

### DocumentChunker
Split into overlapping chunks with page metadata:

```python
from ragstack.pdf_qa import DocumentChunker

chunker = DocumentChunker(chunk_size=512, chunk_overlap=100)
chunks = chunker.chunk(doc)

for chunk in chunks[:3]:
    print(f"Pages {chunk.start_page}-{chunk.end_page}: {len(chunk.text)} chars")
```

### SQLiteVecStore
Store and search embeddings:

```python
from ragstack.pdf_qa import SQLiteVecStore

store = SQLiteVecStore(db_path="embeddings.db", embedding_dim=384)

# Add chunks
for chunk in chunks:
    store.add_chunk(chunk)

# Add embeddings (if computed)
embeddings_model = SentenceTransformer("all-MiniLM-L6-v2")
for chunk in chunks:
    embedding = embeddings_model.encode(chunk.text)
    store.add_embedding(chunk.id, embedding)

# Search
results = store.similarity_search(query_embedding, k=5)
```

### HybridRetriever
Semantic + keyword search + reranking:

```python
from ragstack.pdf_qa import HybridRetriever

retriever = HybridRetriever(
    store,
    embedding_model="all-MiniLM-L6-v2",
    rerank_model="cross-encoder/ms-marco-MiniLM-L-6-v2"
)

# Retrieve with all strategies enabled
results = retriever.retrieve(
    query="What are the findings?",
    k=5,
    use_semantic=True,
    use_keyword=True,
    use_rerank=True
)

for result in results:
    print(f"{result.citation}: {result.final_score:.3f}")
```

### AnswerGenerator
Generate answers with Claude:

```python
from ragstack.pdf_qa import AnswerGenerator

generator = AnswerGenerator()

response = generator.generate_answer(
    query="What is X?",
    retrieved_chunks=results,
    include_reasoning=True  # Extended thinking
)

print(response.answer)
print(response.citations_text)
```

### LangGraph Orchestration
End-to-end workflow:

```python
from ragstack.pdf_qa import create_qa_graph

graph = create_qa_graph(db_path="qa.db")

# Single query
result = graph.process_query(
    query="Your question here",
    pdf_path="document.pdf",
    retrieve_k=5,
    include_reasoning=True
)

print(result["formatted_response"])

# Or use a directory of PDFs
result = graph.process_query(
    query="Compare across documents",
    pdf_dir="./research_papers/",
    retrieve_k=10
)

graph.close()
```

## Data Flow

```
Query
  ↓
HybridRetriever
  ├─ Semantic Search (embeddings)
  ├─ Keyword Matching (TF-IDF-like)
  └─ Reranking (CrossEncoder)
  ↓
Top-K Results with Page Citations
  ↓
AnswerGenerator
  ├─ Format context with citations
  ├─ Send to Claude with extended thinking
  └─ Return answer + reasoning
  ↓
QAResponse (answer + citations + reasoning)
```

## Performance Tips

### For Speed
```python
# Use smaller embedding model
retriever = HybridRetriever(
    store,
    embedding_model="all-MiniLM-L6-v2",  # Fast, good quality
    rerank_model=None  # Skip reranking
)

# Retrieve fewer results
results = retriever.retrieve(query, k=3, use_rerank=False)
```

### For Quality
```python
# Use larger models
retriever = HybridRetriever(
    store,
    embedding_model="all-mpnet-base-v2",  # 768-dim, better quality
    rerank_model="cross-encoder/ms-marco-MiniLM-L-6-v2"
)

# Retrieve more results
results = retriever.retrieve(query, k=10, use_rerank=True)

# Enable reasoning
response = generator.generate_answer(
    query,
    results,
    include_reasoning=True
)
```

## Testing

Run the test suite:

```bash
# All tests
pytest tests/test_pdf_qa.py -v

# Specific test class
pytest tests/test_pdf_qa.py::TestDocumentChunker -v

# With coverage
pytest tests/test_pdf_qa.py --cov=ragstack.pdf_qa
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'langgraph'"
Install dependencies:
```bash
pip install -e .
```

### "sqlite_vec extension not available"
This is OK—the system falls back to manual similarity computation. For production use, install:
```bash
pip install sqlite-vec
```

### "No relevant documents found"
- Check PDF was loaded correctly
- Verify chunks were created
- Try with fewer filters: `use_rerank=False`, `use_keyword=True`
- Increase `k` parameter

### Memory usage high
- Reduce `chunk_size` (default 512)
- Use smaller embedding model (all-MiniLM-L6-v2 vs all-mpnet-base-v2)
- Close graph when done: `graph.close()`

## Architecture Details

### Page Citation Tracking
- PDFLoader marks page breaks in extracted text
- DocumentChunker maps text positions to page numbers
- RetrievalResult tracks page range per chunk
- QAResponse formats citations with page numbers

### Hybrid Retrieval
1. **Semantic**: Dense embeddings from SentenceTransformer (best for semantic similarity)
2. **Keyword**: Term frequency in chunks (best for exact matches)
3. **Reranking**: CrossEncoder scores (best for relevance to query)
4. **Final Score**: Weighted combination of all signals

### Answer Generation
- Claude 3.5 Sonnet by default (configurable)
- Extended thinking for reasoning (optional)
- Context includes page citations
- Answers grounded in retrieved text

## File Structure

```
src/ragstack/pdf_qa/
├── __init__.py           # Public API exports
├── models.py             # Data structures (Document, Chunk, etc.)
├── pdf_loader.py         # PDF extraction with page tracking
├── chunking.py           # Document chunking with overlap
├── vector_store.py       # SQLite embeddings storage
├── retriever.py          # Hybrid search + reranking
├── llm_chain.py          # Claude answer generation
├── graph.py              # LangGraph orchestration
├── example.py            # Usage examples
├── QUICKSTART.md         # This file
└── README.md             # Full documentation
```

## Next Steps

1. **Read full docs**: See [README.md](README.md) for complete API reference
2. **Run examples**: Check [example.py](example.py) for more use cases
3. **Run tests**: `pytest tests/test_pdf_qa.py -v`
4. **Integrate**: Add to your application (see README.md integration section)

## API Reference (Cheat Sheet)

```python
# Loading
doc = PDFLoader.load("file.pdf")
docs = PDFLoader.batch_load("./pdfs/")

# Chunking
chunks = DocumentChunker(512, 100).chunk(doc)

# Storage
store = SQLiteVecStore("db.db", 384)
store.add_chunk(chunk)
store.add_embedding(chunk.id, embedding)

# Retrieval
retriever = HybridRetriever(store, "all-MiniLM-L6-v2", "cross-encoder/...")
results = retriever.retrieve(query, k=5)

# Generation
gen = AnswerGenerator("claude-3-5-sonnet-20241022")
response = gen.generate_answer(query, results, include_reasoning=True)

# End-to-end
graph = create_qa_graph("qa.db")
result = graph.process_query(query, pdf_path="file.pdf")
print(result["formatted_response"])
```

## License & Credits

Built with:
- LangGraph for orchestration
- Anthropic Claude for answer generation
- Sentence-Transformers for embeddings
- SQLite for vector storage
