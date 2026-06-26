import html as _html


def safe(text: str | None) -> str:
    """Escape HTML special characters in user-supplied strings.

    Always call this before interpolating any user input into HTML-mode
    Telegram messages. Prevents injection of <tags>, links, and bold/italic
    formatting crafted by malicious nicknames or emails.
    """
    return _html.escape(text or "")
