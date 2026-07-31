"""End-to-end run of an ADK app in this directory, headless.

Exercises the same path the web UI does — real Vertex calls, real cloud reads,
real retrieval — so a green run here means the UI will work.

    .venv/Scripts/python.exe adk_apps/smoke_test.py                    # incident_commander
    .venv/Scripts/python.exe adk_apps/smoke_test.py finops_commander
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.adk.tools.base_toolset import BaseToolset  # noqa: E402
from google.genai import types  # noqa: E402

PROMPTS = {
    "incident_commander": (
        "Checkout API has been returning HTTP 503 for roughly 12% of requests since "
        "14:20 today. Customers are reporting failed payments. A deploy went out at "
        "14:05. We have not rolled back yet because we are still trying to work out "
        "which service is at fault."
    ),
    "finops_commander": (
        "Give me a full cost review of my Google Cloud setup. What is running, what "
        "is it costing, where am I exposed, and what should I change?"
    ),
    "research_agent": (
        "What are our severity levels, who becomes Incident Commander, and are "
        "Friday deploys allowed? Cite the runbook for each."
    ),
    "billing_app": (
        "Audit my Google Cloud billing connections. Which projects are linked to "
        "billing, is the BigQuery export actually carrying data, do budgets cover "
        "everything, and is there anything you could not verify?"
    ),
    "sales_app": (
        "New opportunity: a logistics company wants us to run their tracking "
        "platform on Google Cloud in asia-south1. They need 6 n2-standard-4 "
        "application servers running 24/7 and about 4 TB of pd-balanced storage. "
        "Their head of engineering is championing it and says the CTO controls the "
        "budget, but we have not spoken to the CTO yet. Their current contract "
        "expires 2026-10-31. No regulated data. They are asking for 25% off and a "
        "12-month term. Qualify it, price it, and tell me if we can do that "
        "discount."
    ),
}

# Each app's report lands in a different state key.
REPORT_KEY = {
    "incident_commander": "final_report",
    "finops_commander": "finops_report",
    "research_agent": "research_answer",
    "billing_app": "connection_report",
    "sales_app": "sales_proposal",
}

# Every tool name across all apps, so preflight can spot an instruction naming
# one the agent does not hold.
KNOWN_TOOL_NAMES = {
    "search_runbook",
    "audit_compute_fleet",
    "audit_network_exposure",
    "check_billing_posture",
    "check_deploy_window",
    "record_timeline",
    "mark_plan_approved",
    "inventory_billable_resources",
    "check_vertex_ai_resources",
    "estimate_instance_monthly_cost",
    "estimate_disk_monthly_cost",
    "lookup_sku_price",
    "check_budgets",
    "check_project_billing_links",
    "check_spend_data_availability",
    "query_actual_spend",
    "record_finding",
    "approve_savings_plan",
    "check_billing_access",
    "map_project_billing_links",
    "check_export_connection",
    "check_budget_coverage",
    "record_connection_gap",
    "approve_connection_plan",
    "price_compute_footprint",
    "price_storage_footprint",
    "price_committed_use",
    "qualify_opportunity",
    "compute_deal_economics",
    "check_discount_authority",
    "record_deal_risk",
    "approve_proposal",
    # Served by the ragstack MCP toolset rather than as function tools. Listed
    # because the toolset names them in its tool_filter, so an instruction that
    # calls one on an agent not holding the toolset is still a catchable error.
    "rag_search",
    "rag_answer",
    "rag_index_status",
}


def preflight(agent, problems: list[str]) -> list[str]:
    """Check every tool an instruction names is actually registered on that agent.

    ADK only discovers this at call time, so a stale instruction costs a full
    multi-minute run before failing. Walking the tree first turns that into a
    one-second check. This exists because the mistake was made.
    """
    tools = getattr(agent, "tools", None) or []
    registered: set[str] = set()
    opaque = False
    for t in tools:
        if isinstance(t, BaseToolset):
            # A toolset normally resolves its tools by talking to a live server,
            # so its contents cannot be known statically and checking an agent
            # holding one would report something untrue. The exception is a
            # *list* tool_filter, which names them exactly — RAGSTACK_MCP carries
            # one. Reading it keeps this check alive on agents that hold a
            # toolset, which matters now that every sales_app agent does: treating
            # them all as opaque would have quietly turned preflight into a no-op
            # for that app at the moment new tool references were added to it.
            names = getattr(t, "tool_filter", None)
            if isinstance(names, (list, tuple)):
                registered.update(names)
            else:
                opaque = True
            continue
        registered.add(getattr(t, "__name__", getattr(t, "name", "")))
    instruction = getattr(agent, "instruction", "") or ""
    if not opaque:
        for name in KNOWN_TOOL_NAMES:
            if f"`{name}`" in instruction and name not in registered:
                problems.append(
                    f"{agent.name}: instruction calls `{name}` but it is not registered"
                )
    for sub in agent.sub_agents or []:
        preflight(sub, problems)
    return problems


async def main() -> int:
    # The Windows console defaults to cp1252, which cannot encode the rupee sign.
    # Every app here reports in INR, so printing the report raised
    # UnicodeEncodeError *after* a fully successful run — losing the RESULT line
    # and returning a failure exit code for a run that had actually passed.
    # errors="replace" rather than a narrower fix: a smoke test must not be able
    # to fail on how a character renders in a terminal.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    app = sys.argv[1] if len(sys.argv) > 1 else "incident_commander"
    if app not in PROMPTS:
        print(f"unknown app {app!r}; known: {', '.join(PROMPTS)}")
        return 2

    root_agent = importlib.import_module(f"{app}.agent").root_agent

    issues = preflight(root_agent, [])
    if issues:
        print("PREFLIGHT FAILED:")
        for i in issues:
            print("  -", i)
        return 2
    print("preflight: tool wiring OK")
    runner = InMemoryRunner(agent=root_agent, app_name=app)
    session = await runner.session_service.create_session(app_name=app, user_id="smoke")

    started = time.time()
    seen: list[str] = []

    async for event in runner.run_async(
        user_id="smoke",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=PROMPTS[app])]),
    ):
        author = getattr(event, "author", "?")
        if author not in seen:
            seen.append(author)
            print(f"  [{time.time()-started:6.1f}s] -> {author}", flush=True)
        if event.content and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "function_call", None):
                    print(f"           tool: {part.function_call.name}", flush=True)

    state = (
        await runner.session_service.get_session(
            app_name=app, user_id="smoke", session_id=session.id
        )
    ).state

    # Read the report from session state rather than reassembling it from the
    # event stream: `output_key` holds the agent's complete final text, whereas
    # streamed parts arrive piecewise and are easy to truncate by accident.
    final = state.get(REPORT_KEY[app], "")

    print(f"\n=== finished in {time.time()-started:.1f}s ===")
    print("agents that ran :", " -> ".join(seen))
    print("state keys      :", sorted(state.keys()))
    print("report chars    :", len(final))
    print("report sections :", [ln for ln in final.splitlines() if ln.startswith("## ")])
    print("\n=== final report ===")
    print(final if final else "(no report produced)")

    # Assert on the output, not on agent count: apps here range from 2 agents to
    # 8, so a count threshold fails a working app for no reason.
    #
    # The upper bounds are not decoration. A report agent asked for an aligned
    # markdown table once degenerated into a single 107,000-character line of
    # column padding, spending its whole token budget on whitespace — and a bare
    # "longer than 200 chars" check called that a PASS. A report is prose: it has
    # line breaks, and no line in it is 2,000 characters wide.
    longest_line = max((len(ln) for ln in final.splitlines()), default=0)
    print("longest line    :", longest_line)
    ok = (
        200 < len(final) < 20_000
        and longest_line < 2_000
        and len(seen) >= 2
    )
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
