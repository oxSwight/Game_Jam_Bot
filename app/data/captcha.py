"""Inline emoji CAPTCHA used as the first anti-bot gate before registration.

The user is shown a row of emoji buttons and asked to tap a specific one. A
scripted client that blindly walks the registration flow can't know which emoji
was named in the prompt, so it fails here. The prompt embeds the target emoji
itself (no translation needed), and the correct button is identified by index so
nothing emoji-shaped ends up in callback_data.
"""

from __future__ import annotations

import random

# Visually distinct emojis so the target is unambiguous on any client/font.
CAPTCHA_POOL: tuple[str, ...] = (
    "🚗", "🐶", "🍎", "⚽", "🌳", "⭐", "🔑", "🎈", "🚀", "🎧", "🍔", "🐱",
)

CAPTCHA_CHOICES = 5


def build_captcha() -> tuple[list[str], int]:
    """Return (options, target_index): five distinct emojis and the index of the
    one the user must tap. Caller shows ``options[target_index]`` in the prompt."""
    options = random.sample(CAPTCHA_POOL, CAPTCHA_CHOICES)
    target_index = random.randrange(CAPTCHA_CHOICES)
    return options, target_index
