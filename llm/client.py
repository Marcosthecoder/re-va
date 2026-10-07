"""Thin Anthropic SDK wrapper used by intake, reports, and coach.

Every call is logged (purpose, model, truncated prompt/response) via
db.models.LLMCallLog. This module never computes a financial number — it's
only ever used to extract text into structured fields or to explain numbers
the underwriting engine already produced.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from db.models import LLMCallLog

load_dotenv()

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
_EXCERPT_LIMIT = 4000


class LLMNotConfigured(RuntimeError):
    """Raised when ANTHROPIC_API_KEY isn't set. Callers should catch this and
    show a friendly "add your API key" message instead of letting it crash."""


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _get_client():
    if not is_configured():
        raise LLMNotConfigured(
            "ANTHROPIC_API_KEY is not set. Add it to .env to enable document extraction, "
            "plain-English explanations, and the coach chat. See README.md for how to get a key."
        )
    import anthropic  # imported lazily so Phase 1 code paths never require the package

    default_headers = {}
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    if workspace_id:
        default_headers["anthropic-workspace-id"] = workspace_id

    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], default_headers=default_headers or None)


def log_call(session: Session, purpose: str, model: str, prompt: str, response: str, deal_id: int | None = None) -> None:
    session.add(
        LLMCallLog(
            purpose=purpose,
            model=model,
            prompt_excerpt=prompt[:_EXCERPT_LIMIT],
            response_excerpt=response[:_EXCERPT_LIMIT],
            deal_id=deal_id,
        )
    )
    session.commit()


def call_claude(
    purpose: str,
    user_message: str,
    system: str | None = None,
    session: Session | None = None,
    deal_id: int | None = None,
    max_tokens: int = 1500,
    model: str | None = None,
) -> str:
    """Send one message to Claude, log it if a session is given, and return the text reply.

    Raises LLMNotConfigured if no API key is set. Callers in the Streamlit app
    should catch that and render a setup hint instead of crashing the page.
    """
    client = _get_client()
    model_name = model or DEFAULT_MODEL
    kwargs = {"model": model_name, "max_tokens": max_tokens, "messages": [{"role": "user", "content": user_message}]}
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")

    if session is not None:
        log_call(session, purpose=purpose, model=model_name, prompt=user_message, response=text, deal_id=deal_id)

    return text
