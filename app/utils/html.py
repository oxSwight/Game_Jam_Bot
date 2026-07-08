import html as _html


def safe(text: str | None) -> str:
    """Escape HTML special characters in user-supplied strings.

    Always call this before interpolating any user input into HTML-mode
    Telegram messages. Prevents injection of <tags>, links, and bold/italic
    formatting crafted by malicious nicknames or emails.
    """
    return _html.escape(text or "")


def join_with_other(items: list[str], other: str | None) -> str:
    """Render a multi-select list as an HTML-safe, comma-joined string,
    substituting the free-text value for the 'Other' entry. Returns '-' if empty.
    """
    rendered = [safe(other) if (item == "Other" and other) else safe(item) for item in items]
    return ", ".join(rendered) or "-"
