"""Shape of a deal-intake extraction result, before the user has corrected it."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ConfidenceLevel = Literal["high", "medium", "low"]


class IntakeResult(BaseModel):
    """Best-effort extraction. ``deal_dict`` may be incomplete or fail PropertyInput
    validation — that's expected; the UI shows it alongside confidence flags so the
    user corrects it before anything is underwritten.
    """

    deal_dict: dict = Field(default_factory=dict)
    confidence: dict[str, ConfidenceLevel] = Field(default_factory=dict)
    unresolved_notes: list[str] = Field(default_factory=list)
    source_excerpt: str = ""

    def confidence_for(self, field_path: str) -> str:
        return self.confidence.get(field_path, "unknown")
