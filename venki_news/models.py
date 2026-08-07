"""Structured outputs for the ten agents.

Every agent in this newsroom returns a Pydantic model rather than prose, which
the Agents SDK enforces at the API layer by compiling each into a strict JSON
schema. That is not a style preference. The output of eight of these ten agents
is consumed by another agent or by the renderer, and free text between stages is
where a pipeline stops being checkable: a desk that answers "I could not find
enough detail on this one" in prose is indistinguishable, to the next stage, from
one that filed a story.

Two conventions worth knowing before reading the fields:

* **`cluster_id` is on every per-story model.** Agents are handed a batch and
  return a batch, and there is no promise the order survives. Matching on
  position would silently attach one incident's ticker line to another's card.
  Anything coming back with an id that was not sent is dropped in `newsroom.py`.
* **Empty string means "none", not "unknown".** Strict schemas make every field
  required, so an optional value is expressed as `""` and documented here rather
  than as a nullable the model has to decide how to fill.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Region = Literal["americas", "europe", "asia_pacific", "mideast_africa", "global"]

Category = Literal[
    "conflict",
    "disaster",
    "politics",
    "economy",
    "health",
    "climate",
    "science_tech",
    "society",
    "sport",
    "other",
]

#: Severity drives ordering and the colour of the card's rail. `breaking` is
#: reserved deliberately: if everything is breaking, the ticker tells a reader
#: nothing they can act on.
Severity = Literal["breaking", "major", "developing", "routine"]


# --------------------------------------------------------------------------- #
# 1 · wire_triage
# --------------------------------------------------------------------------- #

class TriageVerdict(BaseModel):
    cluster_id: str
    publish: bool = Field(
        description="True if this is a real-world event a world desk would carry. "
        "False for opinion, analysis, sport results, listicles, live-blog "
        "rollups, and anything that is commentary about an event rather than "
        "the event."
    )
    reason: str = Field(description="One clause. Why publish or why not.")
    region: Region = Field(
        description="Where the event HAPPENED. Not where the outlet is. Use "
        "'global' only when the event genuinely has no single location."
    )
    category: Category
    severity: Severity
    incident: bool = Field(
        description="True when something happened TO people or places -- a "
        "strike, crash, quake, fire, flood, outbreak, attack. False for "
        "process news: talks, rulings, appointments, market moves."
    )


class TriageBatch(BaseModel):
    verdicts: list[TriageVerdict]


# --------------------------------------------------------------------------- #
# 2-5 · regional desks
# --------------------------------------------------------------------------- #

class DeskStory(BaseModel):
    cluster_id: str
    headline: str = Field(description="Plain, factual, under 100 characters. No colon-clause padding.")
    dateline: str = Field(
        description="Place and date in wire style, e.g. 'KYIV, Aug 4'. Empty "
        "string if the filings do not agree on a place."
    )
    body: str = Field(description="Two to three sentences. What happened, where, who is affected.")
    confirmed: list[str] = Field(
        description="Facts carried by the filings and attributed. Each entry a short clause."
    )
    reported_not_confirmed: list[str] = Field(
        description="Claims a single outlet carries, or that the filings attribute to "
        "an interested party. Casualty figures early in an event belong here."
    )


class DeskFile(BaseModel):
    stories: list[DeskStory]


# --------------------------------------------------------------------------- #
# 6 · corroboration_editor
# --------------------------------------------------------------------------- #

class CorroborationRuling(BaseModel):
    cluster_id: str
    status: Literal["corroborated", "single_source", "conflicting"] = Field(
        description="'corroborated' needs two or more INDEPENDENT newsrooms -- "
        "use the count from the tool, not your own reading of the list. "
        "'conflicting' when the filings disagree on a material fact."
    )
    conflict_note: str = Field(
        description="If status is 'conflicting', what the outlets disagree about. "
        "Empty string otherwise."
    )
    safe_to_state_as_fact: bool = Field(
        description="False for a single-source claim, and for any casualty or "
        "attribution figure that only one newsroom carries."
    )


class CorroborationFile(BaseModel):
    rulings: list[CorroborationRuling]


# --------------------------------------------------------------------------- #
# 7 · image_curator
# --------------------------------------------------------------------------- #

class ImagePick(BaseModel):
    cluster_id: str
    image_url: str = Field(
        description="Must be copied EXACTLY from the candidate list returned by "
        "the image_candidates tool. Empty string when no candidate is "
        "defensible -- that is a normal outcome, not a failure."
    )
    credit: str = Field(description="The outlet that filed the image. Empty string when no image.")
    alt_text: str = Field(description="What is depicted, for a screen reader. Empty when no image.")
    note: str = Field(description="One clause: why this image, or why none.")


class ImageFile(BaseModel):
    picks: list[ImagePick]


# --------------------------------------------------------------------------- #
# 8 · ticker_writer
# --------------------------------------------------------------------------- #

class TickerLine(BaseModel):
    cluster_id: str
    text: str = Field(
        description="One scrolling line. Present tense, no trailing full stop, "
        "no outlet name. Written to fit the character limit given in the prompt."
    )


class TickerFile(BaseModel):
    lines: list[TickerLine]


# --------------------------------------------------------------------------- #
# 9 · bulletin_editor
# --------------------------------------------------------------------------- #

class BulletinEntry(BaseModel):
    cluster_id: str
    rank: int = Field(description="1 is the lead story. Consecutive from 1, no ties.")
    why_ranked: str = Field(description="One clause justifying the position.")


class Bulletin(BaseModel):
    lead: str = Field(
        description="One sentence a reader could hear at the top of the hour: "
        "the single most important thing happening in the world right now."
    )
    entries: list[BulletinEntry]


# --------------------------------------------------------------------------- #
# 10 · standards_critic
# --------------------------------------------------------------------------- #

class StandardsReview(BaseModel):
    """The critic's findings. Approval itself is a *tool call*, not this field.

    `approved` here is what the model asserts; `EditorialContext.approved` is
    what it actually did. They are compared in `newsroom.py`, and the tool wins.
    A model that writes approved=True without calling `approve_bulletin` has not
    approved anything.
    """

    approved: bool
    defects: list[str] = Field(
        description="Each entry names the cluster_id and the specific problem."
    )
    required_fixes: list[str] = Field(
        description="Instructions to the bulletin editor, one per defect. Empty when approved."
    )
