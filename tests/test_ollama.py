"""Local-backend tests. No network: urlopen is monkeypatched."""

import json
import urllib.error
import urllib.request

import pytest

from ragstack import config, llm, ollama, retrieve
from ragstack.errors import LocalModelError
from ragstack.store import SearchHit


@pytest.fixture(autouse=True)
def local_backend(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "ollama")


def hit(text="Friday deploys are blocked.", source="deploy-policy.md", ordinal=0, score=0.8):
    return SearchHit(score=score, text=text, source=source, ordinal=ordinal, id=f"x{ordinal}")


# --- context budgeting -------------------------------------------------------
# A local window is small and pre-allocated, so passages have to be budgeted
# before the call rather than truncated by the server after it.


def test_all_passages_kept_when_they_fit():
    hits = [hit(text="short", ordinal=i) for i in range(5)]

    kept, dropped = ollama.fit_hits(hits, overhead_chars=500, num_ctx=4096, num_predict=1024)

    assert kept == hits
    assert dropped == 0


def test_weakest_passages_are_dropped_first():
    """Hits arrive best-first, so trimming from the tail sheds the least."""
    hits = [hit(text="x" * 2000, ordinal=i, score=0.9 - i / 10) for i in range(5)]

    kept, dropped = ollama.fit_hits(hits, overhead_chars=500, num_ctx=4096, num_predict=1024)

    assert 0 < len(kept) < 5
    assert dropped == 5 - len(kept)
    assert [h.ordinal for h in kept] == list(range(len(kept)))


def test_single_oversized_passage_is_truncated_not_dropped():
    """Answering from the best passage beats refusing to answer."""
    kept, dropped = ollama.fit_hits(
        [hit(text="y" * 100_000)], overhead_chars=200, num_ctx=4096, num_predict=1024
    )

    assert len(kept) == 1
    assert dropped == 0
    assert "truncated" in kept[0].text
    assert len(kept[0].text) < 100_000


def test_no_room_at_all_is_a_clear_error():
    with pytest.raises(LocalModelError, match="Raise RAGSTACK_OLLAMA_NUM_CTX"):
        ollama.fit_hits([hit()], overhead_chars=10, num_ctx=512, num_predict=512)


def test_empty_hits_are_not_an_error():
    assert ollama.fit_hits([], overhead_chars=10, num_ctx=4096, num_predict=256) == ([], 0)


# --- error mapping -----------------------------------------------------------


def test_missing_model_says_how_to_pull_it():
    exc = ollama._as_local_error(
        json.dumps({"error": 'model "llama3.2:3b" not found, try pulling it first'}),
        404,
        model="llama3.2:3b",
        num_ctx=4096,
    )

    assert "ollama pull llama3.2:3b" in str(exc)


def test_kv_cache_failure_points_at_the_context_setting_not_the_install():
    """The failure mode that looks exactly like a broken install: the KV cache
    is sized for the whole window at load time, so it is a RAM ceiling."""
    exc = ollama._as_local_error(
        json.dumps({"error": "failed to allocate buffer for kv cache"}),
        500,
        model="llama3.2:3b",
        num_ctx=131072,
    )
    text = str(exc)

    assert "RAGSTACK_OLLAMA_NUM_CTX" in text
    assert "reinstalling will not change it" in text


def test_unrecognised_error_is_passed_through_verbatim():
    exc = ollama._as_local_error("something odd", 503, model="m", num_ctx=4096)

    assert "HTTP 503" in str(exc)
    assert "something odd" in str(exc)


def test_unreachable_server_explains_how_to_start_it(monkeypatch):
    def refuse(*a, **k):
        raise urllib.error.URLError("[WinError 10061] connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)

    with pytest.raises(LocalModelError, match="ollama serve"):
        ollama.chat("q", system="s")


def test_probe_reports_unreachable_rather_than_raising(monkeypatch):
    def refuse(*a, **k):
        raise urllib.error.URLError("nope")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)

    assert ollama.probe()["reachable"] is False


# --- the streamed call -------------------------------------------------------


def test_chat_streams_deltas_and_reports_usage(monkeypatch):
    sent = _fake_stream(
        monkeypatch,
        [
            {"message": {"content": "Not "}, "done": False},
            {"message": {"content": "on Friday."}, "done": False},
            {
                "done": True,
                "done_reason": "stop",
                "model": "llama3.2:3b",
                "prompt_eval_count": 310,
                "eval_count": 12,
            },
        ],
    )

    seen = []
    result = ollama.chat("question", system="rules", on_text=seen.append)

    assert seen == ["Not ", "on Friday."]
    assert result["text"] == "Not on Friday."
    assert result["usage"] == {"input_tokens": 310, "output_tokens": 12}
    assert result["done_reason"] == "stop"

    payload = json.loads(sent[0].data)
    assert payload["stream"] is True
    assert payload["options"]["num_ctx"] == config.OLLAMA_NUM_CTX
    assert payload["messages"][0] == {"role": "system", "content": "rules"}


def test_mid_stream_error_frame_is_raised(monkeypatch):
    """A failure can arrive as a frame inside an otherwise-200 response."""
    _fake_stream(monkeypatch, [{"error": "failed to allocate buffer for kv cache"}])

    with pytest.raises(LocalModelError, match="RAGSTACK_OLLAMA_NUM_CTX"):
        ollama.chat("question", system="rules")


def test_blank_lines_do_not_break_the_stream(monkeypatch):
    _fake_stream(
        monkeypatch,
        [{"message": {"content": "ok"}, "done": False}, {"done": True, "done_reason": "stop"}],
        interleave_blanks=True,
    )

    assert ollama.chat("q", system="s")["text"] == "ok"


# --- answer() over the local backend -----------------------------------------


def test_answer_routes_to_the_local_backend(monkeypatch):
    monkeypatch.setattr(retrieve, "search", lambda *a, **k: [hit()])
    monkeypatch.setattr(
        ollama,
        "chat",
        lambda *a, **k: {
            "text": "  Not on Friday. [1]  ",
            "model": "llama3.2:3b",
            "done_reason": "stop",
            "usage": {"input_tokens": 300, "output_tokens": 9},
        },
    )

    result = llm.answer("When can I deploy?")

    assert result.answer == "Not on Friday. [1]"
    assert result.model == "llama3.2:3b"
    assert result.citations == ["deploy-policy.md#chunk0"]
    # Normalised to the Anthropic vocabulary so callers stay backend-agnostic.
    assert result.stop_reason == "end_turn"


def test_local_truncation_is_flagged_like_the_api_one(monkeypatch):
    monkeypatch.setattr(retrieve, "search", lambda *a, **k: [hit()])
    monkeypatch.setattr(
        ollama,
        "chat",
        lambda *a, **k: {
            "text": "partial",
            "model": "llama3.2:3b",
            "done_reason": "length",
            "usage": {},
        },
    )

    result = llm.answer("q")

    assert "truncated" in result.answer
    assert result.stop_reason == "max_tokens"


def test_citations_match_what_the_model_was_shown(monkeypatch):
    """Passages dropped to fit the window must not be cited as sources."""
    monkeypatch.setattr(
        retrieve, "search", lambda *a, **k: [hit(text="z" * 3000, ordinal=i) for i in range(5)]
    )
    captured = {}

    def fake_chat(prompt, **kwargs):
        captured["prompt"] = prompt
        return {
            "text": "answer",
            "model": "llama3.2:3b",
            "done_reason": "stop",
            "usage": {},
        }

    monkeypatch.setattr(ollama, "chat", fake_chat)

    result = llm.answer("q")

    assert len(result.hits) < 5
    assert "left out to fit" in result.answer
    assert captured["prompt"].count("source:") == len(result.hits)
    for citation in result.citations:
        assert citation in captured["prompt"]


def test_no_hits_short_circuits_before_touching_the_server(monkeypatch):
    monkeypatch.setattr(retrieve, "search", lambda *a, **k: [])

    def explode(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("the local model must not be called with nothing retrieved")

    monkeypatch.setattr(ollama, "chat", explode)

    result = llm.answer("anything")

    assert result.stop_reason == "no_context"
    assert result.model == config.OLLAMA_MODEL, "should name the backend that would have run"


def test_unknown_backend_is_rejected_with_the_valid_names():
    with pytest.raises(ValueError, match="anthropic, ollama"):
        llm.answer("q", backend="gpt")


def test_backend_argument_overrides_configuration(monkeypatch):
    """`--backend anthropic` must reach Claude even when .env says otherwise."""
    monkeypatch.setattr(retrieve, "search", lambda *a, **k: [hit()])
    monkeypatch.setattr(ollama, "chat", lambda *a, **k: pytest.fail("wrong backend"))

    class _Messages:
        def stream(self, **kwargs):
            # What the SDK raises with no credential anywhere.
            raise TypeError("Could not resolve authentication method. Expected one of api_key")

    monkeypatch.setattr(llm, "build_client", lambda: type("C", (), {"messages": _Messages()})())

    with pytest.raises(llm.MissingCredentialsError):
        llm.answer("q", backend="anthropic")


# --- fakes -------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._lines)


def _fake_stream(monkeypatch, events, *, interleave_blanks=False):
    """Install a urlopen that replays `events` as NDJSON. Returns the list the
    intercepted Request objects land in, for asserting on the payload."""
    lines = []
    for event in events:
        lines.append(json.dumps(event).encode("utf-8") + b"\n")
        if interleave_blanks:
            lines.append(b"\n")

    sent = []

    def fake_urlopen(request, timeout=None):
        sent.append(request)
        return _FakeResponse(lines)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return sent
