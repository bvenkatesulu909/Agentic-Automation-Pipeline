"""Research Agent — RAG reached over the MCP protocol, not a direct import.

This is the local counterpart of the "Research Agent" being built in Agent
Platform on `customer-report-12`: search the corpus first, ground every claim in
a citation, and be explicit about what the corpus does not cover.

The distinction worth understanding: `incident_commander` also does RAG, but it
imports `ragstack.retrieve` and calls Python directly. This agent speaks **MCP**
to the same corpus — ADK spawns `ragstack.exe serve` as a subprocess and talks
JSON-RPC over stdio. Same documents, entirely different integration path, and the
one that generalises: any MCP server can be attached the same way, including ones
written by other people in other languages.

    research_agent            SequentialAgent
    ├── retriever             LlmAgent + McpToolset   searches the corpus
    └── synthesiser           LlmAgent                writes the cited answer

Two operational facts this file encodes, both learned the hard way:

* **The handshake takes ~35 seconds.** ragstack loads a sentence-transformers
  model before it answers `initialize`. ADK's `StdioConnectionParams` defaults to
  a 5-second timeout, so the default configuration fails 100% of the time.
* **`rag_reindex` is excluded.** The MCP server exposes it, and it rewrites the
  index on disk. A research agent has no business holding a write tool, so
  `tool_filter` allows only the three read operations.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.genai import types
from mcp import StdioServerParameters
from mcp.client.stdio import get_default_environment

load_dotenv(Path(__file__).parent / ".env", override=False)

MODEL = "gemini-2.5-flash"
_GEN = types.GenerateContentConfig(temperature=0.2, max_output_tokens=4096)

# On the Windows dev box ragstack lives in the venv's Scripts directory; in the
# container it is a console script already on PATH. Resolve rather than assume,
# so the same file works in both places.
_VENV_EXE = Path(__file__).resolve().parents[2] / ".venv" / "Scripts" / "ragstack.exe"
RAGSTACK_CMD = str(_VENV_EXE) if _VENV_EXE.exists() else "ragstack"

# The MCP SDK does NOT hand the parent process's environment to a stdio server —
# it builds a minimal safe one, so custom variables are silently dropped. That
# matters here: ragstack derives its corpus and index paths from RAGSTACK_ROOT,
# and without it the server falls back to a location relative to the installed
# package and reports an empty corpus. The failure is quiet, because an empty
# index is a valid answer rather than an error.
#
# Only forwarded when set, so the dev box (editable install, paths already
# correct) is unaffected.
_FORWARD = ("RAGSTACK_ROOT", "RAGSTACK_DOCS_DIR", "RAGSTACK_INDEX_DIR", "HF_HOME")
_env = get_default_environment()
_env.update({k: os.environ[k] for k in _FORWARD if os.environ.get(k)})

ragstack_mcp = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=RAGSTACK_CMD,
            args=["serve"],
            env=_env,
        ),
        # Measured at 34.8s for the embedding model to load before the server
        # answers `initialize`. The 5.0 default is not close to sufficient; this
        # leaves headroom for a cold filesystem cache.
        timeout=120.0,
    ),
    # rag_reindex is deliberately absent — it rewrites the index on disk.
    tool_filter=["rag_search", "rag_answer", "rag_index_status"],
)

retriever = LlmAgent(
    name="retriever",
    model=MODEL,
    description="Searches the document corpus over MCP and reports what it found.",
    instruction="""You retrieve evidence from the team's document corpus.

The corpus is reached over MCP. If you are unsure what is indexed, call
`rag_index_status` first — answering from an empty or unexpected corpus is worse
than saying it is empty.

Call `rag_search` at least twice with differently-worded queries. One phrasing
reliably misses passages another finds, and a single query is the most common
reason a correct answer is reported as "not in the corpus".

Report the passages you found, each with its `source` citation and similarity
score, and nothing else. Do not answer the user's question — the next agent does
that. Your job is evidence, and evidence you did not retrieve is not evidence.

If the corpus genuinely has nothing relevant, say so plainly and state which
queries you tried.""",
    tools=[ragstack_mcp],
    generate_content_config=_GEN,
    output_key="evidence",
)

synthesiser = LlmAgent(
    name="synthesiser",
    model=MODEL,
    description="Writes the final cited answer from retrieved evidence.",
    instruction="""Answer the user's question from the retrieved evidence.

Evidence:
{evidence}

Rules:
- **Every factual claim carries its citation**, in the form `source#chunkN` as it
  appears in the evidence. A sentence without one reads as corpus-backed when it
  is not.
- **Do not supplement from general knowledge.** If the corpus is silent, say so.
  This team's policies differ from industry defaults in specific ways, so a
  plausible-sounding general answer is actively misleading here.
- If the evidence is thin or conflicting, say that rather than presenting a
  confident synthesis over weak material.

Structure:

## Answer
The direct answer, cited.

## Supporting passages
The specific citations you relied on.

## Not covered by the corpus
What the question asked that the documents do not address. Leave this out only if
the corpus genuinely covered everything.""",
    generate_content_config=_GEN,
    output_key="research_answer",
)

root_agent = SequentialAgent(
    name="research_agent",
    description=(
        "Answers questions from the local document corpus, reached over the MCP "
        "protocol, with a citation on every claim."
    ),
    sub_agents=[retriever, synthesiser],
)
