"""Entry point: `python -m venki_news`.

Also usable headlessly, which is how you check the newsroom without a browser:

    python -m venki_news --once      one wire tick, print what came off it
    python -m venki_news --pass      one wire tick + one full editorial pass
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from . import config
from .live import LiveDesk
from .server import create_app


def _log_setup(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)-16s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def _once(settings: config.Settings, run_editorial: bool) -> int:
    desk = LiveDesk(settings)
    await desk.wire.tick()

    clusters = desk.wire.clusters
    with_images = sum(1 for c in clusters if c.image_candidates)
    multi = sum(1 for c in clusters if len(c.outlets) > 1)
    print(f"\n{'=' * 78}")
    print(f"WIRE TICK  {len(clusters)} clusters  ·  {multi} multi-outlet  ·  {with_images} with images")
    if desk.wire.last_errors:
        for outlet, err in desk.wire.last_errors.items():
            print(f"  ! {outlet}: {err}")
    print("=" * 78)
    for cluster in clusters[:12]:
        outlets = ", ".join(cluster.outlets[:4])
        print(f"\n  [{len(cluster.outlets)} src] {cluster.lead.title[:88]}")
        print(f"          {outlets}  ·  {cluster.latest:%H:%M}Z  ·  {len(cluster.image_candidates)} img")

    if not run_editorial:
        return 0

    if not settings.editorial_enabled:
        print(
            "\nEditorial pass skipped: no API key. Set OPENAI_API_KEY (or "
            "VENKI_MODEL_PROVIDER=openrouter with OPENROUTER_API_KEY)."
        )
        return 1

    batch = [c for c in clusters if c.needs_review][: settings.editorial_max_incidents]
    print(f"\n{'=' * 78}")
    print(f"EDITORIAL PASS  {len(batch)} clusters  ·  {settings.provider}/{settings.model}")
    print("=" * 78)

    from .newsroom import Newsroom, run_pass

    result = await run_pass(desk.wire, Newsroom(settings), batch)
    if result.error:
        print(f"\n  FAILED: {result.error}")
        return 1

    print(f"\n  LEAD  {result.lead}\n")
    for story in result.stories:
        flag = "✓" if story.safe_to_state_as_fact else "~"
        print(f"  {story.rank}. [{flag}] {story.headline}")
        print(f"      {story.dateline or '(no dateline)'}  ·  {story.region}  ·  {story.severity}")
        print(f"      {story.corroboration} ({story.outlet_count} outlets)  ·  image: {'yes' if story.image_url else 'none'}")
        print(f"      TICKER  {story.ticker}")
    print(
        f"\n  approved={result.approved} rounds={result.review_rounds} "
        f"tools={len(result.tool_calls)} in {result.duration_s:.0f}s"
    )
    if result.approval_reason:
        print(f"  critic: {result.approval_reason}")
    for defect in result.defects:
        print(f"  DEFECT: {defect}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="venki_news", description="Venki News live desk")
    parser.add_argument("--once", action="store_true", help="one wire tick, then exit")
    parser.add_argument("--pass", dest="do_pass", action="store_true",
                        help="one wire tick and one editorial pass, then exit")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    _log_setup(args.verbose)
    settings = config.load()

    if args.once or args.do_pass:
        return asyncio.run(_once(settings, args.do_pass))

    import uvicorn

    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level="warning",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
