"""Wait for the desk to answer `/healthz`, then open a browser at it.

Run detached by the desktop launcher so the server itself can hold the console
in the foreground. Exists as a file rather than a `python -c` one-liner in the
.cmd because quoting a multi-statement program through cmd is exactly the trap
that made the launcher's first port lookup fail silently.

Waiting rather than sleeping a fixed few seconds: the first wire tick polls
nineteen feeds, and how long that takes depends on the slowest of them.
"""

from __future__ import annotations

import sys
import time
import urllib.request
import webbrowser

#: Long enough for a cold start on a slow link. On expiry the browser opens
#: anyway -- a page showing a connection error is more use than a launcher that
#: appears to have done nothing at all.
TIMEOUT_S = 60.0
POLL_S = 1.0


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8300
    deadline = time.monotonic() + TIMEOUT_S

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/healthz", timeout=2
            ) as response:
                if response.status == 200:
                    break
        except Exception:  # noqa: BLE001 - not up yet is the expected case
            pass
        time.sleep(POLL_S)

    webbrowser.open(f"http://localhost:{port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
