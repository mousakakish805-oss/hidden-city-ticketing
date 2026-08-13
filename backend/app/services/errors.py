"""Turning internal failures into something a visitor can act on.

Two audiences, two messages, and conflating them is a real fault:

* The **operator** needs the exception type, the vendor, and the fix. That
  belongs in the log and in the database row.
* The **visitor** needs to know whether to wait, retry, or change their
  search. They cannot act on "RapidAPI monthly quota is exhausted", and
  telling them to set an environment variable on a server they do not own is
  noise at best -- at worst it leaks how the service is built.

So the technical text is recorded, and a translated, plain-language message is
what reaches the browser.
"""

from __future__ import annotations

from app.i18n import DEFAULT_LANGUAGE, translate
from app.providers.base import ProviderError

# Matched case-insensitively against the exception text, best-fit first.
_SIGNATURES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("quota is exhausted", "quota exhausted", "0 requests remaining"), "error.quota"),
    (("rate limited", "too many requests"), "error.busy"),
    (("no flights found",), "error.noFlights"),
    (("token", "credentials", "unauthorized", "not subscribed", "api key"), "error.misconfigured"),
    (("timed out", "timeout", "transport error"), "error.unreachable"),
)


def user_facing_message(exc: Exception, lang: str = DEFAULT_LANGUAGE) -> str:
    """A message worth showing a visitor, in their language."""
    text = str(exc).lower()

    for needles, key in _SIGNATURES:
        if any(needle in text for needle in needles):
            return translate(key, lang)

    if isinstance(exc, ProviderError):
        return translate("error.unreachable", lang)
    return translate("error.unexpected", lang)


def operator_detail(exc: Exception) -> str:
    """The full technical text, for logs and the stored search row."""
    return f"{type(exc).__name__}: {exc}"
