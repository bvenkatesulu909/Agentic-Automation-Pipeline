"""Settings for Venki News, read from the environment.

The one setting that shapes everything else is that there are **two cadences**,
not one:

* **The wire tick** runs every `VENKI_WIRE_INTERVAL` seconds (60 by default).
  It is pure Python — fetch, parse, dedupe, cluster — with no model call in it
  at all. This is what makes the ticker move every minute, and it costs nothing.
* **The editorial pass** runs the ten agents, and only when the wire tick
  actually produced something new, no more often than
  `VENKI_EDITORIAL_MIN_INTERVAL` seconds, over at most
  `VENKI_EDITORIAL_MAX_INCIDENTS` clusters.

Running ten agents every sixty seconds is the obvious reading of "live updates
every minute", and it is the wrong build: a full pass is 8-12 model calls, most
minutes bring no new incident, and the pass does not reliably finish inside the
window it would be restarted in. Separating the cadences gets the minute-by-minute
liveness from the layer that can actually sustain it, and spends model calls only
on genuinely new events.

With no API key at all the app still runs: the wire layer is unaffected and the
front page fills from the feeds directly. `VENKI_EDITORIAL=auto` (the default)
turns the agents on when a key is present and leaves them off when it is not,
rather than crashing on startup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Pointed at the repo's own .env rather than searched from the working
# directory. The desktop launcher can be started from anywhere -- a shortcut
# carries whatever "Start in" it was given -- and a CWD-relative search would
# silently find nothing, leaving the editorial desk off with the key sitting
# right there in the file. Real environment variables still win: load_dotenv
# does not override what is already set.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# The SDK's own default. Overridden by VENKI_MODEL; must be a model the account
# in OPENAI_API_KEY (or OPENROUTER_API_KEY) can actually call.
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
# OpenRouter needs a model whose supported_parameters include `tools` — this is a
# tool-calling agent graph and a model without function calling fails every run.
# It needs `structured_outputs` for the same reason: every agent declares an
# output_type, which the SDK sends as a strict json_schema response_format.
DEFAULT_OPENROUTER_MODEL = "tencent/hy3"

#: OpenRouter serves one model id from several upstream providers, and they do
#: not all expose the same features. `tencent/hy3` arrives with tools *and*
#: structured outputs from DeepInfra, Novita, AtlasCloud and Baidu; with tools
#: but no structured outputs from Tencent's own endpoint; and with neither from
#: GMICloud. Routing is decided per request, so pinning the model id is not
#: enough — a graph that ran all morning starts failing the moment load moves it
#: onto a thinner endpoint, and the failure reads like a model quality problem
#: rather than a routing one. `require_parameters` makes OpenRouter discard any
#: provider that cannot serve every parameter in the request, which turns that
#: silent degradation into ordinary provider selection.
OPENROUTER_REQUIRE_PARAMETERS = True


def _int(name: str, default: int, *, low: int, high: int) -> int:
    """Read an int from the environment, clamped to a sane range.

    Clamped rather than validated: a typo in a container env var should degrade
    the cadence, not stop the newsroom starting.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(low, min(high, int(raw)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # --- Cadence -------------------------------------------------------------
    wire_interval: int = 60
    editorial_mode: str = "auto"          # auto | on | off
    editorial_min_interval: int = 180
    editorial_max_incidents: int = 6

    # --- Model ---------------------------------------------------------------
    provider: str = "openai"              # openai | openrouter
    model: str = DEFAULT_OPENAI_MODEL
    #: OpenRouter only. An explicit upstream allowlist, in preference order --
    #: `("deepinfra", "novita")`. Empty means "any provider that satisfies
    #: require_parameters", which is the right default: naming one provider and
    #: nothing else means an outage there is an outage here.
    openrouter_providers: tuple[str, ...] = ()

    # --- Presentation --------------------------------------------------------
    #: Ticker lines are written to fit a single scrolling strip. The limit is
    #: enforced in Python after the agent writes, never trusted to the prompt.
    ticker_max_chars: int = 90
    #: How many stories the front page holds before the oldest fall off.
    front_page_size: int = 24
    #: Wire items older than this are dropped on ingest. Several feeds carry a
    #: long tail of day-old items that would otherwise look like breaking news
    #: on first boot.
    max_item_age_minutes: int = 360

    # --- Server --------------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 8300

    # --- Fetch ---------------------------------------------------------------
    fetch_timeout: float = 15.0
    #: Feeds are polled concurrently; this bounds how many sockets at once.
    fetch_concurrency: int = 12
    user_agent: str = "VenkiNews/1.0 (+personal news desk; contact: local)"

    editorial_enabled: bool = field(default=False)
    api_key_present: bool = field(default=False)


def load() -> Settings:
    provider = os.environ.get("VENKI_MODEL_PROVIDER", "openai").strip().lower()
    if provider not in ("openai", "openrouter"):
        provider = "openai"

    key_env = "OPENROUTER_API_KEY" if provider == "openrouter" else "OPENAI_API_KEY"
    has_key = bool(os.environ.get(key_env, "").strip())

    mode = os.environ.get("VENKI_EDITORIAL", "auto").strip().lower()
    if mode not in ("auto", "on", "off"):
        mode = "auto"
    # `on` without a key is a configuration error worth failing loudly for --
    # the operator asked for the agents by name. `auto` silently degrades.
    if mode == "on" and not has_key:
        raise RuntimeError(
            f"VENKI_EDITORIAL=on but {key_env} is not set. Export the key, or "
            "use VENKI_EDITORIAL=auto to run the wire layer without the agents."
        )
    enabled = has_key if mode == "auto" else (mode == "on")

    default_model = (
        DEFAULT_OPENROUTER_MODEL if provider == "openrouter" else DEFAULT_OPENAI_MODEL
    )

    return Settings(
        wire_interval=_int("VENKI_WIRE_INTERVAL", 60, low=15, high=3600),
        editorial_mode=mode,
        editorial_min_interval=_int(
            "VENKI_EDITORIAL_MIN_INTERVAL", 180, low=30, high=86400
        ),
        editorial_max_incidents=_int("VENKI_EDITORIAL_MAX_INCIDENTS", 6, low=1, high=20),
        provider=provider,
        model=os.environ.get("VENKI_MODEL", "").strip() or default_model,
        openrouter_providers=tuple(
            p.strip()
            for p in os.environ.get("VENKI_OPENROUTER_PROVIDERS", "").split(",")
            if p.strip()
        ),
        ticker_max_chars=_int("VENKI_TICKER_MAX_CHARS", 90, low=40, high=200),
        front_page_size=_int("VENKI_FRONT_PAGE_SIZE", 24, low=4, high=100),
        max_item_age_minutes=_int("VENKI_MAX_ITEM_AGE_MINUTES", 360, low=15, high=10080),
        host=os.environ.get("VENKI_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=_int("VENKI_PORT", 8300, low=1, high=65535),
        editorial_enabled=enabled,
        api_key_present=has_key,
    )
