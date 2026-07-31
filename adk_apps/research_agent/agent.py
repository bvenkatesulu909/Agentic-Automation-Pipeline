"""Research Agent — RAG reached over the MCP protocol, not a direct import.

This is the local counterpart of the "Research Agent" being built in Agent
Platform on `customer-report-12`: search the corpus first, ground every claim in
a citation, and be explicit about what the corpus does not cover.

    research_agent            SequentialAgent
    ├── retriever             LlmAgent + McpToolset   searches the corpus
    └── synthesiser           LlmAgent                writes the cited answer

The corpus is reached over **MCP**, not by importing `ragstack.retrieve`: ADK
spawns `ragstack serve` as a subprocess and talks JSON-RPC over stdio. Same
documents, entirely different integration path, and the one that generalises —
any MCP server attaches the same way, whoever wrote it and in whatever language.

Every app in this directory now shares a single toolset from
`ragstack_mcp_tool`, so there is one subprocess and one model load across the
whole server rather than one per app. The operational gotchas that toolset
encodes — the ~35s handshake that defeats ADK's 5s default, the environment the
MCP SDK declines to forward, and the write tool that is filtered out — are
documented there.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, SequentialAgent
from google.genai import types

# Shared across every app here: one subprocess, one model load. See the module
# docstring for why this is a singleton rather than a per-app toolset.
from ragstack_mcp_tool import RAGSTACK_MCP

load_dotenv(Path(__file__).parent / ".env", override=False)

# Provider chosen from the environment; Gemini via Vertex unless
# ADK_MODEL_PROVIDER=openrouter. See adk_apps/model_config.py.
from model_config import MODEL
_GEN = types.GenerateContentConfig(temperature=0.2, max_output_tokens=4096)

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
    tools=[RAGSTACK_MCP],
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
