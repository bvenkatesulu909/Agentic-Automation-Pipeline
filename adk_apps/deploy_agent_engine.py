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
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).parent


def _stage(app: str) -> Path:
    """Assemble the exact directory layout the container will import from.

    This exists because of one line in the SDK: `_upload_extra_packages` calls
    `tar.add(file)` with no `arcname`, so each archive entry is named by exactly
    the path handed to it. Passing absolute paths — which is the natural thing to
    do from a script — puts `C:/Users/.../sales_app` in the tarball, which
    extracts in the container as `./Users/.../sales_app`. Nothing is then
    importable, the process dies before logging is configured, and the only
    signal is "failed to start and cannot serve traffic" after a build whose logs
    end in DONE.

    So: copy everything into one flat staging dir, chdir into it, and pass bare
    relative names. What lands in the container's working directory is then
    exactly what is listed here.
    """
    staging = Path(tempfile.mkdtemp(prefix="ae-stage-"))
    # src/ragstack -> ragstack/, so `import ragstack` resolves from the CWD.
    shutil.copytree(ROOT / "src" / "ragstack", staging / "ragstack")
    # The app package, minus local env files: sales_app/.env sets
    # GOOGLE_CLOUD_PROJECT, which Agent Engine reserves and injects itself.
    shutil.copytree(
        HERE / app, staging / app, ignore=shutil.ignore_patterns(".env", "__pycache__", ".adk")
    )
    shutil.copytree(ROOT / "docs", staging / "docs")
    shutil.copytree(ROOT / ".ragstack_index", staging / ".ragstack_index")

    # The embedding model weights, as a plain self-contained directory.
    #
    # Needed because nothing else puts them in the container. The GKE image bakes
    # them at build time; Agent Engine has no equivalent step, so
    # `sentence-transformers` is installed but its weights are not, and the first
    # rag_search fails inside the tool with OSError "Can't load the model" after
    # a download attempt that does not succeed.
    #
    # Saved via .save() rather than copying ~/.cache/huggingface: that cache is a
    # blobs+symlinks layout, and tarring symlinks across platforms is a second
    # failure waiting to happen. A saved directory is self-contained, so
    # RAGSTACK_EMBED_MODEL can point straight at it and the hub is never
    # consulted. Same weights as built the index, so the vectors stay comparable
    # — a different model here would return plausible nonsense rather than fail.
    from sentence_transformers import SentenceTransformer

    SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2").save(
        str(staging / "embed_model")
    )
    for mod in ("ragstack_mcp_tool.py", "model_config.py"):
        shutil.copy2(HERE / mod, staging / mod)
    return staging


def _verify_tar_layout(staging: Path, names: list[str]) -> list[str]:
    """Build the tarball the SDK would build and return its top-level entries.

    Cheap, and it is the check that would have caught the absolute-path bug
    before two fifteen-minute deploys rather than after.
    """
    with tempfile.TemporaryDirectory() as tmp:
        # str(), not Path: tarfile's stream mode calls .endswith() on the name.
        path = str(Path(tmp) / "check.tar.gz")
        cwd = os.getcwd()
        os.chdir(staging)
        try:
            with tarfile.open(path, mode="w|gz") as tar:
                for n in names:
                    tar.add(n)
            with tarfile.open(path) as tar:
                return sorted({m.name.split("/")[0] for m in tar.getmembers()})
        finally:
            os.chdir(cwd)

# Must precede the app import: the transport is resolved at module load.
os.environ["RAGSTACK_TRANSPORT"] = "local"
# Agent Engine runs the agent, so it needs the model provider that works there.
# Vertex needs no key; OpenRouter would need one plumbed through env_vars.
os.environ.setdefault("SALES_APP_PROVIDER", "vertex")
os.environ.setdefault("BILLING_APP_PROVIDER", "vertex")

import vertexai  # noqa: E402
from vertexai import agent_engines  # noqa: E402

PROJECT = os.environ.get("AE_PROJECT", "salesagent-504119")

# us-central1, and NOT us-west1 where the GKE cluster and registry live.
#
# Agent Engine is not available in every Vertex region, and it does not say so.
# `create` accepts the request, builds the container, pushes the image, and logs
# DONE — then the resource fails health checks with "failed to start and cannot
# serve traffic", which reads exactly like a broken application.
#
# Established by controlled test rather than inference: the same hello-world
# agent, same project, same service accounts, same code, changing only this
# value, fails in us-west1 and succeeds in us-central1. Check regional
# availability before moving this.
LOCATION = os.environ.get("AE_LOCATION", "us-central1")
# Must be in the same region as LOCATION.
STAGING_BUCKET = os.environ.get("AE_STAGING_BUCKET", f"gs://{PROJECT}-ae-usc1")

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

    staging = _stage(app)
    packages = [
        "ragstack",
        app,
        "ragstack_mcp_tool.py",
        "model_config.py",
        "docs",
        ".ragstack_index",
        "embed_model",
    ]

    top = _verify_tar_layout(staging, packages)
    print(f"staging    : {staging}")
    print(f"tar entries: {top}")
    missing = [p.split("/")[0] for p in packages if p.split("/")[0] not in top]
    if missing:
        print(f"tarball would not contain {missing} at its root — aborting.")
        return 2

    # Import from the staging layout so the pickle's module references match what
    # the container will actually have on disk.
    sys.path.insert(0, str(staging))
    os.chdir(staging)

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

    # Wrapped, not passed raw. Agent Engine serves whatever exposes a registered
    # query interface; a bare SequentialAgent has none, so the container builds
    # and pushes cleanly and then fails health checks with "failed to start and
    # cannot serve traffic" — a message that says nothing about the cause.
    # AdkApp is what adapts an ADK graph to that interface.
    app_obj = agent_engines.AdkApp(agent=root_agent, enable_tracing=True)

    ops = app_obj.register_operations()
    print(f"operations : {ops}")
    if not ops:
        print("AdkApp registered no operations — it would deploy and never serve.")
        return 2

    remote = agent_engines.create(
        agent_engine=app_obj,
        requirements=REQUIREMENTS,
        # Relative names, resolved against the staging dir we chdir'd into. See
        # _stage() for why absolute paths silently produce an unimportable
        # container. The corpus and index are in here because they are data, not
        # packages — nothing in dependency resolution would carry them, and the
        # tool returns `no_index` rather than failing without them.
        extra_packages=packages,
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
            # Load the weights shipped above instead of resolving the hub id.
            # Relative to the container's working directory.
            "RAGSTACK_EMBED_MODEL": "./embed_model",
            # Belt and braces: with the weights local, any hub lookup is a bug,
            # and offline mode turns a silent retry-and-hang into an immediate
            # error.
            "HF_HUB_OFFLINE": "1",
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
