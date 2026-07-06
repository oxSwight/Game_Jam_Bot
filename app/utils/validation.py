"""Input hardening shared across the registration free-text steps."""

import re

# Matches an explicit http/https URL, a bare www. host, or a Telegram link. It
# deliberately does NOT flag "@handles": the email step legitimately contains an
# @, and the spec only bars actual links (http/https). Any hit resets the flow.
_URL_RE = re.compile(
    r"(https?://|www\.|t\.me/|telegram\.me/)",
    re.IGNORECASE,
)


def contains_url(text: str | None) -> bool:
    """True if the text carries anything link-shaped (http/https, www., t.me).
    Free-text registration answers with a link are treated as spam."""
    if not text:
        return False
    return _URL_RE.search(text) is not None
