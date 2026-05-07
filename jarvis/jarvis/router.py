"""Tiny fast-path for control-flow phrases that should never round-trip to Claude.

Anything that's a real command (open X, play Y, weather, timer, etc.) goes
through the LLM tool-use loop in :mod:`jarvis.brain`. This router only handles
session-control phrases where latency matters most.
"""

from __future__ import annotations

# Sentinel constants returned to the main loop.
STOP  = "__STOP__"     # interrupt current speech, stay awake
SLEEP = "__SLEEP__"    # back to wake-word standby
EXIT  = "__EXIT__"     # quit Jarvis entirely


_STOP_PHRASES = (
    "stop", "cancel", "be quiet", "shut up", "enough", "silence",
)
_SLEEP_PHRASES = (
    "go to sleep", "sleep now", "stand by", "standby",
    "go sleep", "sleep mode", "you can sleep", "rest now",
    "go to bed", "back to sleep", "take a nap",
)
_EXIT_PHRASES = (
    "goodbye", "bye", "shut down jarvis", "exit", "quit",
    "turn off jarvis", "power off",
)


def fast_route(text: str) -> str | None:
    """Return STOP/SLEEP/EXIT if `text` matches a control phrase, else None."""
    if not text:
        return None
    t = text.lower().strip()

    # Treat single-word "sleep" specially so it doesn't fire on "sleepless".
    words = t.split()
    if t in _STOP_PHRASES or (len(words) == 1 and words[0] in _STOP_PHRASES):
        return STOP
    if any(p in t for p in _SLEEP_PHRASES) or t == "sleep":
        return SLEEP
    if any(p in t for p in _EXIT_PHRASES):
        return EXIT
    return None
