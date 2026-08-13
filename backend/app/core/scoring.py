"""Execution-risk model for a hidden-city candidate.

A cheaper price is only half the answer. The other half is whether the
passenger can actually *execute* the plan, and the dominant failure mode is not
the price -- it is being rerouted around B.

An itinerary A -> X -> B -> C only delivers you to B if the airline flies the
schedule it sold. After an irregular operation the carrier will rebook you to
C by any path, and it has no idea you cared about B. The more legs that sit
*before* B, the more chances there are for that to happen. An itinerary whose
very first arrival is B is therefore dramatically safer than one that connects
first, and the score reflects that above everything else.

Flags carry a **code plus parameters**, never a rendered sentence: the same
assessment has to be presentable in any language, and the database stores the
codes so old findings stay readable whatever the caller's locale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.i18n import DEFAULT_LANGUAGE, translate

Severity = Literal["critical", "warning", "info"]

# Starts below 100 so the bonus for a first-leg arrival stays visible instead of
# being clipped away, which would flatten the gap against riskier structures.
BASE_SCORE = 92.0

# A return leg makes the itinerary unusable rather than merely risky, so it caps
# the result outright instead of subtracting from it.
NOT_ONE_WAY_CEILING = 20


@dataclass(frozen=True, slots=True)
class RiskFlag:
    code: str
    severity: Severity
    params: dict[str, Any] = field(default_factory=dict)

    def message(self, lang: str = DEFAULT_LANGUAGE) -> str:
        return translate(f"risk.{self.code}", lang, **self.params)

    def to_dict(self, lang: str = DEFAULT_LANGUAGE) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message(lang),
        }


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    confidence: int
    band: Literal["high", "medium", "low"]
    flags: tuple[RiskFlag, ...]

    def to_dict(self, lang: str = DEFAULT_LANGUAGE) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "band": self.band,
            "flags": [flag.to_dict(lang) for flag in self.flags],
        }


def _band(confidence: int) -> Literal["high", "medium", "low"]:
    if confidence >= 80:
        return "high"
    if confidence >= 55:
        return "medium"
    return "low"


def assess(
    *,
    deplane_index: int,
    total_segments: int,
    layover_minutes: int | None,
    savings_percent: float,
    bookable_seats: int | None,
    is_one_way: bool,
    deplane_city: str,
    ticketed_city: str,
) -> RiskAssessment:
    """Score how safely a hidden-city itinerary can be executed (0-100)."""
    score = BASE_SCORE
    flags: list[RiskFlag] = []
    cities = {"deplane_city": deplane_city, "ticketed_city": ticketed_city}

    # -- always true of hidden-city ticketing -----------------------------
    flags.append(RiskFlag("CARRY_ON_ONLY", "critical", dict(cities)))
    flags.append(RiskFlag("ONE_WAY_ONLY", "critical"))
    flags.append(RiskFlag("CONTRACT_OF_CARRIAGE", "warning"))
    flags.append(RiskFlag("NO_LOYALTY_NUMBER", "warning"))

    # -- the dominant risk: getting rerouted around B ----------------------
    if deplane_index == 0:
        score += 8
        flags.append(RiskFlag("DIRECT_FIRST_LEG", "info", dict(cities)))
    else:
        score -= 30 * deplane_index
        flags.append(
            RiskFlag("REROUTE_RISK", "critical", {**cities, "deplane_index": deplane_index})
        )

    remaining_legs = total_segments - deplane_index - 1
    if remaining_legs > 1:
        score -= 5

    # -- connection timing ---------------------------------------------------
    if layover_minutes is not None:
        if layover_minutes < 45:
            score -= 8
            flags.append(
                RiskFlag(
                    "TIGHT_CONNECTION", "info", {**cities, "layover_minutes": layover_minutes}
                )
            )
        elif layover_minutes > 300:
            flags.append(
                RiskFlag(
                    "LONG_LAYOVER", "info", {**cities, "layover_hours": layover_minutes // 60}
                )
            )

    # -- price quality -------------------------------------------------------
    if savings_percent < 10:
        score -= 15
        flags.append(RiskFlag("MARGINAL_SAVINGS", "info"))

    if bookable_seats is not None and bookable_seats <= 2:
        score -= 5
        flags.append(RiskFlag("LOW_AVAILABILITY", "info", {"bookable_seats": bookable_seats}))

    if not is_one_way:
        flags.append(RiskFlag("NOT_ONE_WAY", "critical"))

    # -- border formalities --------------------------------------------------
    flags.append(RiskFlag("IMMIGRATION", "warning", dict(cities)))

    confidence = int(max(0.0, min(100.0, score)))
    if not is_one_way:
        confidence = min(confidence, NOT_ONE_WAY_CEILING)
    return RiskAssessment(confidence=confidence, band=_band(confidence), flags=tuple(flags))
