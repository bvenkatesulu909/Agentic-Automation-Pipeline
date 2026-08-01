"""One shared ragstack MCP toolset, used by every app in this directory.

Why a singleton rather than a toolset per app:

Each `McpToolset` spawns its own `ragstack serve` subprocess, and each of those
loads sentence-transformers — roughly 500 MB resident and ~35 seconds before it
answers `initialize`. Five apps in this directory now use it, so a toolset each
would mean five subprocesses, five model loads, and about 2.5 GB on top of the
parent process's torch. The pod's memory limit is 2500Mi, so that does not fit —
and the margin gets worse with every app added, which is the point.

Python caches modules, so every app that imports `RAGSTACK_MCP` from here shares
one toolset, one subprocess, and one model load.

This module lives beside the app packages rather than inside one of them: ADK's
loader treats *directories* under the agents dir as apps and ignores plain
modules, so a shared `.py` here is importable by all of them without being
mistaken for an app of its own.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from mcp import StdioServerParameters
from mcp.client.stdio import get_default_environment

# On the Windows dev box ragstack lives in the venv's Scripts directory; in the
# container it is a console script already on PATH.
_VENV_EXE = Path(__file__).resolve().parents[1] / ".venv" / "Scripts" / "ragstack.exe"
RAGSTACK_CMD = str(_VENV_EXE) if _VENV_EXE.exists() else "ragstack"

# The MCP SDK does NOT hand the parent's environment to a stdio server — it
# builds a minimal safe one, so custom variables are silently dropped. ragstack
# derives its corpus and index paths from RAGSTACK_ROOT; without it the server
# resolves them relative to the installed package and reports an empty corpus.
# That failure is quiet, because an empty index is a valid answer rather than an
# error. Only forwarded when set, so the dev box (editable install, paths already
# correct) is unaffected.
#
# The HF_* pair is here for the same reason and cost a real outage to find. The
# embedding model is baked into the image, but sentence-transformers still issues
# an update-check HEAD to huggingface.co when it loads one. On a cluster with
# private nodes and no Cloud NAT there is no route out, so that call hangs through
# five retries with backoff — about 120s — on every rag_search, and the agent run
# times out.
#
# The trap is that this process is not where the model loads. Setting
# HF_HUB_OFFLINE in the Dockerfile or the pod spec looks right and does nothing,
# because the SDK strips it before the subprocess starts. It has to be forwarded
# here or it does not exist where it matters.
_FORWARD = (
    "RAGSTACK_ROOT",
    "RAGSTACK_DOCS_DIR",
    "RAGSTACK_INDEX_DIR",
    "HF_HOME",
    "HF_HUB_OFFLINE",
    "HF_HUB_DISABLE_TELEMETRY",
)
_env = get_default_environment()
_env.update({k: os.environ[k] for k in _FORWARD if os.environ.get(k)})

def _mcp_toolset() -> McpToolset:
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=RAGSTACK_CMD,
                args=["serve"],
                env=_env,
            ),
            # Measured at ~35s for the embedding model to load before the server
            # answers `initialize`. ADK's 5.0 default fails every time.
            timeout=120.0,
        ),
        # rag_reindex is deliberately excluded — it rewrites the index on disk,
        # and none of these agents has any business holding a write tool.
        tool_filter=["rag_search", "rag_answer", "rag_index_status"],
    )


def rag_search(
    query: str, top_k: int = 5, source_filter: str = "", min_score: float = 0.0
) -> dict[str, Any]:
    """Search the indexed documents for passages relevant to a query.

    Args:
        query: What to search for. Natural language works better than keywords.
        top_k: How many passages to return.
        source_filter: Only match documents whose path contains this substring.
            Empty string searches the whole corpus.
        min_score: Cosine similarity floor, 0-1. 0 uses the configured default;
            lower it to widen a thin result set.

    Returns:
        The matching passages with their source paths and similarity scores.
    """
    # Imported here, not at module scope: this pulls in sentence-transformers and
    # torch, and the MCP path deliberately keeps them out of the parent process.
    from ragstack import config, retrieve
    from ragstack.store import VectorStore

    if not VectorStore.exists():
        return {
            "error": "no_index",
            "message": (
                f"No index found at {config.INDEX_DIR}. Build one with "
                f"`ragstack index` after putting documents in {config.DOCS_DIR}."
            ),
        }
    try:
        hits = retrieve.search(
            query,
            top_k=top_k,
            min_score=min_score or None,
            source_filter=source_filter or None,
        )
    except ValueError as exc:
        return {"error": "bad_request", "message": str(exc)}

    return {
        "query": query,
        "count": len(hits),
        "results": [
            {
                "rank": i,
                "score": round(hit.score, 4),
                "source": hit.citation(),
                "text": hit.text,
            }
            for i, hit in enumerate(hits, start=1)
        ],
    }


# Which transport the agents get. The default is unchanged, so GKE and the dev
# box behave exactly as before.
#
# **local** exists because Vertex AI Agent Engine cannot use the MCP one. That
# runtime pickles the agent graph and runs it in a managed container: there is no
# `ragstack` console script on PATH to exec, and no supervisor to keep a stdio
# subprocess alive across invocations. A toolset that shells out is therefore not
# portable to it, whatever the tooling claims.
#
# The two are deliberately answer-compatible — `rag_search` above returns the
# same dict as the MCP tool of the same name, keyed identically down to `source`,
# because every agent instruction in this repo tells the model to cite that
# field. A transport swap that quietly renamed it would degrade the citations
# rather than fail, which is the worst way for this to break.
#
# What local does NOT provide is `rag_answer` and `rag_index_status`. Nothing in
# sales_app calls either; incident_commander and research_agent do, so keep them
# on the MCP transport.
_TRANSPORT = os.environ.get("RAGSTACK_TRANSPORT", "mcp").strip().lower()

RAGSTACK_TOOLS: Any = rag_search if _TRANSPORT == "local" else _mcp_toolset()

# The name the five apps import. Kept as an alias rather than renamed at 20-odd
# call sites; `RAGSTACK_TOOLS` is the accurate name for new code, since under
# RAGSTACK_TRANSPORT=local there is no MCP involved at all.
RAGSTACK_MCP = RAGSTACK_TOOLS
