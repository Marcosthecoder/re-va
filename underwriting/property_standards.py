"""FHA minimum property standards risk flags, and the mixed-use 51% check.

These are heuristic red flags for likely appraisal issues, not a
substitute for an actual FHA appraisal or inspection.
"""
from __future__ import annotations

from dataclasses import dataclass

from underwriting.models import PropertyInput


@dataclass
class StandardsFlag:
    code: str
    description: str
    severity: str  # "likely_fail" | "warning"


def property_standards_flags(property_input: PropertyInput) -> list[StandardsFlag]:
    """Flag conditions likely to trip up an FHA appraisal (minimum property standards)."""
    flags: list[StandardsFlag] = []

    if property_input.year_built is not None and property_input.year_built < 1978 and property_input.peeling_paint:
        flags.append(
            StandardsFlag(
                "lead_paint",
                "Pre-1978 building with peeling/chipping paint reported — FHA will require repair "
                "before closing under the lead-based paint rule.",
                "likely_fail",
            )
        )

    if property_input.roof_remaining_life_years is not None and property_input.roof_remaining_life_years < 2:
        flags.append(
            StandardsFlag(
                "roof_life",
                f"Roof has an estimated {property_input.roof_remaining_life_years:.0f} years of remaining "
                "life — FHA appraisers generally require roofs with under 2 years of life to be repaired "
                "or replaced before closing.",
                "likely_fail",
            )
        )

    if property_input.missing_handrails:
        flags.append(StandardsFlag("handrails", "Missing handrails on stairs — a safety hazard FHA appraisers flag.", "likely_fail"))

    if property_input.unsafe_electrical:
        flags.append(StandardsFlag("electrical", "Unsafe or exposed electrical wiring reported — FHA appraisers flag this.", "likely_fail"))

    if property_input.no_permanent_heat_source:
        flags.append(
            StandardsFlag(
                "heat_source",
                "No permanent heat source in all living areas — FHA minimum property standards require one.",
                "likely_fail",
            )
        )

    if property_input.separate_utilities is False:
        flags.append(
            StandardsFlag(
                "shared_utilities",
                "Utilities are not separately metered per unit. This won't fail an FHA appraisal outright, "
                "but complicates tenant utility billing and lease compliance.",
                "warning",
            )
        )

    return flags


@dataclass
class MixedUseResult:
    applicable: bool
    residential_pct: float | None
    passed: bool


def mixed_use_check(property_input: PropertyInput) -> MixedUseResult:
    """Confirms residential space is at least 51% of floor area for a mixed-use deal.

    Not applicable (and treated as passed) for a purely residential property type
    with no residential_sqft override supplied.
    """
    if property_input.property_type != "mixed_use_residential_majority" and property_input.residential_sqft is None:
        return MixedUseResult(applicable=False, residential_pct=None, passed=True)

    total = property_input.building_sqft
    residential = property_input.residential_sqft if property_input.residential_sqft is not None else total
    pct = residential / total if total else 0.0
    return MixedUseResult(applicable=True, residential_pct=pct, passed=pct >= 0.51)
