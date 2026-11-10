import json
from types import SimpleNamespace

import pytest

from app.services.ai import client as ai_client
from app.services.ai.client import call_llm, call_llm_cached
from app.services.ai.features import _verified_quotes
from app.services.ai.schemas import DecisionSummary


class FakeQuery:
    def __init__(self, existing):
        self._existing = existing

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._existing


class FakeSession:
    def __init__(self, existing=None):
        self._existing = existing
        self.added: list = []

    def query(self, model):
        return FakeQuery(self._existing)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass


def test_quote_verification_guard_discards_non_exact_quotes():
    notes = "She managed a class of 35 and raised scores by 15 points."
    quotes = [
        "managed a class of 35",  # exact substring -> kept
        "raised test scores by fifteen points",  # paraphrased -> discarded
        "",  # empty -> discarded
    ]
    assert _verified_quotes(quotes, notes) == ["managed a class of 35"]


def test_cache_hit_path_skips_the_llm_call(monkeypatch):
    cached_row = SimpleNamespace(output={"summary": "Cached summary."}, provider="groq", model="llama-3.3-70b")
    db = FakeSession(existing=cached_row)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("call_llm should not be called on a cache hit")

    monkeypatch.setattr(ai_client, "call_llm", fail_if_called)

    result = call_llm_cached(db, "decision_summary", {"x": 1}, "v1", "system", "user", DecisionSummary)

    assert result.cached is True
    assert result.output.summary == "Cached summary."
    assert db.added == []  # nothing new written on a cache hit


def test_cache_miss_calls_llm_and_stores_result(monkeypatch):
    db = FakeSession(existing=None)

    def fake_call_llm(system_prompt, user_prompt, schema):
        return schema(summary="Fresh summary."), "groq", "llama-3.3-70b"

    monkeypatch.setattr(ai_client, "call_llm", fake_call_llm)

    result = call_llm_cached(db, "decision_summary", {"x": 1}, "v1", "system", "user", DecisionSummary)

    assert result.cached is False
    assert result.output.summary == "Fresh summary."
    assert len(db.added) == 1
    assert db.added[0].provider == "groq"
    assert db.added[0].prompt_version == "v1"


def test_provider_fallback_from_groq_to_gemini(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setattr(ai_client.settings, "GEMINI_API_KEY", "fake-gemini-key")

    calls = []

    def fake_chat_with_backoff(base_url, api_key, model, system_prompt, user_prompt):
        calls.append(base_url)
        if "groq" in base_url:
            raise RuntimeError("groq is down")
        return json.dumps({"summary": "From Gemini."})

    monkeypatch.setattr(ai_client, "_chat_with_backoff", fake_chat_with_backoff)

    output, provider, model = call_llm("system", "user", DecisionSummary)

    assert provider == "gemini"
    assert output.summary == "From Gemini."
    assert len(calls) == 2


def test_invalid_json_retries_once_with_validation_error_then_succeeds(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setattr(ai_client.settings, "GEMINI_API_KEY", None)

    calls = []

    def fake_chat(base_url, api_key, model, system_prompt, user_prompt):
        calls.append(user_prompt)
        if len(calls) == 1:
            return json.dumps({"wrong_field": "oops"})  # fails DecisionSummary validation
        return json.dumps({"summary": "Fixed on retry."})

    monkeypatch.setattr(ai_client, "_chat_with_backoff", fake_chat)
    monkeypatch.setattr(ai_client, "_chat", fake_chat)

    output, provider, model = call_llm("system", "user", DecisionSummary)

    assert provider == "groq"
    assert output.summary == "Fixed on retry."
    assert len(calls) == 2
    assert "did not match the required schema" in calls[1]


def test_invalid_json_on_retry_too_moves_to_next_provider(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setattr(ai_client.settings, "GEMINI_API_KEY", "fake-gemini-key")

    def fake_chat_with_backoff(base_url, api_key, model, system_prompt, user_prompt):
        if "groq" in base_url:
            return json.dumps({"wrong_field": "still wrong"})
        return json.dumps({"summary": "Gemini got it right."})

    monkeypatch.setattr(ai_client, "_chat_with_backoff", fake_chat_with_backoff)
    monkeypatch.setattr(ai_client, "_chat", fake_chat_with_backoff)

    output, provider, model = call_llm("system", "user", DecisionSummary)

    assert provider == "gemini"
    assert output.summary == "Gemini got it right."


def test_all_providers_failing_raises_ai_unavailable(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setattr(ai_client.settings, "GEMINI_API_KEY", "fake-gemini-key")
    monkeypatch.setattr(
        ai_client, "_chat_with_backoff", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))
    )

    with pytest.raises(ai_client.AIUnavailableError):
        call_llm("system", "user", DecisionSummary)


def test_no_providers_configured_raises_ai_unavailable(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "GROQ_API_KEY", None)
    monkeypatch.setattr(ai_client.settings, "GEMINI_API_KEY", None)

    with pytest.raises(ai_client.AIUnavailableError):
        call_llm("system", "user", DecisionSummary)
