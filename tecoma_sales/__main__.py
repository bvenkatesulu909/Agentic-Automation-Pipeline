"""Launcher: prepare the database, warm the demo book, serve the desk.

    python -m tecoma_sales                 # http://127.0.0.1:8800
    python -m tecoma_sales --reset         # start from an empty database
    python -m tecoma_sales --no-demo       # no demo enquiries, empty dashboard
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from . import config, db, seed_data
from .desk import make_bus, run_case


def bootstrap(with_demo: bool = True) -> None:
    db.init_db()
    added = seed_data.install_default_fields()
    if added:
        print(f"  seeding schema: {added} fields installed")

    if not with_demo:
        return
    ids = seed_data.install_demo_book()
    if not ids:
        return

    print(f"  demo book: {len(ids)} enquiries — running them across the desk…")

    async def warm() -> None:
        # pace=0: no theatrical delay when pre-filling, the wall is for live cases.
        bus = make_bus(pace=0.0)
        for eid in ids:
            out = await run_case(bus, eid)
            head = out.get("proposal", {}).get("summary") or out.get("status")
            print(f"    {out['ref']}: {head}")

    asyncio.run(warm())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tecoma_sales",
                                 description="TECOMA multi-agent sales desk")
    ap.add_argument("--host", default=config.HOST)
    ap.add_argument("--port", type=int, default=config.PORT)
    ap.add_argument("--no-demo", action="store_true",
                    help="do not install the demo enquiries")
    ap.add_argument("--reset", action="store_true",
                    help="delete the database first")
    ap.add_argument("--pace", type=float, default=None,
                    help="seconds between agent messages on the live wall")
    args = ap.parse_args(argv)

    if args.reset and config.DB_PATH.exists():
        for suffix in ("", "-wal", "-shm"):
            p = config.DB_PATH.with_name(config.DB_PATH.name + suffix)
            p.unlink(missing_ok=True)
        print(f"  reset: removed {config.DB_PATH.name}")

    print(f"TECOMA sales desk — database at {config.DB_PATH}")
    bootstrap(with_demo=not args.no_demo)

    import uvicorn
    from .server import BUS, app

    if args.pace is not None:
        BUS._pace = args.pace

    print(f"\n  open http://{args.host}:{args.port}\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
