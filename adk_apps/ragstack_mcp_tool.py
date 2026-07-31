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
_FORWARD = ("RAGSTACK_ROOT", "RAGSTACK_DOCS_DIR", "RAGSTACK_INDEX_DIR", "HF_HOME")
_env = get_default_environment()
_env.update({k: os.environ[k] for k in _FORWARD if os.environ.get(k)})

RAGSTACK_MCP = McpToolset(
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
    # rag_reindex is deliberately excluded — it rewrites the index on disk, and
    # none of these agents has any business holding a write tool.
    tool_filter=["rag_search", "rag_answer", "rag_index_status"],
)
