"""Runtime settings, all overridable from the environment.

Nothing here needs an API key. The desk is a deterministic engineering pipeline;
the agents reason with mass balances and selection matrices, not with a model.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


# Where the SQLite file lives. Kept beside the package so a clone runs with no
# setup, but pointed elsewhere in the container (see Dockerfile notes in README).
DB_PATH = Path(os.environ.get("TECOMA_DB", PACKAGE_DIR / "tecoma.db"))

HOST = os.environ.get("TECOMA_HOST", "127.0.0.1")
PORT = _env_int("TECOMA_PORT", 8800)

# Seconds the bus waits between delivering envelopes. This is deliberate: the
# whole point of the live wall is watching the agents hand work to each other,
# and at full speed a ten-agent case finishes before the first paint. Set to 0
# for tests and batch runs.
BUS_PACE = _env_float("TECOMA_PACE", 0.45)

# Commercial defaults used by the pricing agent when the enquiry does not say.
ENERGY_EUR_PER_KWH_THERMAL = _env_float("TECOMA_EUR_KWH_TH", 0.055)
ENERGY_EUR_PER_KWH_ELECTRIC = _env_float("TECOMA_EUR_KWH_EL", 0.185)
OPERATING_HOURS_PER_YEAR = _env_int("TECOMA_HOURS_YEAR", 6000)

COMPANY = {
    "name": "TECOMA DRYING TECHNOLOGY S.r.l.",
    "hq": "Maranello (MO), Italy",
    "domain": "Design and manufacture of drying plants for liquid, solid and "
              "semi-solid products",
    "markets": ["food", "feed", "dairy", "nutraceutical", "pharma",
                "rendering", "chemical"],
}
