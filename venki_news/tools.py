"""The tools the agents call, and the shared context they mutate.

The rule this file exists to enforce: **the model chooses what to say, never what
a number is.** How many independent newsrooms carry a story, how many characters
a ticker line is, which image URLs exist -- all are computed here in Python from
the wire data and handed to the agent. An agent asked to count six outlets in a
list will usually be right, and the failure is invisible when it is not.

`approve_bulletin` is the odd one out: it changes state rather than reporting it.
It is held by `standards_critic` alone, which is the load-bearing decision in the
graph -- an agent that both writes the bulletin and approves it will approve it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agents import RunContextWrapper, function_tool

from .config import Settings
from .wire import Cluster, WireDesk


@dataclass
class EditorialContext:
    """Passed to every agent in a pass; the only mutable state they share."""

    desk: WireDesk
    settings: Settings
    #: Clusters this pass is allowed to touch. A tool asked about anything else
    #: returns an error rather than data, so a model that invents a plausible
    #: cluster id cannot quietly widen the pass.
    in_scope: set[str] = field(default_factory=set)

    #: Set only by `approve_bulletin`. This, not the critic's `approved` field,
    #: is what ends the review loop.
    approved: bool = False
    approval_reason: str = ""
    #: Every tool call made this pass, for the run log shown in the UI.
    tool_calls: list[str] = field(default_factory=list)

    def cluster(self, cluster_id: str) -> Cluster | None:
        if cluster_id not in self.in_scope:
            return None
        return self.desk.get(cluster_id)


def _log(ctx: RunContextWrapper[EditorialContext], call: str) -> None:
    ctx.context.tool_calls.append(call)


def _unknown(cluster_id: str) -> str:
    return json.dumps(
        {
            "error": "unknown cluster_id",
            "cluster_id": cluster_id,
            "hint": "Use only the cluster_id values given to you in the prompt.",
        }
    )


@function_tool
async def list_cluster_filings(
    ctx: RunContextWrapper[EditorialContext], cluster_id: str
) -> str:
    """Every filing on one incident: which newsroom, when, under what headline.

    Use this when the summary in the prompt is not enough to tell what is
    confirmed from what one outlet is claiming.

    Args:
        cluster_id: The incident id, exactly as given in the prompt.
    """
    _log(ctx, f"list_cluster_filings({cluster_id})")
    cluster = ctx.context.cluster(cluster_id)
    if cluster is None:
        return _unknown(cluster_id)

    return json.dumps(
        {
            "cluster_id": cluster_id,
            "first_filed_utc": cluster.lead.published.isoformat(),
            "latest_filed_utc": cluster.latest.isoformat(),
            "filings": [
                {
                    "outlet": item.outlet,
                    "filed_utc": item.published.isoformat(),
                    "headline": item.title,
                    "summary": item.summary[:400],
                    "link": item.link,
                }
                for item in sorted(cluster.items, key=lambda i: i.published)
            ],
        },
        ensure_ascii=False,
    )


@function_tool
async def count_independent_outlets(
    ctx: RunContextWrapper[EditorialContext], cluster_id: str
) -> str:
    """The number of distinct newsrooms carrying an incident. Authoritative.

    Counted in code after collapsing the spellings of a masthead ("BBC" and
    "BBC News" are one newsroom) and after resolving syndication, so a wire
    story reprinted by an aggregator does not present as independent pickup.
    Do not recount the outlet list yourself -- this number is the one the
    standards check uses.

    Args:
        cluster_id: The incident id, exactly as given in the prompt.
    """
    _log(ctx, f"count_independent_outlets({cluster_id})")
    cluster = ctx.context.cluster(cluster_id)
    if cluster is None:
        return _unknown(cluster_id)

    outlets = cluster.outlets
    return json.dumps(
        {
            "cluster_id": cluster_id,
            "independent_outlets": len(outlets),
            "outlets": outlets,
            "meets_two_source_rule": len(outlets) >= 2,
        },
        ensure_ascii=False,
    )


@function_tool
async def image_candidates(
    ctx: RunContextWrapper[EditorialContext], cluster_id: str
) -> str:
    """The images the filing outlets attached to THIS incident. Widest first.

    This list is exhaustive: it is every image published alongside the story by
    the newsrooms that carried it. There is no other source of pictures, by
    design -- an illustrative photograph of a different event is worse than no
    photograph. An empty list is a normal and frequent result, because nine of
    the nineteen wires carry no images at all.

    Copy a chosen URL exactly. A URL that is not in this list is discarded.

    Args:
        cluster_id: The incident id, exactly as given in the prompt.
    """
    _log(ctx, f"image_candidates({cluster_id})")
    cluster = ctx.context.cluster(cluster_id)
    if cluster is None:
        return _unknown(cluster_id)

    candidates = cluster.image_candidates
    return json.dumps(
        {
            "cluster_id": cluster_id,
            "count": len(candidates),
            "candidates": [
                {
                    "url": c.url,
                    "filed_by": c.outlet,
                    "declared_width_px": c.width or "not declared",
                    "attached_to_headline": c.from_headline,
                }
                for c in candidates[:12]
            ],
        },
        ensure_ascii=False,
    )


@function_tool
async def check_ticker_fit(ctx: RunContextWrapper[EditorialContext], text: str) -> str:
    """Measure a ticker line against the strip it has to fit in.

    Args:
        text: The candidate ticker line.
    """
    limit = ctx.context.settings.ticker_max_chars
    _log(ctx, f"check_ticker_fit({len(text)} chars)")
    return json.dumps(
        {
            "characters": len(text),
            "limit": limit,
            "fits": len(text) <= limit,
            "over_by": max(0, len(text) - limit),
        }
    )


@function_tool
async def approve_bulletin(ctx: RunContextWrapper[EditorialContext], reason: str) -> str:
    """Clear the bulletin for publication. Only the standards critic holds this.

    Call it only once every check has passed. Calling it ends the review loop and
    the bulletin goes on air as written; there is no further gate behind this
    one.

    Args:
        reason: One sentence recording what you checked and found clean.
    """
    _log(ctx, "approve_bulletin")
    ctx.context.approved = True
    ctx.context.approval_reason = reason
    return json.dumps({"approved": True, "recorded_at_utc": datetime.now(timezone.utc).isoformat()})


#: Handed to the agents that only need to read the wire.
READ_TOOLS = [list_cluster_filings, count_independent_outlets]
