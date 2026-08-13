"""The canonical operational-risk disclaimer.

Served from the backend rather than hardcoded in the UI so the wording is
versioned, auditable, and identical across every client and language. Bumping
``settings.disclaimer_version`` invalidates all stored acknowledgements and
re-prompts every user.

Structure (which rules exist, their severity, which must be individually
acknowledged) is language-independent and lives here; the prose lives in the
message catalogs.
"""

from __future__ import annotations

from typing import Any, Literal

from app.config import settings
from app.i18n import DEFAULT_LANGUAGE, translate

Severity = Literal["critical", "warning", "info"]

# (code, severity, must be individually ticked before results unlock)
#
# Ordered by how badly getting it wrong hurts, not by topic. The three
# critical rules are the ones that cost you money or a flight home; the rest
# are things travellers reliably fail to consider.
DISCLAIMER_RULES: tuple[tuple[str, Severity, bool], ...] = (
    ("ONE_WAY_ONLY", "critical", True),
    ("CARRY_ON_ONLY", "critical", True),
    ("CONTRACT_OF_CARRIAGE", "critical", True),
    ("REROUTE_RISK", "warning", False),
    ("IMMIGRATION", "warning", False),
    ("NO_LOYALTY_NUMBER", "warning", False),
    ("TRAVEL_INSURANCE", "warning", False),
    ("NO_CHANGES", "warning", False),
    ("PASSENGER_RIGHTS", "info", False),
    ("NOT_ADVICE", "info", False),
)

REQUIRED_CODES: tuple[str, ...] = tuple(
    code for code, _, required in DISCLAIMER_RULES if required
)


def disclaimer_payload(lang: str = DEFAULT_LANGUAGE) -> dict[str, Any]:
    return {
        "version": settings.disclaimer_version,
        "language": lang,
        "title": translate("disclaimer.title", lang),
        "summary": translate("disclaimer.summary", lang),
        "rules": [
            {
                "code": code,
                "severity": severity,
                "required": required,
                "title": translate(f"disclaimer.rule.{code}.title", lang),
                "body": translate(f"disclaimer.rule.{code}.body", lang),
            }
            for code, severity, required in DISCLAIMER_RULES
        ],
        "required_codes": list(REQUIRED_CODES),
    }
