# RAGStack — Production Agentic AI Platform

An end-to-end platform for building, evaluating, deploying and operating LLM agents in production. It started as a local RAG engine and grew module-by-module into a full stack: retrieval, multi-agent apps, human-in-the-loop approval, evaluation, cost-aware model routing, observability, async automation, and Kubernetes deployment with CI/CD.

**Stack:** Python · FastAPI · LangGraph · Google ADK · Anthropic Claude · OpenRouter/LiteLLM · Ollama · Celery · SQLite-vec · Qdrant · MCP · Prometheus · Grafana · Docker · Kubernetes · ArgoCD · GitHub Actions

---

## Architecture

```
            ┌──────────────── Clients / Dashboards / MCP hosts ────────────────┐
                                        │
                 FastAPI gateway  ·  Security guardrails  ·  Rate limiting
                                        │
   ┌──────────────┬──────────────┬──────┴───────┬──────────────┬──────────────┐
   │ RAG engine   │ Multi-agent  │ HITL         │ Model router │ Automation   │
   │ (ragstack)   │ apps (ADK)   │ (LangGraph)  │ (cost-aware) │ (Celery)     │
   └──────┬───────┴──────┬───────┴──────┬───────┴──────┬───────┴──────┬───────┘
          │              │              │              │              │
   Vector store     GCP / billing    Audit log     Claude / Ollama   Webhooks,
   (sqlite-vec,     / sales tools    + approvals   / OpenRouter      retries, DLQ
    Qdrant)
                                        │
             Eval harness · Prometheus metrics · Grafana · Alertmanager
                                        │
               Docker · Kubernetes (canary, overlays) · ArgoCD · GitHub Actions
```

## Feature modules

| Module | Path | What it does |
|---|---|---|
| **RAG engine** | `src/ragstack/` | Chunking, local embeddings, embedding cache, hybrid search + reranking, sqlite-vec and Qdrant stores, answers via Claude or a local Ollama model. CLI: `ragstack`. |
| **PDF Q&A with citations** | `src/ragstack/pdf_qa/` | Page-level citations over PDFs, LangGraph pipeline, CLI `pdf-qa` with interactive mode. |
| **MCP server** | `src/ragstack/mcp_server.py` | Exposes the document index as Model Context Protocol tools for Claude and other MCP hosts. |
| **Multi-agent apps** | `adk_apps/` | Google ADK agents: billing, FinOps commander, incident commander (GCP), research agent, sales/pricing agent. Deployable to Vertex AI Agent Engine. |
| **Human-in-the-loop** | `src/ragstack/hitl_*.py`, `src/langgraph_hitl_contrib/` | Uncertainty detection, approval gates, pause/resume from state snapshots, immutable audit trail, REST + WebSocket API. |
| **Evaluation harness** | `src/ragstack/eval/` | Golden test cases, evaluators, regression detection, pre-deploy gate, pytest plugin. CLI: `eval`. |
| **Cost-optimized model router** | `src/ragstack/router.py` | Scores query complexity (0–100), routes to cheap/medium/expensive tiers, budget limits, Prometheus spend metrics. |
| **Query router** | `src/llamaindex_query_router/` | Feature-based routing of queries to retrieval strategies. |
| **Tool tracer** | `src/crewai_tool_tracer/` | Sync/async tracing decorators and exporters for agent tool calls, with structured logging. |
| **Observability** | `src/observability/`, `prometheus.yml`, `alertmanager.yml` | Metrics, telemetry, middleware, alert rules, Grafana dashboards. |
| **Async automation pipeline** | `src/automation/` | FastAPI + Celery task execution with webhooks, exponential-backoff retries, idempotency keys and a dead-letter queue. |
| **Production inference** | `k8s/inference-server/` | vLLM on Kubernetes behind an ingress with autoscaling. |
| **CI/CD & delivery** | `.github/workflows/`, `k8s/`, `feature-flags/` | CI, security scanning, integration tests, deploy pipeline, ArgoCD, canary releases, feature-flag rollouts. |
| **Domain apps** | `tecoma_sales/`, `venki_news/`, `dashboard/` | A multi-agent sales desk for an industrial client, a live news desk, and a deal-desk dashboard built on the platform. |

## Quick start

```bash
git clone https://github.com/bvenkatesulu909/Agentic-Automation-Pipeline.git
cd Agentic-Automation-Pipeline
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # core RAG engine
pip install -e ".[adk]"            # optional: multi-agent apps
cp .env.example .env               # add your API keys

ragstack --help                    # index and query documents
pdf-qa ask "What is this about?" --pdf document.pdf
eval --help                        # run the evaluation harness
pytest                             # run the test suite
```

- Observability stack: `docker compose -f docker-compose.observability.yml up`
- Automation pipeline: `docker compose -f docker-compose.automation.yml up`

## Testing

350+ test functions across `tests/` and the module-level suites, run in CI on every push (`.github/workflows/ci.yml`).

## Detailed documentation

Each module has its own guide in the repository root, for example `QUICK_START.md`, `SYSTEM_ARCHITECTURE.md`, `HITL_README.md`, `ROUTER_GUIDE.md`, `EVAL_HARNESS_QUICKSTART.md`, `OBSERVABILITY_README.md`, `INFERENCE_SERVER_ARCHITECTURE.md`, `CI_CD_SETUP.md` and `TROUBLESHOOTING_GUIDE.md`.

## Author

**B. Venkatesulu** · [GitHub](https://github.com/bvenkatesulu909)
