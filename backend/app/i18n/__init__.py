"""Localisation for server-generated user-facing text.

Most UI copy belongs in the frontend, but three kinds of text are produced
here and must be translated server-side:

* the **disclaimer**, which is versioned and legally load-bearing -- both
  languages have to come from one auditable source;
* **risk messages**, which interpolate live values (city names, layover
  minutes) and so cannot be pre-translated strings in the client;
* **run warnings** raised by the search service.

Scoring and analysis stay language-free: they emit a message *code* plus
parameters, and rendering happens at the API boundary. That also means the
database stores codes, not prose, so stored findings are readable in any
language later.
"""

from __future__ import annotations

import logging
from typing import Literal

from app.i18n.catalog_ar import MESSAGES_AR
from app.i18n.catalog_en import MESSAGES_EN

logger = logging.getLogger(__name__)

Language = Literal["en", "ar"]

DEFAULT_LANGUAGE: Language = "en"
SUPPORTED_LANGUAGES: tuple[Language, ...] = ("en", "ar")
RTL_LANGUAGES: frozenset[str] = frozenset({"ar"})

CATALOGS: dict[str, dict[str, str]] = {"en": MESSAGES_EN, "ar": MESSAGES_AR}


def normalize_language(value: str | None) -> Language:
    """Coerce a query param or Accept-Language header to a supported language.

    Accepts ``ar``, ``ar-JO``, ``ar_SA``, ``en-GB`` and similar; anything
    unrecognised falls back to English rather than failing a request.
    """
    if not value:
        return DEFAULT_LANGUAGE

    # Accept-Language can be "ar-JO,ar;q=0.9,en;q=0.8" -- take the best match.
    for chunk in value.split(","):
        tag = chunk.split(";")[0].strip().replace("_", "-").lower()
        if not tag:
            continue
        primary = tag.split("-")[0]
        if primary in SUPPORTED_LANGUAGES:
            return primary  # type: ignore[return-value]
    return DEFAULT_LANGUAGE


def is_rtl(lang: str) -> bool:
    return lang in RTL_LANGUAGES


def translate(key: str, lang: str = DEFAULT_LANGUAGE, /, **params: object) -> str:
    """Render ``key`` in ``lang``, falling back to English then to the key.

    A missing translation must never break a response, so every failure
    degrades one step instead of raising.
    """
    catalog = CATALOGS.get(lang, MESSAGES_EN)
    template = catalog.get(key)

    if template is None:
        template = MESSAGES_EN.get(key)
        if template is None:
            logger.warning("Missing translation key: %s", key)
            return key

    try:
        return template.format(**params)
    except (KeyError, IndexError):
        logger.warning("Translation key %s is missing a parameter", key)
        return template


def missing_keys(lang: str) -> set[str]:
    """Keys present in English but absent from ``lang``. Used by the tests."""
    return set(MESSAGES_EN) - set(CATALOGS.get(lang, {}))
