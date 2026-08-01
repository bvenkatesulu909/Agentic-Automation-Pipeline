"""Deploy an ADK app in this directory to Vertex AI Agent Engine.

    .venv/Scripts/python.exe adk_apps/deploy_agent_engine.py sales_app

Agent Engine is the managed runtime for ADK: no cluster, no image, no pods. It
pickles the agent graph, installs `requirements` in a managed container, and
serves it behind a resource name. That removes the GKE control-plane fee and the
node bill, and removes the operational surface with them.

Two things about this runtime shape the code below, and both cost something real
if discovered after deploying rather than before.

**The MCP transport cannot come along.** `ragstack_mcp_tool` normally spawns
`ragstack serve` as a stdio subprocess. In a managed container there is no such
console script on PATH and nothing supervising a long-lived child across
invocations. So this script sets RAGSTACK_TRANSPORT=local *before* importing the
app, which swaps the toolset for the in-process `rag_search` — same corpus, same
embeddings, same return shape down to the `source` key the agent instructions
cite. Setting it afterwards would be too late: the toolset is chosen at import.

**Everything the agent closes over must pickle and must exist remotely.** The
corpus and the prebuilt index are not Python packages and would not be picked up
by dependency resolution, so they ship explicitly via `extra_packages`. If the
index is missing at run time the tool returns `no_index` rather than failing, so
a forgotten file degrades into agents that quietly cite nothing — which is why
this script refuses to deploy without one.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))

# Must precede the app import: the transport is resolved at module load.
os.environ["RAGSTACK_TRANSPORT"] = "local"
# Agent Engine runs the agent, so it needs the model provider that works there.
# Vertex needs no key; OpenRouter would need one plumbed through env_vars.
os.environ.setdefault("SALES_APP_PROVIDER", "vertex")
os.environ.setdefault("BILLING_APP_PROVIDER", "vertex")

import vertexai  # noqa: E402
from vertexai import agent_engines  # noqa: E402

PROJECT = os.environ.get("AE_PROJECT", "salesagent-504119")
LOCATION = os.environ.get("AE_LOCATION", "us-west1")
STAGING_BUCKET = os.environ.get("AE_STAGING_BUCKET", f"gs://{PROJECT}-agent-engine")

# Pinned to what the container actually needs to answer a request. Deliberately
# NOT the full `adk` extra: litellm is only for the OpenRouter path, which is not
# reachable from here, and it is a large tree.
REQUIREMENTS = [
    "google-adk>=2.5",
    "google-cloud-aiplatform[agent-engines]>=1.140",
    "requests>=2.31",
    "sentence-transformers>=3.0",
    "numpy>=1.26",
    "python-dotenv>=1.0",
    "pypdf>=4.0",
]


def main() -> int:
    app = sys.argv[1] if len(sys.argv) > 1 else "sales_app"

    index_dir = ROOT / ".ragstack_index"
    if not (index_dir / "vectors.npz").exists():
        print(
            f"No index at {index_dir}. Agent Engine cannot build one -- the docs\n"
            "are read at deploy time, not fetched at run time. Build it first:\n"
            "    .venv/Scripts/ragstack.exe index"
        )
        return 2

    root_agent = importlib.import_module(f"{app}.agent").root_agent

    # Fail here rather than remotely: if the transport swap did not take, the
    # deploy would succeed and every retrieval call would fail in production.
    from ragstack_mcp_tool import RAGSTACK_TOOLS

    if getattr(RAGSTACK_TOOLS, "__name__", None) != "rag_search":
        print(
            "RAGSTACK_TRANSPORT=local did not take -- the app still holds the MCP "
            "toolset, which cannot run on Agent Engine. Check that nothing "
            "imported ragstack_mcp_tool before this script set the variable."
        )
        return 2

    print(f"app        : {app}")
    print(f"project    : {PROJECT}")
    print(f"location   : {LOCATION}")
    print(f"staging    : {STAGING_BUCKET}")
    print(f"transport  : local (in-process rag_search)")
    print("deploying -- this takes several minutes ...", flush=True)

    vertexai.init(project=PROJECT, location=LOCATION, staging_bucket=STAGING_BUCKET)

    remote = agent_engines.create(
        agent_engine=root_agent,
        requirements=REQUIREMENTS,
        # The corpus and index are data, not packages: nothing in dependency
        # resolution would carry them, and the tool degrades quietly without
        # them rather than erroring.
        extra_packages=[
            str(ROOT / "src" / "ragstack"),
            str(ROOT / "docs"),
            str(index_dir),
            str(Path(__file__).parent / app),
            str(Path(__file__).parent / "ragstack_mcp_tool.py"),
            str(Path(__file__).parent / "model_config.py"),
        ],
        # GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, and GOOGLE_GENAI_USE_VERTEXAI
        # are deliberately absent: Agent Engine reserves them and rejects the
        # deployment outright if they appear here. The runtime injects its own,
        # pointing at the project and region it is deployed into, which is what
        # the agents want anyway.
        env_vars={
            "RAGSTACK_TRANSPORT": "local",
            # Relative, because extra_packages land beside the app in the managed
            # container rather than at any path this machine knows.
            "RAGSTACK_ROOT": ".",
            "GCP_QUOTA_PROJECT": PROJECT,
            "SALES_APP_PROVIDER": "vertex",
            "BILLING_APP_PROVIDER": "vertex",
        },
        display_name=f"{app} (ADK)",
        description=getattr(root_agent, "description", "") or app,
    )

    print("\ndeployed")
    print("resource_name:", remote.resource_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
