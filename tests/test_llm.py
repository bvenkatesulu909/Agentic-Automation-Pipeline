"""Claude-backend tests. No network: the API boundary is monkeypatched.

The local backend is covered in test_ollama.py.
"""

import anthropic
import httpx
import pytest

from ragstack import config, llm, retrieve
from ragstack.store import SearchHit


@pytest.fixture(autouse=True)
def claude_backend(monkeypatch):
    """Pin the backend for this module.

    `config` reads RAGSTACK_LLM_BACKEND from the environment and from .env, so
    a machine set up to answer locally would otherwise route these through
    Ollama and fail for the wrong reason.
    """
    monkeypatch.setattr(config, "LLM_BACKEND", "anthropic")


def hit(text="Friday deploys are blocked.", source="deploy-policy.md", ordinal=0, score=0.8):
    return SearchHit(score=score, text=text, source=source, ordinal=ordinal, id="x")


# --- credential-error detection ----------------------------------------------
# The SDK reports "no credential configured" as a bare TypeError raised while
# building request headers, so this mapping is what keeps the failure legible.


def test_recognises_sdk_auth_resolution_typeerror():
    exc = TypeError(
        "Could not resolve authentication method. Expected one of api_key, "
        "auth_token, or credentials to be set."
    )
    assert isinstance(llm._as_credentials_error(exc), llm.MissingCredentialsError)


def _auth_error() -> anthropic.AuthenticationError:
    # AuthenticationError needs a real response to read .request off.
    response = httpx.Response(
        401, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    return anthropic.AuthenticationError(message="invalid key", response=response, body=None)


def test_rejected_key_is_not_reported_as_a_missing_one():
    """A 401 means a key was supplied and refused — a different fix than setting one."""
    mapped = llm._as_credentials_error(_auth_error())

    assert isinstance(mapped, llm.InvalidCredentialsError)
    assert not isinstance(mapped, llm.MissingCredentialsError)


def test_rejected_key_message_points_at_the_real_causes():
    text = str(llm._as_credentials_error(_auth_error()))
    assert "rejected" in text.lower()
    assert "revoked" in text.lower(), "should name the usual suspects"
    assert "overrides the .env" in text, "a stale shell variable is the subtle one"


def test_unrelated_typeerror_is_not_swallowed():
    """A real bug in our request kwargs must not masquerade as a missing key."""
    assert llm._as_credentials_error(TypeError("got an unexpected keyword 'effrot'")) is None


def test_credentials_message_mentions_how_to_fix():
    exc = llm._as_credentials_error(TypeError("Could not resolve authentication method."))
    text = str(exc)
    assert "ANTHROPIC_API_KEY" in text
    assert "ragstack search" in text, "should say retrieval still works without a key"
    assert "ollama" in text, "should offer the keyless backend as a way out"


# --- prompt construction -----------------------------------------------------


def test_prompt_carries_passages_and_question():
    prompt = llm.build_prompt("When can I deploy?", [hit()])

    assert "Friday deploys are blocked." in prompt
    assert "When can I deploy?" in prompt
    assert "deploy-policy.md#chunk0" in prompt
    assert "<retrieved_passages>" in prompt


def test_passages_are_numbered_for_citation():
    prompt = llm.build_prompt("q", [hit(text="first"), hit(text="second", ordinal=1)])

    assert "[1]" in prompt and "[2]" in prompt


def test_system_prompt_forbids_ungrounded_answers():
    assert "only the retrieved passages" in llm.SYSTEM_PROMPT
    assert "speculate" in llm.SYSTEM_PROMPT


# --- answer() behaviour ------------------------------------------------------


def test_no_hits_short_circuits_without_calling_the_api(monkeypatch):
    monkeypatch.setattr(retrieve, "search", lambda *a, **k: [])

    def explode(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("the API must not be called when nothing was retrieved")

    monkeypatch.setattr(llm, "build_client", explode)

    result = llm.answer("anything")

    assert result.stop_reason == "no_context"
    assert result.hits == []
    assert "min-score" in result.answer, "should suggest how to widen the search"


def test_empty_question_is_rejected():
    with pytest.raises(ValueError, match="must not be empty"):
        llm.answer("   ")


def test_refusal_is_raised_not_returned_as_text(monkeypatch):
    monkeypatch.setattr(retrieve, "search", lambda *a, **k: [hit()])
    monkeypatch.setattr(llm, "build_client", lambda: _FakeClient(_FakeMessage("refusal")))

    with pytest.raises(llm.ModelRefusalError, match="declined"):
        llm.answer("a question")


def test_truncation_is_flagged_in_the_answer(monkeypatch):
    monkeypatch.setattr(retrieve, "search", lambda *a, **k: [hit()])
    monkeypatch.setattr(
        llm, "build_client", lambda: _FakeClient(_FakeMessage("max_tokens", text="partial"))
    )

    result = llm.answer("a question")

    assert "truncated" in result.answer
    assert result.stop_reason == "max_tokens"


def test_successful_answer_reports_citations_and_usage(monkeypatch):
    monkeypatch.setattr(retrieve, "search", lambda *a, **k: [hit()])
    monkeypatch.setattr(
        llm, "build_client", lambda: _FakeClient(_FakeMessage("end_turn", text="Not on Friday."))
    )

    result = llm.answer("When can I deploy?")

    assert result.answer == "Not on Friday."
    assert result.citations == ["deploy-policy.md#chunk0"]
    assert result.usage == {"input_tokens": 11, "output_tokens": 22}


def test_missing_credentials_surfaces_as_our_error(monkeypatch):
    monkeypatch.setattr(retrieve, "search", lambda *a, **k: [hit()])
    monkeypatch.setattr(
        llm,
        "build_client",
        lambda: _FakeClient(
            raises=TypeError("Could not resolve authentication method. Expected one of api_key")
        ),
    )

    with pytest.raises(llm.MissingCredentialsError, match="ANTHROPIC_API_KEY"):
        llm.answer("a question")


def test_unexpected_typeerror_propagates(monkeypatch):
    monkeypatch.setattr(retrieve, "search", lambda *a, **k: [hit()])
    monkeypatch.setattr(
        llm, "build_client", lambda: _FakeClient(raises=TypeError("bad kwarg 'effrot'"))
    )

    with pytest.raises(TypeError, match="effrot"):
        llm.answer("a question")


# --- fakes -------------------------------------------------------------------


class _FakeBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeUsage:
    input_tokens = 11
    output_tokens = 22


class _FakeMessage:
    def __init__(self, stop_reason, text="answer text"):
        self.stop_reason = stop_reason
        self.content = [_FakeBlock(text)]
        self.model = "claude-opus-5"
        self.usage = _FakeUsage()
        self.stop_details = type("D", (), {"category": "cyber"})()


class _FakeStream:
    def __init__(self, message):
        self._message = message
        self.text_stream = iter(["answer ", "text"])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._message


class _FakeMessages:
    def __init__(self, message, raises):
        self._message = message
        self._raises = raises

    def stream(self, **kwargs):
        if self._raises is not None:
            raise self._raises
        return _FakeStream(self._message)


class _FakeClient:
    def __init__(self, message=None, raises=None):
        self.messages = _FakeMessages(message, raises)
