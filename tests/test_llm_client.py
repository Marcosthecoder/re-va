"""Tests for llm.client: config detection, call logging, and the
LLMNotConfigured guard. No real network calls are made."""
from __future__ import annotations

from db.models import LLMCallLog
from llm.client import LLMNotConfigured, call_claude, is_configured, log_call


def test_is_configured_false_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert is_configured() is False


def test_is_configured_true_with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-for-test")
    assert is_configured() is True


def test_call_claude_raises_llm_not_configured_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    try:
        call_claude(purpose="test", user_message="hello")
        assert False, "expected LLMNotConfigured"
    except LLMNotConfigured as e:
        assert "ANTHROPIC_API_KEY" in str(e)


def test_log_call_writes_truncated_excerpt(db_session):
    long_prompt = "x" * 10_000
    log_call(db_session, purpose="test_purpose", model="claude-sonnet-5-5", prompt=long_prompt, response="short reply", deal_id=None)
    rows = db_session.query(LLMCallLog).all()
    assert len(rows) == 1
    assert rows[0].purpose == "test_purpose"
    assert len(rows[0].prompt_excerpt) <= 4000
    assert rows[0].response_excerpt == "short reply"


def test_log_call_associates_with_deal_id(db_session):
    log_call(db_session, purpose="test", model="m", prompt="p", response="r", deal_id=42)
    row = db_session.query(LLMCallLog).one()
    assert row.deal_id == 42
