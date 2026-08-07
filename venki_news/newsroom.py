"""The ten agents, and the editorial pass that runs them.

```
                        wire tick (no model calls)
                                 |
                         new / changed clusters
                                 |
                    1. wire_triage        <- runs alone, gates everything
                                 |
             +--------+----------+----------+--------+
             |        |          |          |        |
        2. americas 3. europe 4. asia_pac 5. mideast_africa      (parallel)
             +--------+----------+----------+--------+
                                 |
             +-------------------+-------------------+
             |                   |                   |
   6. corroboration_editor  7. image_curator   8. ticker_writer   (parallel)
             +-------------------+-------------------+
                                 |
                    9. bulletin_editor  <--------+
                                 |               | defects
                   10. standards_critic ---------+   (loop, max 2)
                                 |
                          approve_bulletin
                                 |
                            front page + ticker
```

## Why triage runs alone rather than inside the parallel branch

It would fit there and it would be wrong. Everything downstream is *scoped* by
triage: the regional desks only see stories triage routed to them, the image
curator only pulls pictures for stories triage kept, and the ticker only carries
what triage judged to be an event. Run it alongside the desks and every desk is
working on unfiltered wire -- including the live-blog rollups and opinion columns
that make up a third of a raw feed poll. The fifteen seconds saved buys a
front page of comment pieces.

## Why the desks are four agents and not one with a region parameter

Because they disagree, and the disagreement is the product. Four separate agents
each hold a different remit and see only their own region's filings, so no single
context is asked to weigh a Sahel coup against a Senate vote and decide which is
"more important" -- that ranking is `bulletin_editor`'s job, made once, visibly,
with all four desks' copy in front of it. Folding the desks into one agent moves
that judgment into an unlogged corner of a prompt.

## What the model is not allowed to do

**Add context from its own knowledge.** This is the rule that matters most here
and it is the opposite of what an LLM is good at. A model's world knowledge is
frozen at its training cutoff; this app's whole claim is that it is current. An
agent that helpfully explains the background to a ceasefire is reciting a
possibly-superseded state of the world in the middle of a live bulletin, in
exactly the same voice as the facts it read off the wire two minutes ago. Every
desk instruction says: if the filings do not say it, it does not go in.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agents import (
    Agent,
    AsyncOpenAI,
    ModelSettings,
    OpenAIChatCompletionsModel,
    Runner,
    set_default_openai_api,
    set_default_openai_client,
    set_tracing_disabled,
)

from .config import OPENROUTER_REQUIRE_PARAMETERS, Settings
from .models import (
    Bulletin,
    CorroborationFile,
    DeskFile,
    ImageFile,
    StandardsReview,
    TickerFile,
    TriageBatch,
)
from .sources import REGION_LABELS
from .tools import (
    EditorialContext,
    approve_bulletin,
    check_ticker_fit,
    count_independent_outlets,
    image_candidates,
    list_cluster_filings,
)
from .wire import Cluster, WireDesk

log = logging.getLogger("venki.newsroom")

_MAX_REVIEW_ROUNDS = 2
#: Tool-calling agents need headroom for a call-then-answer round per story.
_MAX_TURNS = 14


# --------------------------------------------------------------------------- #
# Provider
# --------------------------------------------------------------------------- #

_configured = False
_openrouter_client: AsyncOpenAI | None = None


def configure_provider(settings: Settings) -> AsyncOpenAI | None:
    """Point the SDK at OpenAI or at OpenRouter. Idempotent.

    Returns the OpenRouter client when there is one, so the agents can be bound
    to it by hand -- see `_resolve_model` for why a client is not enough.
    """
    global _configured, _openrouter_client
    if _configured:
        return _openrouter_client

    if not settings.api_key_present:
        # Reached only by tests, which drive the agents with a stub model. The
        # SDK would otherwise try to ship traces to OpenAI and log a warning per
        # run about the key it cannot find.
        set_tracing_disabled(True)

    if settings.provider == "openrouter":
        # OpenRouter speaks Chat Completions, not the Responses API the SDK
        # defaults to, so both the client and the API surface have to move.
        _openrouter_client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )
        set_default_openai_client(_openrouter_client, use_for_tracing=False)
        set_default_openai_api("chat_completions")
        # Traces upload to OpenAI, which this key cannot authenticate against;
        # leaving it on produces a stream of 401s that look like model failures.
        set_tracing_disabled(True)

    _configured = True
    return _openrouter_client


def _resolve_model(
    settings: Settings, client: AsyncOpenAI | None
) -> str | OpenAIChatCompletionsModel:
    """Bind the model to a client rather than handing the SDK a bare string.

    This is the difference between hy3 running and hy3 not running at all. A
    string goes through the SDK's MultiProvider, which reads everything before
    the first '/' as a *provider prefix*: `tencent/hy3` raises
    `UserError: Unknown prefix: tencent` at turn one, before any request is
    built. Setting the default client does not help, because resolution happens
    before the client is ever consulted.

    The old OpenRouter default hid this completely -- `openai/gpt-5.4-mini`
    happens to lead with a prefix the SDK recognises, so it resolved by
    coincidence while every non-OpenAI vendor on OpenRouter was unreachable.
    Passing a model object skips prefix resolution altogether.
    """
    if client is None:
        return settings.model
    return OpenAIChatCompletionsModel(model=settings.model, openai_client=client)


# --------------------------------------------------------------------------- #
# House style, shared by every agent
# --------------------------------------------------------------------------- #

_HOUSE_RULES = """
You work at Venki News, a live world desk. House rules, in force for every agent:

1. The filings are the only source of fact. If the wire copy in front of you does
   not say it, you do not write it. This includes background, history, and
   context you happen to know: your training data is months old and this bulletin
   is minutes old, and a reader cannot tell which sentence is which.
2. Attribute anything contested. "Police said", "the health ministry reported",
   "according to one outlet" -- not the bare assertion.
3. Casualty figures, blame for an attack, and death tolls in the first hours are
   claims, not facts, unless two independent newsrooms carry the same number.
4. Numbers come from tools, never from your own counting or arithmetic.
5. Never invent a URL, an outlet, a place, or a time.
6. Plain English. No "amid mounting tensions", no "sends shockwaves", no
   rhetorical questions, no scare quotes doing an argument's work.
""".strip()


def _openrouter_routing(settings: Settings) -> dict:
    """The `provider` block OpenRouter reads to choose an upstream.

    See `config.OPENROUTER_REQUIRE_PARAMETERS` for why this is not optional: the
    same model id is served by endpoints with and without structured outputs,
    and the ones without do not error cleanly -- they return prose where the SDK
    expects a schema, which surfaces as a parse failure three stages later.
    """
    routing: dict = {"require_parameters": OPENROUTER_REQUIRE_PARAMETERS}
    if settings.openrouter_providers:
        routing["only"] = list(settings.openrouter_providers)
    return routing


def _model_settings(settings: Settings) -> ModelSettings:
    """Lower the temperature where the model accepts one, and pin OpenRouter
    routing where that applies.

    Reasoning models reject `temperature` outright and the default OpenAI model
    is one, so those get an empty ModelSettings -- *not* None, which the SDK
    refuses with a TypeError at Agent construction. Returning None here crashed
    every agent build under the default model until a test caught it.

    `tencent/hy3` is a reasoning model but does take `temperature`, so it is not
    in the exclusion below; the check is on model families known to reject the
    parameter, not on whether a model reasons.
    """
    name = settings.model.lower()
    temperature = (
        None if ("gpt-5" in name or name.startswith(("o1", "o3", "o4"))) else 0.2
    )
    extra_body = (
        {"provider": _openrouter_routing(settings)}
        if settings.provider == "openrouter"
        else None
    )
    return ModelSettings(temperature=temperature, extra_body=extra_body)


# --------------------------------------------------------------------------- #
# The ten agents
# --------------------------------------------------------------------------- #

_DESK_REMITS: dict[str, str] = {
    "americas": (
        "the Americas -- the United States, Canada, Mexico, Central and South "
        "America, and the Caribbean. Washington politics is heavily filed and "
        "easy to over-weight; a hurricane landfall in Honduras or a mine "
        "collapse in Peru is the bigger story on most days."
    ),
    "europe": (
        "Europe -- the EU, the UK, the Balkans, Turkey, Russia, Ukraine, and the "
        "Caucasus. The Russia-Ukraine war produces continuous filings, so "
        "distinguish a new event from a running summary of an old one."
    ),
    "asia_pacific": (
        "Asia-Pacific -- China, India, Japan, the Koreas, Southeast Asia, "
        "Australia, New Zealand, and the Pacific islands. This is the region "
        "most under-covered by English-language wires, so a thin filing does "
        "not mean a small event."
    ),
    "mideast_africa": (
        "the Middle East and Africa -- the Gulf, Israel and the Palestinian "
        "territories, Iran, the Levant, North Africa, the Sahel, the Horn, and "
        "sub-Saharan Africa. Casualty figures here are contested more often "
        "than anywhere else on the wire; attribute every one of them."
    ),
}


@dataclass
class Newsroom:
    """The ten agents, built once and reused across passes."""

    settings: Settings
    triage: Agent = field(init=False)
    desks: dict[str, Agent] = field(init=False)
    corroboration: Agent = field(init=False)
    images: Agent = field(init=False)
    ticker: Agent = field(init=False)
    bulletin: Agent = field(init=False)
    critic: Agent = field(init=False)

    def __post_init__(self) -> None:
        model = _resolve_model(self.settings, configure_provider(self.settings))
        ms = _model_settings(self.settings)

        def agent(name: str, instructions: str, output_type, tools=()) -> Agent:
            return Agent(
                name=name,
                instructions=f"{_HOUSE_RULES}\n\n{instructions.strip()}",
                model=model,
                model_settings=ms,
                tools=list(tools),
                output_type=output_type,
            )

        # -- 1 -------------------------------------------------------------- #
        self.triage = agent(
            "wire_triage",
            """
You are the wire triage desk. You see everything that came off nineteen feeds and
you decide what the newsroom works on. Nothing downstream sees what you reject.

Return EXACTLY one verdict for each cluster_id you are given -- no extras, no
omissions, ids copied character for character.

Set publish=false for:
  - opinion, comment, analysis, editorials, columns, "what this means for..."
  - live-blog rollups and running summaries ("Middle East crisis live: ...",
    "Ukraine war briefing", "as it happened")
  - sport results and fixtures, entertainment, celebrity, royals
  - reviews, recipes, listicles, quizzes, obituaries of private individuals
  - explainers and "what we know so far" pieces that restate an event rather
    than report a new development

Set publish=true for a discrete real-world development a world desk would carry.

region is where the event HAPPENED. The outlet's own country is irrelevant and is
a common trap: the BBC files on Indonesia, Al Jazeera files on Washington.

severity:
  breaking    - mass casualties, a major attack, a large disaster, the fall of a
                government, in the last hour or two. Be strict. If everything is
                breaking, the word carries nothing.
  major       - a significant national or international development
  developing  - a real event still taking shape, details thin
  routine     - genuine news, no urgency

incident=true when something happened TO people or places: a strike, a crash, an
earthquake, a fire, a flood, an outbreak, an attack, a collapse. incident=false
for process news: talks, rulings, elections, appointments, indictments, markets.
            """,
            TriageBatch,
            tools=[list_cluster_filings],
        )

        # -- 2-5 ------------------------------------------------------------ #
        self.desks = {
            region: agent(
                f"{region}_desk",
                f"""
You are the {REGION_LABELS[region]} desk. Your patch is {_DESK_REMITS[region]}

For each incident you are given, file the copy the front page will carry.

  headline    Plain and factual, under 100 characters. Say what happened. Do not
              use a colon to smuggle in a second clause.
  dateline    Wire style -- 'KYIV, Aug 4'. The place is where the event happened,
              taken from the filings. Empty string if the filings do not agree on
              one, which is normal early in a disaster.
  body        Two to three sentences: what happened, where, who is affected. No
              background paragraph. No prediction of what happens next.
  confirmed   Facts the filings carry with attribution.
  reported_not_confirmed
              Anything one outlet alone carries; anything attributed to a party
              with an interest in it; every casualty figure that
              count_independent_outlets does not show as multi-source.

Call count_independent_outlets before you decide where a casualty figure goes.
Call list_cluster_filings when the prompt summary is too thin to write from.

Return exactly one story per cluster_id given, ids copied exactly. If a story is
too thin to write honestly, still file it -- say what is known in one sentence
and put the rest in reported_not_confirmed. Do not drop it silently.
                """,
                DeskFile,
                tools=[list_cluster_filings, count_independent_outlets],
            )
            for region in _DESK_REMITS
        }

        # -- 6 -------------------------------------------------------------- #
        self.corroboration = agent(
            "corroboration_editor",
            """
You decide what the front page is allowed to state as fact.

For EVERY incident, call count_independent_outlets. That number is authoritative
and already accounts for one masthead spelling its name two ways and for
syndication. Do not count the outlet list yourself.

  corroborated   two or more independent newsrooms
  single_source  exactly one
  conflicting    the filings disagree on a material fact -- a death toll, who did
                 it, whether someone is alive, whether a deal was signed. Call
                 list_cluster_filings and read them before ruling this.

safe_to_state_as_fact is false for every single_source incident, for every
conflicting one, and for any casualty or attribution figure carried by one
newsroom even when the event itself is corroborated.

A single-source story is not a rejected story. It runs, labelled. Set
conflict_note only for 'conflicting'; empty string otherwise.
            """,
            CorroborationFile,
            tools=[list_cluster_filings, count_independent_outlets],
        )

        # -- 7 -------------------------------------------------------------- #
        self.images = agent(
            "image_curator",
            """
You choose the picture on each card, from the pictures the filing newsrooms
attached to that exact story. There is no other source of images and you must not
invent one.

For EVERY incident, call image_candidates. Then:

  - Copy the chosen url EXACTLY as returned. A url that is not in the list is
    discarded before it reaches the page, and the card runs blank.
  - Prefer the widest declared width. Below about 300px a picture is a thumbnail
    and looks broken across a card.
  - Read attached_to_headline. Feeds sometimes attach a section-front or a
    promotional image that belongs to a different story; if the headline the
    image was attached to is not this incident, reject it.
  - Return an empty image_url when no candidate is defensible. That is a normal
    outcome -- nine of the nineteen wires carry no images at all -- and it is
    always better than a picture of a different event.

  credit    the newsroom in filed_by, exactly. Empty when no image.
  alt_text  what is actually depicted, for a screen reader. Do not restate the
            headline; describe the picture. Empty when no image.
  note      one clause: why this one, or why none.

Return exactly one pick per cluster_id given.
            """,
            ImageFile,
            tools=[image_candidates],
        )

        # -- 8 -------------------------------------------------------------- #
        self.ticker = agent(
            "ticker_writer",
            """
You write the scrolling strip in the app bar. It moves past a reader in a couple
of seconds and it is often all they read.

One line per incident:
  - Lead with the place in capitals, then a colon: 'GAZA: ...', 'TOKYO: ...'
  - Present tense. No trailing full stop. No outlet name. No 'BREAKING'.
  - Say the thing itself. 'Ferry sinks off Mindanao, 30 missing' -- not
    'Officials respond to maritime incident'.
  - Numbers only when the desk copy marked them confirmed.

Call check_ticker_fit on each line before you return it, and rewrite anything
that does not fit. Shorten by cutting words, not by ending mid-phrase.

Return exactly one line per cluster_id given.
            """,
            TickerFile,
            tools=[check_ticker_fit],
        )

        # -- 9 -------------------------------------------------------------- #
        self.bulletin = agent(
            "bulletin_editor",
            """
You run the front page. You have every desk's copy, the corroboration rulings and
the ticker lines. Rank the incidents and write the lead.

Rank on, in order:
  1. Human impact -- lives at risk or lost, people displaced, services down.
  2. Recency -- something that happened an hour ago outranks this morning.
  3. Corroboration -- between two comparable stories, the confirmed one leads.
  4. Spread -- do not stack four stories from one region at the top if the world
     is doing other things.

Ranks are consecutive from 1 with no gaps and no ties. Include every cluster_id
you are given, exactly once.

lead: one sentence, the single most important thing happening in the world right
now. It must be supported by the top-ranked story's copy -- it is a summary of
that story, not a new claim, and not a claim about several stories at once.

If you are given defects from a previous review, fix exactly those and change
nothing else.
            """,
            Bulletin,
        )

        # -- 10 ------------------------------------------------------------- #
        self.critic = agent(
            "standards_critic",
            """
You are the last gate before the bulletin goes on air. You did not write any of
it, and that is the point: your job is to find what is wrong with it.

Work through all six checks, every time:

  1. Ranking. Every cluster_id given is ranked exactly once. Ranks run 1..N with
     no gaps and no ties.
  2. Unverified material stated as fact. Cross-check the desk copy against the
     corroboration rulings: anything where safe_to_state_as_fact is false must be
     attributed in the body or sitting in reported_not_confirmed -- never
     asserted flat. This is the check that matters most.
  3. Images. Every credit names a newsroom that actually carried that story. An
     image credited to an outlet not in that incident's filings is a defect.
  4. Ticker. Within the character limit, no outlet names, no full stops, and it
     says the same thing as the headline it belongs to.
  5. Lead. Supported by the top-ranked story. A lead that generalises across
     several stories, or adds a claim none of them make, is a defect.
  6. Duplicates. Two entries describing the same event is a defect -- name both
     cluster_ids.

If every check passes, call approve_bulletin with one sentence recording what you
checked, and return approved=true with empty lists.

If anything fails, DO NOT call approve_bulletin. Return approved=false, one
defect per problem naming the cluster_id, and one instruction per defect in
required_fixes. Be specific: 'entry a1b2 states 30 dead as fact; corroboration
says single_source; attribute it to the health ministry' -- not 'improve
sourcing'.

You are not here to make it read better. Only defects.
            """,
            StandardsReview,
            tools=[approve_bulletin, list_cluster_filings, count_independent_outlets],
        )

    @property
    def all_agents(self) -> list[Agent]:
        return [
            self.triage,
            *self.desks.values(),
            self.corroboration,
            self.images,
            self.ticker,
            self.bulletin,
            self.critic,
        ]


# --------------------------------------------------------------------------- #
# What a pass produces
# --------------------------------------------------------------------------- #

@dataclass
class PublishedStory:
    cluster_id: str
    headline: str
    dateline: str
    body: str
    region: str
    category: str
    severity: str
    incident: bool
    confirmed: list[str]
    reported_not_confirmed: list[str]
    corroboration: str
    conflict_note: str
    safe_to_state_as_fact: bool
    outlets: list[str]
    outlet_count: int
    image_url: str
    image_credit: str
    image_alt: str
    ticker: str
    rank: int
    link: str
    published_utc: str
    first_seen_utc: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class PassResult:
    stories: list[PublishedStory]
    lead: str
    approved: bool
    approval_reason: str
    review_rounds: int
    defects: list[str]
    tool_calls: list[str]
    started_utc: str
    duration_s: float
    error: str = ""


# --------------------------------------------------------------------------- #
# Prompt payloads
# --------------------------------------------------------------------------- #

def _brief(cluster: Cluster) -> dict:
    lead = cluster.lead
    return {
        "cluster_id": cluster.id,
        "headline": lead.title,
        "summary": lead.summary[:320],
        "outlets": cluster.outlets,
        "outlet_count": len(cluster.outlets),
        "first_filed_utc": lead.published.isoformat(timespec="minutes"),
        "latest_filed_utc": cluster.latest.isoformat(timespec="minutes"),
        "other_headlines": [
            i.title for i in sorted(cluster.items, key=lambda x: x.published)[1:4]
        ],
        "has_image_candidates": bool(cluster.image_candidates),
    }


def _now_line() -> str:
    now = datetime.now(timezone.utc)
    return f"Current time: {now:%Y-%m-%d %H:%M} UTC ({now:%A}). Use it for datelines."


async def _run(agent: Agent, prompt: str, ctx: EditorialContext):
    result = await Runner.run(agent, prompt, context=ctx, max_turns=_MAX_TURNS)
    return result.final_output


# --------------------------------------------------------------------------- #
# The pass
# --------------------------------------------------------------------------- #

async def run_pass(
    desk: WireDesk, newsroom: Newsroom, clusters: list[Cluster]
) -> PassResult:
    """Run all ten agents over `clusters` and return a publishable front page.

    Every stage validates the agent's output against the wire before the next
    stage sees it. An id that was not sent out, an image URL that was not in the
    candidate list, a ticker line over the limit -- all are corrected or dropped
    here rather than trusted. The agents are asked to get these right and are not
    relied upon to.
    """
    started = datetime.now(timezone.utc)
    settings = newsroom.settings
    ctx = EditorialContext(
        desk=desk, settings=settings, in_scope={c.id for c in clusters}
    )
    by_id = {c.id: c for c in clusters}

    def fail(msg: str) -> PassResult:
        log.warning("editorial pass aborted: %s", msg)
        return PassResult(
            stories=[],
            lead="",
            approved=False,
            approval_reason="",
            review_rounds=0,
            defects=[],
            tool_calls=ctx.tool_calls,
            started_utc=started.isoformat(),
            duration_s=(datetime.now(timezone.utc) - started).total_seconds(),
            error=msg,
        )

    # -- 1 · triage --------------------------------------------------------- #
    try:
        triage: TriageBatch = await _run(
            newsroom.triage,
            f"{_now_line()}\n\nTriage these {len(clusters)} wire clusters.\n\n"
            + json.dumps([_brief(c) for c in clusters], ensure_ascii=False, indent=1),
            ctx,
        )
    except Exception as exc:  # noqa: BLE001
        return fail(f"triage failed: {type(exc).__name__}: {exc}")

    verdicts = {v.cluster_id: v for v in triage.verdicts if v.cluster_id in by_id}
    kept = [v for v in verdicts.values() if v.publish]
    if not kept:
        log.info("triage rejected all %d clusters", len(clusters))
        return PassResult(
            stories=[],
            lead="",
            approved=True,
            approval_reason="Nothing on the wire met the bar for the front page.",
            review_rounds=0,
            defects=[],
            tool_calls=ctx.tool_calls,
            started_utc=started.isoformat(),
            duration_s=(datetime.now(timezone.utc) - started).total_seconds(),
        )

    # -- 2-5 · regional desks, in parallel ---------------------------------- #
    # 'global' has no desk of its own -- a genuinely borderless story still
    # happened somewhere a desk covers, and the alternative is a fifth desk with
    # no remit. Triage routes it to Europe, which carries the multilateral beat.
    routed: dict[str, list[str]] = {r: [] for r in newsroom.desks}
    for v in kept:
        routed[v.region if v.region in routed else "europe"].append(v.cluster_id)

    async def desk_run(region: str, ids: list[str]) -> DeskFile | None:
        if not ids:
            return None
        payload = [_brief(by_id[i]) | {"triage": verdicts[i].model_dump()} for i in ids]
        try:
            return await _run(
                newsroom.desks[region],
                f"{_now_line()}\n\nFile copy on these {len(ids)} incidents.\n\n"
                + json.dumps(payload, ensure_ascii=False, indent=1),
                ctx,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("%s desk failed: %s", region, exc)
            return None

    desk_files = await asyncio.gather(*(desk_run(r, ids) for r, ids in routed.items()))
    stories = {
        s.cluster_id: s
        for f in desk_files
        if f is not None
        for s in f.stories
        if s.cluster_id in verdicts
    }
    if not stories:
        return fail("every regional desk failed or filed nothing")

    live_ids = sorted(stories, key=lambda i: by_id[i].latest, reverse=True)
    ctx.in_scope = set(live_ids)
    briefs = json.dumps(
        [_brief(by_id[i]) for i in live_ids], ensure_ascii=False, indent=1
    )
    copy = json.dumps(
        [stories[i].model_dump() for i in live_ids], ensure_ascii=False, indent=1
    )

    # -- 6-8 · verification and presentation, in parallel ------------------- #
    async def stage(agent: Agent, prompt: str, label: str):
        try:
            return await _run(agent, prompt, ctx)
        except Exception as exc:  # noqa: BLE001
            log.warning("%s failed: %s", label, exc)
            return None

    corrob, imgs, ticks = await asyncio.gather(
        stage(
            newsroom.corroboration,
            f"Rule on these {len(live_ids)} incidents. Call "
            f"count_independent_outlets for every one.\n\n{briefs}",
            "corroboration_editor",
        ),
        stage(
            newsroom.images,
            f"Pick the picture for these {len(live_ids)} incidents. Call "
            f"image_candidates for every one.\n\n{briefs}",
            "image_curator",
        ),
        stage(
            newsroom.ticker,
            f"Write ticker lines for these {len(live_ids)} incidents. The strip "
            f"holds {settings.ticker_max_chars} characters.\n\n{copy}",
            "ticker_writer",
        ),
    )

    rulings = {r.cluster_id: r for r in (corrob.rulings if corrob else [])}
    picks = {p.cluster_id: p for p in (imgs.picks if imgs else [])}
    lines = {t.cluster_id: t for t in (ticks.lines if ticks else [])}

    # -- 9-10 · the review loop --------------------------------------------- #
    bulletin: Bulletin | None = None
    review: StandardsReview | None = None
    rounds = 0
    fixes: list[str] = []

    review_payload = json.dumps(
        [
            {
                **stories[i].model_dump(),
                "corroboration": rulings[i].model_dump() if i in rulings else None,
                "image": picks[i].model_dump() if i in picks else None,
                "ticker": lines[i].text if i in lines else "",
                "outlet_count": len(by_id[i].outlets),
                "latest_filed_utc": by_id[i].latest.isoformat(timespec="minutes"),
            }
            for i in live_ids
        ],
        ensure_ascii=False,
        indent=1,
    )

    for rounds in range(1, _MAX_REVIEW_ROUNDS + 1):
        note = (
            ""
            if not fixes
            else "\n\nThe standards desk sent this back. Fix exactly these and "
            "nothing else:\n- " + "\n- ".join(fixes)
        )
        bulletin = await stage(
            newsroom.bulletin,
            f"{_now_line()}\n\nRank these {len(live_ids)} incidents and write the "
            f"lead.\n\n{review_payload}{note}",
            "bulletin_editor",
        )
        if bulletin is None:
            break

        ctx.approved = False
        review = await stage(
            newsroom.critic,
            f"{_now_line()}\n\nReview this bulletin against all six checks.\n\n"
            f"BULLETIN\n{bulletin.model_dump_json(indent=1)}\n\n"
            f"THE MATERIAL IT WAS BUILT FROM\n{review_payload}",
            "standards_critic",
        )
        # The tool call is the approval. A review asserting approved=true without
        # having called approve_bulletin has not approved anything, and this is
        # the check that makes the critic's tool monopoly mean something.
        if ctx.approved:
            break
        fixes = list(review.required_fixes) if review else []
        if not fixes:
            break

    if bulletin is None:
        return fail("bulletin editor failed on every round")

    ranks = {e.cluster_id: e.rank for e in bulletin.entries if e.cluster_id in stories}

    # -- assemble ------------------------------------------------------------ #
    published: list[PublishedStory] = []
    for i in live_ids:
        s = stories[i]
        v = verdicts[i]
        c = by_id[i]
        r = rulings.get(i)
        p = picks.get(i)

        # Hard guard: an image URL the curator did not take from the candidate
        # list never reaches the page. The instruction says copy exactly; this is
        # what makes that true.
        image_url, image_credit, image_alt = "", "", ""
        if p and p.image_url:
            allowed = {cand.url: cand for cand in c.image_candidates}
            cand = allowed.get(p.image_url.strip())
            if cand is not None:
                image_url = cand.url
                image_credit = p.credit or cand.outlet
                image_alt = p.alt_text or s.headline
            else:
                log.warning("dropped invented image url on %s", i)

        ticker_text = (lines[i].text if i in lines else s.headline).strip()
        if len(ticker_text) > settings.ticker_max_chars:
            ticker_text = ticker_text[: settings.ticker_max_chars - 1].rstrip(" ,;:-") + "…"

        published.append(
            PublishedStory(
                cluster_id=i,
                headline=s.headline.strip(),
                dateline=s.dateline.strip(),
                body=s.body.strip(),
                region=v.region,
                category=v.category,
                severity=v.severity,
                incident=v.incident,
                confirmed=s.confirmed,
                reported_not_confirmed=s.reported_not_confirmed,
                corroboration=r.status if r else "unreviewed",
                conflict_note=r.conflict_note if r else "",
                safe_to_state_as_fact=r.safe_to_state_as_fact if r else False,
                outlets=c.outlets,
                outlet_count=len(c.outlets),
                image_url=image_url,
                image_credit=image_credit,
                image_alt=image_alt,
                ticker=ticker_text,
                rank=ranks.get(i, 999),
                link=c.lead.link,
                published_utc=c.latest.isoformat(),
                first_seen_utc=c.first_seen.isoformat(),
            )
        )

    published.sort(key=lambda s: (s.rank, s.published_utc))

    return PassResult(
        stories=published,
        lead=bulletin.lead.strip(),
        approved=ctx.approved,
        approval_reason=ctx.approval_reason,
        review_rounds=rounds,
        defects=list(review.defects) if review and not ctx.approved else [],
        tool_calls=ctx.tool_calls,
        started_utc=started.isoformat(),
        duration_s=(datetime.now(timezone.utc) - started).total_seconds(),
    )
