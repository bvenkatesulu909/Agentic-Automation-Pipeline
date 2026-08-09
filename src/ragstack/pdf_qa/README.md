# PDF Q&A with Citations

Production-grade RAG system for PDF question-answering with grounded citations. Combines semantic search, keyword matching, and cross-encoder reranking in a LangGraph orchestration pipeline.

## Architecture

```
PDF Input
    ↓
[PDFLoader] Extract text with page boundaries
    ↓
[DocumentChunker] Split into overlapping chunks, preserve page info
    ↓
[SQLiteVecStore] Store chunks + embeddings (semantic + keyword indices)
    ↓
Query Input
    ↓
[HybridRetriever] 
    ├─ Semantic search (SentenceTransformer embeddings)
    ├─ Keyword matching (TF-IDF-like scoring)
    └─ Reranking (CrossEncoder relevance)
    ↓
[Top-K Results with Citations]
    ↓
[AnswerGenerator] Generate answer via Claude with extended thinking
    ↓
[QAResponse] Answer + Source citations with page numbers
```

## Components

### PDFLoader
Extracts text from PDFs preserving page boundaries.

```python
from ragstack.pdf_qa import PDFLoader

doc = PDFLoader.load("document.pdf")
print(f"Loaded {doc.total_pages} pages")

# Batch load directory
docs = PDFLoader.batch_load("./pdfs/")
```

### DocumentChunker
Splits documents into overlapping chunks while preserving page-level metadata.

- Configurable chunk size and overlap
- Respects sentence boundaries where possible
- Tracks page numbers for each chunk
- Maintains chunk order and indices

```python
from ragstack.pdf_qa import DocumentChunker

chunker = DocumentChunker(chunk_size=512, chunk_overlap=100)
chunks = chunker.chunk(document)

for chunk in chunks:
    print(f"Pages {chunk.start_page}-{chunk.end_page}: {chunk.text[:50]}...")
```

### SQLiteVecStore
Vector store for chunk embeddings using SQLite with optional vec extension.

- Stores chunks with metadata (document ID, page numbers, index)
- Stores embeddings (vec type if extension available, fallback to BLOB)
- Similarity search via distance functions or manual cosine similarity
- Batch operations and pagination support

```python
from ragstack.pdf_qa import SQLiteVecStore

store = SQLiteVecStore(db_path="embeddings.db", embedding_dim=384)

# Add chunk
store.add_chunk(chunk)

# Add embedding
store.add_embedding(chunk.id, embedding_vector)

# Search
results = store.similarity_search(query_embedding, k=5)

# Retrieve chunk
chunk = store.get_chunk(chunk_id)

# All chunks for a document
all_chunks = store.get_all_chunks_for_document(doc_id)
```

### HybridRetriever
Combines multiple retrieval strategies with ranking.

**Retrieval Strategies:**
1. **Semantic Search**: Dense embeddings from SentenceTransformer
2. **Keyword Matching**: TF-IDF-like scoring based on query term frequency
3. **Reranking**: Cross-encoder (ms-marco-MiniLM) for final ranking

```python
from ragstack.pdf_qa import HybridRetriever

retriever = HybridRetriever(
    vector_store,
    embedding_model="all-MiniLM-L6-v2",
    rerank_model="cross-encoder/ms-marco-MiniLM-L-6-v2"
)

results = retriever.retrieve(
    query="What is machine learning?",
    k=5,
    use_semantic=True,
    use_keyword=True,
    use_rerank=True
)

for result in results:
    print(f"{result.citation}: {result.chunk.text[:50]}...")
    print(f"Score: {result.final_score:.3f}")
```

### AnswerGenerator
Generates answers using Claude with retrieved context.

- Uses extended thinking for reasoning (optional)
- Formats context with citations
- Supports custom system prompts
- Validates answers against source documents

```python
from ragstack.pdf_qa import AnswerGenerator

gen = AnswerGenerator(model="claude-3-5-sonnet-20241022")

response = gen.generate_answer(
    query="What is X?",
    retrieved_chunks=results,
    include_reasoning=True
)

print(response.answer)
print(response.citations_text)
```

### LangGraph Orchestration
End-to-end workflow coordinating all components.

```python
from ragstack.pdf_qa import create_qa_graph

graph = create_qa_graph(db_path="qa.db")

result = graph.process_query(
    query="What are the main findings?",
    pdf_path="document.pdf",
    retrieve_k=5,
    include_reasoning=True
)

print(result["formatted_response"])
print(result["response"].citations_text)
```

## Data Models

### Document
Represents a loaded PDF.

```python
@dataclass
class Document:
    id: str                    # Unique document ID
    path: str                  # File path
    name: str                  # Document name
    text: str                  # Full extracted text
    total_pages: int           # Number of pages
```

### Chunk
A piece of text with metadata.

```python
@dataclass
class Chunk:
    id: str                    # Unique chunk ID
    document_id: str           # Parent document
    text: str                  # Chunk text
    start_page: int            # First page in chunk
    end_page: int              # Last page in chunk
    chunk_index: int           # Position in document
    embedding: list[float]     # Embedding vector (optional)
```

### RetrievalResult
Retrieved chunk with relevance scores.

```python
@dataclass
class RetrievalResult:
    chunk: Chunk               # Retrieved chunk
    semantic_score: float      # Embedding similarity (0-1)
    rerank_score: float        # Cross-encoder score (0-1)
    keyword_score: float       # Keyword matching score (0-1)
    
    @property
    def final_score(self) -> float:
        # Combined weighted score
        
    @property
    def citation(self) -> str:
        # "Page X" or "Pages X-Y"
```

### QAResponse
Final response with citations.

```python
@dataclass
class QAResponse:
    question: str              # Original query
    answer: str                # Generated answer
    sources: list[RetrievalResult]  # Supporting chunks
    reasoning: str             # Extended thinking (optional)
    
    @property
    def citations_text(self) -> str:
        # Formatted citations with page numbers and scores
```

## Usage Examples

### Single PDF Query
```python
from ragstack.pdf_qa import create_qa_graph

graph = create_qa_graph(db_path="qa.db")
result = graph.process_query(
    query="What is the conclusion?",
    pdf_path="paper.pdf"
)
print(result["formatted_response"])
graph.close()
```

### Multiple PDF Directory
```python
graph = create_qa_graph(db_path="qa.db")
result = graph.process_query(
    query="Compare findings across documents",
    pdf_dir="./research_papers/",
    retrieve_k=10
)
print(result["formatted_response"])
graph.close()
```

### Manual Workflow Control
```python
from ragstack.pdf_qa import (
    PDFLoader, DocumentChunker, SQLiteVecStore,
    HybridRetriever, AnswerGenerator
)

# Load and chunk
doc = PDFLoader.load("document.pdf")
chunker = DocumentChunker()
chunks = chunker.chunk(doc)

# Index
store = SQLiteVecStore()
for chunk in chunks:
    store.add_chunk(chunk)
    embedding = embeddings_model.encode(chunk.text)
    store.add_embedding(chunk.id, embedding)

# Retrieve
retriever = HybridRetriever(store)
results = retriever.retrieve("Your question?", k=5)

# Generate answer
generator = AnswerGenerator()
response = generator.generate_answer("Your question?", results)

print(f"Answer: {response.answer}")
print(f"\nCitations:\n{response.citations_text}")
```

## Performance Considerations

### Chunk Size
- **512 tokens**: Good balance for most documents
- **256 tokens**: Higher precision, more chunks to store
- **1024 tokens**: Lower latency, less granular citations

### Overlap
- **100 tokens**: Default, good for context preservation
- **50 tokens**: Lower storage, some context loss
- **200 tokens**: Higher redundancy, better coverage

### Retrieval Parameters
- **k=5**: Fast, focused results
- **k=10**: Better coverage, slower ranking
- **Reranking**: +50% latency for significantly better results

### Embedding Models
- **all-MiniLM-L6-v2**: 384-dim, fast, good quality (default)
- **all-mpnet-base-v2**: 768-dim, slower, better quality
- **sentence-transformers/all-distilroberta-v1**: 768-dim, distilled

### Reranking Models
- **cross-encoder/ms-marco-MiniLM-L-6-v2**: Fast, good (default)
- **cross-encoder/mmarco-MiniLMv2-L12-H384-V1**: Multilingual
- **cross-encoder/ms-marco-TinyBERT-L-2-v2**: Smallest, fastest

## Integration with Existing Projects

### With MCP Server
```python
# In mcp_server.py
from ragstack.pdf_qa import create_qa_graph

qa_graph = create_qa_graph(db_path="data/qa.db")

@server.call_tool()
async def ask_pdf(query: str, pdf_path: str) -> str:
    result = qa_graph.process_query(query, pdf_path=pdf_path)
    return result["formatted_response"]
```

### With FastAPI
```python
from fastapi import FastAPI
from ragstack.pdf_qa import create_qa_graph

app = FastAPI()
qa_graph = create_qa_graph()

@app.post("/query")
async def query_pdf(query: str, pdf_path: str):
    result = qa_graph.process_query(query, pdf_path=pdf_path)
    return result["response"]
```

## Testing

Run the test suite:
```bash
pytest tests/test_pdf_qa.py -v
```

With coverage:
```bash
pytest tests/test_pdf_qa.py --cov=ragstack.pdf_qa
```

## Dependencies

- `anthropic`: Answer generation with extended thinking
- `langgraph`: Workflow orchestration
- `sentence-transformers`: Embeddings and reranking
- `sqlite-vec`: Optional vector search extension
- `pypdf`: PDF text extraction
- `numpy`: Vector operations

## Future Enhancements

- [ ] Async/await support for batch processing
- [ ] Query expansion with multi-hop reasoning
- [ ] Document summarization with citations
- [ ] Multi-language support
- [ ] Custom reranking strategies
- [ ] Streaming response generation
- [ ] Semantic caching
- [ ] Graph-based entity extraction
