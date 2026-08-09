# Local RAG Development Environment

A complete offline RAG (Retrieval-Augmented Generation) system for development, testing, and experimentation. This environment mirrors production RAG capabilities using Ollama (local LLM) + LanceDB (embedded vector DB) + FastAPI.

## Why Local RAG?

### Advantages

| Aspect | Production | Local Dev |
|--------|-----------|-----------|
| **Cost** | $0.05 per query | Free (after setup) |
| **Latency** | 2-5 seconds | <1 second |
| **Internet** | Required | Offline |
| **Data Privacy** | Transmitted to API | Stays local |
| **Development Speed** | Slow iteration | Instant feedback |

### Use Cases

1. **RAG Pipeline Development**
   - Test retrieval strategies without API costs
   - Experiment with embeddings, chunking, ranking
   - Debug end-to-end flows

2. **Evaluation & Testing**
   - Run 1000+ test queries without Stripe charges
   - A/B test different retrieval methods
   - Stress test vector DB with large corpora

3. **Prototyping**
   - Offline demo to stakeholders
   - Test on airplane/unreliable internet
   - No API key needed

4. **Production Parity**
   - Catch issues before they hit production
   - Profile performance bottlenecks
   - Verify embedding quality

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│            Local RAG Development Stack                      │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  FastAPI (Port 8001)                                 │   │
│  │  - /api/documents/upload (PDF)                      │   │
│  │  - /api/query (ask question)                        │   │
│  │  - /api/search (semantic search)                    │   │
│  │  - /api/health                                       │   │
│  └──────────────────────────────────────────────────────┘   │
│                           ↓                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  LanceDB (Embedded Vector DB)                        │   │
│  │  - In-process (no server needed)                     │   │
│  │  - 384-dim embeddings                               │   │
│  │  - HNSW indexing for fast retrieval                │   │
│  └──────────────────────────────────────────────────────┘   │
│                           ↓                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Ollama (Local LLM Server on Port 11434)            │   │
│  │  - Mistral 7B (fast, accurate)                      │   │
│  │  - OR Llama2 13B (larger, slower)                  │   │
│  │  - Runs on CPU or GPU                              │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  Data stays local (disk + RAM)                             │
│  No external API calls                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Setup

### Prerequisites

- Python 3.10+
- 4GB RAM (minimum; 8GB recommended)
- Disk space: 10GB for Ollama models + documents

### 1. Install Ollama

**macOS**:
```bash
# Download from https://ollama.ai
# Or via Homebrew
brew install ollama

# Start Ollama (background)
ollama serve
# Listens on http://localhost:11434
```

**Linux**:
```bash
curl https://ollama.ai/install.sh | sh
systemctl start ollama
```

**Windows**:
```bash
# Download from https://ollama.ai/download
# Or via scoop
scoop install ollama

# Run from PowerShell
ollama serve
```

### 2. Pull a Model

```bash
# Mistral 7B (recommended: fast, accurate, 4GB)
ollama pull mistral

# Or Llama2 13B (larger, slower, 7GB)
ollama pull llama2

# Check available models
ollama list
# Output:
# NAME         SIZE     MODIFIED
# mistral:latest  4.1 GB  2 minutes ago
# llama2:latest   6.7 GB  1 hour ago
```

### 3. Clone local-rag-dev

```bash
cd /path/to/project

# local-rag-dev already exists
cd local-rag-dev

# Install dependencies
pip install -r requirements.txt
# Contains: fastapi, lancedb, pydantic, python-multipart, requests
```

### 4. Start FastAPI Server

```bash
# Terminal 1: Ollama (already running)
# Terminal 2: Start FastAPI
cd local-rag-dev
python -m uvicorn main:app --port 8001 --reload

# Output:
# Uvicorn running on http://127.0.0.1:8001
# Docs: http://127.0.0.1:8001/docs
```

### 5. Verify Setup

```bash
# Check Ollama
curl http://localhost:11434/api/tags
# Returns: { "models": [{ "name": "mistral:latest" }] }

# Check FastAPI
curl http://localhost:8001/health
# Returns: { "status": "ok" }
```

---

## Usage

### Upload a PDF

```bash
curl -X POST http://localhost:8001/api/documents/upload \
  -F "file=@document.pdf" \
  -F "name=warranty_guide"

# Response:
# {
#   "document_id": "doc_abc123",
#   "chunks": 47,
#   "name": "warranty_guide"
# }
```

**What happens behind the scenes**:
1. PDF loaded (pypdf)
2. Text extracted per page
3. Split into 1K-token chunks (with overlap)
4. Embedded via Ollama embedding model (384-dim vectors)
5. Stored in LanceDB with document metadata

### Query Documents

```bash
curl -X POST http://localhost:8001/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the warranty period?",
    "top_k": 5,
    "temperature": 0.7
  }'

# Response:
# {
#   "response": "The warranty period is 12 months from the purchase date, covering defects in materials and workmanship. Extended warranty options are available.",
#   "sources": [
#     {
#       "document": "warranty_guide",
#       "page": 3,
#       "chunk": "Section 3.2: Warranty Coverage",
#       "text": "Standard warranty: 12 months from purchase date..."
#     }
#   ],
#   "latency_ms": 850,
#   "model": "mistral:latest"
# }
```

### Semantic Search (No Generation)

```bash
curl -X POST http://localhost:8001/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "warranty coverage",
    "top_k": 3
  }'

# Response:
# {
#   "results": [
#     {
#       "rank": 1,
#       "similarity": 0.92,
#       "document": "warranty_guide",
#       "page": 3,
#       "text": "Standard warranty: 12 months from purchase..."
#     },
#     {
#       "rank": 2,
#       "similarity": 0.87,
#       "document": "warranty_guide",
#       "page": 5,
#       "text": "Extended warranty options add 24 months of..."
#     },
#     {
#       "rank": 3,
#       "similarity": 0.80,
#       "document": "terms_conditions",
#       "page": 1,
#       "text": "Warranty claims must be filed within..."
#     }
#   ],
#   "latency_ms": 120
# }
```

---

## Configuration

### Model Selection

**Fast queries (CPU-friendly)**:
```python
# In local-rag-dev/config.py
MODEL = "mistral:7b"  # ~7B params, 4GB, ~500ms per query
EMBEDDING_MODEL = "mistral:7b-instruct-q4"  # Quantized, fast
```

**Accurate queries (GPU recommended)**:
```python
MODEL = "llama2:13b"  # ~13B params, 7GB, ~2s per query
EMBEDDING_MODEL = "llama2:13b-chat-q8"  # Higher quality
```

### Chunk Size & Overlap

```python
# local-rag-dev/config.py

CHUNK_SIZE = 1024          # Tokens per chunk (default: 1K)
CHUNK_OVERLAP = 100        # Overlap for context (default: 100)
TOP_K = 5                  # Chunks to retrieve (default: 5)
TEMPERATURE = 0.7          # LLM creativity (0=deterministic, 1=random)
MAX_CONTEXT_TOKENS = 4000  # Max context in prompt
```

**Tuning advice**:
```python
# For short documents (FAQ, manual)
CHUNK_SIZE = 512           # Shorter chunks = more precise retrieval
TOP_K = 3

# For long documents (books, reports)
CHUNK_SIZE = 2048          # Longer chunks = more context
TOP_K = 5
CHUNK_OVERLAP = 200        # More overlap = better coherence
```

---

## Development Workflow

### 1. Load Reference Data

```bash
# Put PDFs in documents/ folder
ls local-rag-dev/documents/
# warranty_guide.pdf
# user_manual.pdf
# faq.txt

# Script to load all at startup
python local-rag-dev/load_documents.py
# Outputs: Loaded 3 documents, 150 total chunks
```

### 2. Write Test Cases

```python
# local-rag-dev/test_rag.py
import requests

BASE_URL = "http://localhost:8001"

def test_warranty_query():
    response = requests.post(
        f"{BASE_URL}/api/query",
        json={
            "query": "What is the warranty period?",
            "top_k": 3
        }
    )
    
    result = response.json()
    
    # Assertions
    assert "warranty" in result["response"].lower()
    assert len(result["sources"]) > 0
    assert "warranty_guide" in result["sources"][0]["document"]
    assert result["latency_ms"] < 2000  # Should be fast

def test_edge_case():
    response = requests.post(
        f"{BASE_URL}/api/query",
        json={
            "query": "How do I return an item?"
        }
    )
    
    result = response.json()
    # Verify retrieval got relevant chunks
    assert any("return" in s["text"].lower() for s in result["sources"])

# Run tests
# pytest test_rag.py -v
```

### 3. Iterate on Retrieval

```python
# Test different chunk sizes
for chunk_size in [512, 1024, 2048]:
    config.CHUNK_SIZE = chunk_size
    reload_documents()
    
    results = query("What is the warranty period?")
    
    print(f"Chunk size {chunk_size}:")
    print(f"  - Retrieval accuracy: {measure_accuracy(results)}")
    print(f"  - Latency: {results['latency_ms']}ms")
    print(f"  - Top-K relevant: {count_relevant(results)}/5")

# Pick best configuration
```

### 4. Compare with Production

```python
# local-rag-dev/compare_prod.py
import requests

queries = [
    "What is the warranty period?",
    "How do I contact support?",
    "What payment methods do you accept?",
    # ... 100+ test queries
]

results_local = []
results_prod = []

for query in queries:
    # Local
    r_local = requests.post(
        "http://localhost:8001/api/query",
        json={"query": query}
    )
    results_local.append(r_local.json())
    
    # Production
    r_prod = requests.post(
        "http://api.prod.example.com/api/query",
        json={"query": query},
        headers={"Authorization": "Bearer <token>"}
    )
    results_prod.append(r_prod.json())

# Compare
print(f"Local latency: {sum(r['latency_ms'] for r in results_local) / len(results_local)}ms")
print(f"Prod latency: {sum(r['latency_ms'] for r in results_prod) / len(results_prod)}ms")

# Check if responses are similar (semantic similarity)
for local, prod in zip(results_local, results_prod):
    similarity = semantic_similarity(local["response"], prod["response"])
    if similarity < 0.8:
        print(f"⚠️  Divergence: '{local['query']}'")
        print(f"  Local: {local['response'][:100]}...")
        print(f"  Prod:  {prod['response'][:100]}...")
```

---

## Performance Profiling

### Latency Breakdown

```python
# Instrument code to measure each step
import time

@app.post("/api/query")
def query_with_profiling(request: QueryRequest):
    t0 = time.time()
    
    # 1. Embed query
    t1 = time.time()
    query_embedding = embed(request.query)
    t_embed = time.time() - t1  # ~100ms
    
    # 2. Search LanceDB
    t2 = time.time()
    chunks = lancedb.search(query_embedding, top_k=5)
    t_search = time.time() - t2  # ~10ms
    
    # 3. Prepare prompt
    t3 = time.time()
    prompt = build_prompt(request.query, chunks)
    t_prompt = time.time() - t3  # ~5ms
    
    # 4. Invoke Ollama
    t4 = time.time()
    response = ollama.generate(model=MODEL, prompt=prompt)
    t_ollama = time.time() - t4  # ~700ms (most expensive)
    
    total_time = time.time() - t0
    
    return {
        "response": response,
        "latency_ms": int(total_time * 1000),
        "breakdown": {
            "embed": int(t_embed * 1000),      # 100ms
            "search": int(t_search * 1000),    # 10ms
            "prompt": int(t_prompt * 1000),    # 5ms
            "llm": int(t_ollama * 1000)        # 700ms
        }
    }

# Output:
# latency_ms: 815
# breakdown:
#   - embed: 100ms (12%)
#   - search: 10ms (1%)
#   - prompt: 5ms (1%)
#   - llm: 700ms (86%)  ← BOTTLENECK
```

**Optimization**: LLM is bottleneck. Switch to faster model.

### Memory Usage

```bash
# Monitor RAM usage during inference
watch -n 0.1 'ps aux | grep ollama | grep -v grep'

# Before query: 2.5GB (Ollama + models loaded)
# During query: 3.2GB (+700MB for generation)
# After query: 2.5GB (memory freed)

# If running out of memory:
# 1. Use quantized model (7B-q4 vs. 7B-q8)
# 2. Reduce chunk overlap (fewer vectors in RAM)
# 3. Decrease max_context_tokens
```

---

## Evaluation & Benchmarking

### Evaluate Retrieval Quality

```python
# local-rag-dev/eval_retrieval.py
from typing import List

class RetrievalEvaluator:
    def __init__(self, reference_data):
        """reference_data: List of (query, relevant_chunks)"""
        self.data = reference_data
    
    def evaluate(self, retriever):
        """Measure precision, recall, MRR"""
        results = []
        
        for query, expected_chunks in self.data:
            retrieved = retriever.search(query, top_k=5)
            
            # Precision: How many retrieved chunks are relevant?
            relevant = sum(1 for r in retrieved if r in expected_chunks)
            precision = relevant / len(retrieved)
            
            # Recall: How many expected chunks did we retrieve?
            recall = relevant / len(expected_chunks) if expected_chunks else 1.0
            
            # MRR (Mean Reciprocal Rank): Is the first result relevant?
            rank_of_first_relevant = next(
                (i+1 for i, r in enumerate(retrieved) if r in expected_chunks),
                float('inf')
            )
            mrr = 1.0 / rank_of_first_relevant if rank_of_first_relevant != float('inf') else 0
            
            results.append({
                "query": query,
                "precision": precision,
                "recall": recall,
                "mrr": mrr
            })
        
        # Aggregate
        avg_precision = sum(r["precision"] for r in results) / len(results)
        avg_recall = sum(r["recall"] for r in results) / len(results)
        avg_mrr = sum(r["mrr"] for r in results) / len(results)
        
        return {
            "precision@5": avg_precision,
            "recall@5": avg_recall,
            "mrr": avg_mrr,
            "results": results
        }

# Usage
evaluator = RetrievalEvaluator(reference_data)
metrics = evaluator.evaluate(lancedb_retriever)

print(f"Precision@5: {metrics['precision@5']:.2f}")
print(f"Recall@5: {metrics['recall@5']:.2f}")
print(f"MRR: {metrics['mrr']:.2f}")
```

### Evaluate Generation Quality

```python
# local-rag-dev/eval_generation.py
from rouge_score import rouge_scorer
from sentence_transformers import util
import torch

class GenerationEvaluator:
    def __init__(self):
        self.rouge = rouge_scorer.RougeScorer(['rouge1', 'rougeL'])
        self.semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
    
    def evaluate(self, generated, reference):
        """Compare generated response to reference"""
        # ROUGE: Word overlap
        rouge_scores = self.rouge.score(reference, generated)
        
        # Semantic similarity: Are they saying the same thing?
        gen_embedding = self.semantic_model.encode(generated)
        ref_embedding = self.semantic_model.encode(reference)
        similarity = util.pytorch_cos_sim(gen_embedding, ref_embedding)
        
        return {
            "rouge1": rouge_scores['rouge1'].fmeasure,
            "rougeL": rouge_scores['rougeL'].fmeasure,
            "semantic_similarity": float(similarity)
        }

# Test
evaluator = GenerationEvaluator()

test_cases = [
    {
        "query": "What is the warranty period?",
        "generated": "The warranty covers 12 months from purchase.",
        "reference": "The standard warranty is 12 months from the date of purchase."
    }
]

for case in test_cases:
    scores = evaluator.evaluate(case["generated"], case["reference"])
    print(f"Query: {case['query']}")
    print(f"  ROUGE-1: {scores['rouge1']:.2f}")
    print(f"  ROUGE-L: {scores['rougeL']:.2f}")
    print(f"  Semantic similarity: {scores['semantic_similarity']:.2f}")
```

---

## Deployment to Production

### Export Configuration

```bash
# Once you've tuned everything locally, export it
cat > prod_config.json << EOF
{
  "chunk_size": 1024,
  "chunk_overlap": 100,
  "top_k": 5,
  "temperature": 0.7,
  "embedding_model": "claude-3-5-sonnet",
  "llm_model": "claude-3-5-sonnet",
  "vector_db": "qdrant",
  "retrieval_strategy": "semantic_search_with_ranking"
}
EOF
```

### Update RAG Pipeline

```python
# src/ragstack/pdf_qa/config.py

# Load tuned parameters from local-rag-dev
config = load_config("prod_config.json")

CHUNK_SIZE = config["chunk_size"]
CHUNK_OVERLAP = config["chunk_overlap"]
TOP_K = config["top_k"]
TEMPERATURE = config["temperature"]
```

### Run Evaluation on Production

```bash
# Use same test suite that passed locally
pytest tests/test_rag_production.py --config prod_config.json

# Verify parity
# - Local accuracy: 92%
# - Prod accuracy: 91% (acceptable margin)
# - Local latency: 800ms
# - Prod latency: 1200ms (API overhead acceptable)
```

---

## Troubleshooting Local RAG

### Issue: Ollama connection refused

```bash
# Check if Ollama is running
ps aux | grep ollama
# Not running?

ollama serve
# Should output: Listening on 127.0.0.1:11434
```

### Issue: Model not found

```bash
# Pull model first
ollama pull mistral
# Or
ollama pull llama2

# Verify
ollama list
```

### Issue: Slow queries

```bash
# Profile latency breakdown (see above)
# LLM is the bottleneck? Use faster model:
# mistral:7b (500ms) instead of llama2:13b (2000ms)

# Retrieval is slow? Check LanceDB index:
# - Rebuild index: lancedb.reindex()
# - Verify chunk_size is reasonable
```

### Issue: Poor retrieval quality

```bash
# Experiment with:
# 1. Chunk size: smaller = more precise, larger = more context
# 2. Overlap: more = better coherence, less = faster
# 3. Top-K: more = better recall, less = better latency

# Use eval_retrieval.py to measure precision/recall
# - If precision low: chunks include junk → smaller chunks
# - If recall low: missing relevant chunks → larger chunks or more overlap
```

---

## Integration with Production RAG

### Local Development Flow

```
1. Write code locally (using Ollama)
   ↓ Fast iteration (instant feedback)
   ↓
2. Run tests locally (100% passing)
   ↓ No API costs
   ↓
3. Push to GitHub
   ↓
4. GitHub Actions runs tests (uses production Claude)
   ↓ Catches any model-specific issues
   ↓
5. Deploy to production
   ↓ High confidence (tested locally + CI)
```

### Cost Savings

```
Scenario: Develop RAG feature over 2 weeks

Without local RAG (direct to production):
  - 5,000 test queries at $0.001/query = $5
  - 2,000 iteration queries at $0.001/query = $2
  - Total: $7 + time waiting for API responses

With local RAG:
  - Setup: 5 min (one-time)
  - 7,000 test/iteration queries = $0 (Ollama is free)
  - 10x faster iteration (no network latency)
  - Saved: $7 + development time

Scale to 10 engineers, monthly:
  - Savings: $700/month + productivity gains
```

---

## Next Steps

1. **Set up local RAG** (30 minutes)
   - Install Ollama
   - Pull a model
   - Start FastAPI

2. **Load sample documents** (10 minutes)
   - Add PDFs to `documents/` folder
   - Run `load_documents.py`

3. **Write evaluation tests** (1 hour)
   - Create reference data
   - Measure precision/recall
   - Iterate on chunking

4. **Profile and optimize** (2 hours)
   - Measure latency breakdown
   - Tune chunk size, overlap, top-k
   - Compare with production

5. **Document your findings** (30 minutes)
   - Share optimal config
   - Document edge cases
   - Update prod config

