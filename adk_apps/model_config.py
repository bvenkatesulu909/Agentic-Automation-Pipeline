"""Chooses which LLM the agents run on, from the environment.

Two providers are supported and the default is unchanged, so nothing switches
without being asked to:

* **vertex** (default) — Gemini through Vertex AI using the pod's Workload
  Identity credentials. No key material anywhere.
* **openrouter** — any OpenRouter model, via ADK's LiteLLM bridge. Needs
  `OPENROUTER_API_KEY` in the environment; in the cluster that comes from a
  Kubernetes Secret, never from this file or the image.

Set `ADK_MODEL_PROVIDER=openrouter` and optionally `OPENROUTER_MODEL` to switch.

An app that wants a *different* default from its neighbours passes its own
environment variable names to `get_model`, rather than reading the shared ones.
`billing_app` and `sales_app` both do this: each is pinned to
OpenRouter/`tencent/hy3` and reads its own `<APP>_PROVIDER` / `<APP>_MODEL` pair,
so the cluster-wide `ADK_MODEL_PROVIDER=vertex` that keeps the other apps on
Gemini does not drag those two back to Gemini too.

A caveat that matters more than it looks: these are **tool-calling multi-agent**
systems. A single `finops_commander` run makes 10-15 model calls, most of which
must emit well-formed function calls. Free OpenRouter models vary widely in how
reliably they do that, and free-tier accounts are rate limited per minute and per
day — a limit a multi-agent run can exhaust on its own. Gemini remains the
default for that reason, not preference.
"""

from __future__ import annotations

import os
from typing import Any

# tencent/hy3: 262k context and — the requirement that actually matters here —
# `tools` in its supported_parameters, so it can drive ADK function calls.
#
# Note it is a PAID model, not one of OpenRouter's `:free` ids. Calls fail with
# HTTP 402 unless the account has credits. Free alternatives that also support
# tool calling, if the bill matters more than the model:
#   openai/gpt-oss-20b:free, nvidia/nemotron-3-super-120b-a12b:free,
#   google/gemma-4-31b-it:free, inclusionai/ling-3.0-flash:free
DEFAULT_OPENROUTER_MODEL = "tencent/hy3"
DEFAULT_VERTEX_MODEL = "gemini-2.5-flash"


def get_model(
    default_provider: str = "vertex",
    provider_env: str = "ADK_MODEL_PROVIDER",
    model_env: str = "OPENROUTER_MODEL",
) -> Any:
    """Return the model for an agent: a Gemini id, or a LiteLlm instance.

    Args:
        default_provider: What to use when `provider_env` is unset.
        provider_env: Environment variable naming the provider. An app passes
            its own so it can be switched independently of the others.
        model_env: Environment variable naming the OpenRouter model id.
    """
    provider = os.environ.get(provider_env, default_provider).strip().lower()

    if provider == "openrouter":
        # Key checked before the import: ADK raises its own ImportError for a
        # missing litellm, and that message would otherwise mask the far more
        # likely problem of an unset key.
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise RuntimeError(
                f"{provider_env}=openrouter but OPENROUTER_API_KEY is not set. "
                "In the cluster this comes from the `openrouter` Secret; locally, "
                "export it in your shell. It is deliberately not stored in the "
                "image or the repo."
            )
        # Imported lazily so the Vertex path does not require litellm at all.
        # Needs `pip install litellm` — it is in the `adk` extra in pyproject.
        from google.adk.models.lite_llm import LiteLlm
        name = os.environ.get(model_env, DEFAULT_OPENROUTER_MODEL)
        # LiteLLM routes `openrouter/<id>` to OpenRouter and reads the key from
        # OPENROUTER_API_KEY itself.
        return LiteLlm(model=f"openrouter/{name}")

    return os.environ.get("VERTEX_MODEL", DEFAULT_VERTEX_MODEL)


MODEL = get_model()
