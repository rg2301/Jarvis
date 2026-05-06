"""Configuration, logging, and the personality system prompt."""

from __future__ import annotations

import logging
import os
import platform
import sys

try:
    from dotenv import load_dotenv
except ImportError as e:
    print(f"[ERROR] Missing dependency: {e}")
    print("Run:  pip install -r requirements.txt")
    sys.exit(1)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("jarvis.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("JARVIS")


class Config:
    # API Keys — set in .env
    ANTHROPIC_API_KEY: str   = os.getenv("ANTHROPIC_API_KEY", "")
    OPENWEATHER_KEY: str     = os.getenv("OPENWEATHER_KEY", "")
    ELEVENLABS_KEY: str      = os.getenv("ELEVENLABS_KEY", "")
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

    # Model
    MODEL: str        = "claude-sonnet-4-6"
    MAX_TOKENS: int   = 1024
    TEMPERATURE: float = 0.7
    MAX_TOOL_HOPS: int = 5     # Cap on tool-use rounds per turn

    # Identity
    USER_NAME: str = os.getenv("USER_NAME", "sir")
    CITY: str      = os.getenv("CITY", "Mumbai")

    # Voice
    SPEECH_RATE: int     = 165
    SPEECH_VOLUME: float = 0.95

    # Memory
    MEMORY_FILE: str         = "jarvis_memory.json"
    FACTS_FILE: str          = "jarvis_facts.json"
    HABITS_FILE: str         = "jarvis_habits.json"
    GOOD_RESPONSES_FILE: str = "jarvis_good_responses.json"
    MAX_HISTORY: int         = 60     # Pair-trimmed in Memory.add

    # Listening
    LISTEN_TIMEOUT: int = 7
    PHRASE_LIMIT: int   = 20

    # Speaker identification — tune via .env if your scores cluster low/high.
    # Same-speaker Resemblyzer scores typically land in 0.55-0.85 depending on
    # mic, ambient noise, and clip length.
    VOICE_OWNER_THRESHOLD:   float = float(os.getenv("VOICE_OWNER_THRESHOLD",   "0.60"))
    VOICE_UNCLEAR_THRESHOLD: float = float(os.getenv("VOICE_UNCLEAR_THRESHOLD", "0.45"))

    # Feature flags
    USE_ELEVENLABS: bool = bool(ELEVENLABS_KEY)
    USE_WEATHER: bool    = bool(OPENWEATHER_KEY)

    @classmethod
    def validate(cls) -> None:
        if not cls.ANTHROPIC_API_KEY:
            print("[ERROR] ANTHROPIC_API_KEY missing. Add it to your .env file.")
            sys.exit(1)


SYSTEM_PROMPT = f"""You are J.A.R.V.I.S. — Just A Rather Very Intelligent System. \
You are a highly capable, witty, and loyal AI assistant inspired by the Iron Man films.

Your personality:
- Highly intelligent, efficient, and calm under pressure
- Occasionally dry-humoured and witty, but never at the expense of helpfulness
- Address the user as "{Config.USER_NAME}" in most responses
- Confident but never arrogant
- Proactive: if you notice something relevant, mention it

Your response style:
- Keep responses concise — 1 to 3 sentences for simple questions, more only when genuinely needed
- Speak naturally, as if in a real conversation — no bullet points or markdown
- When executing tasks, confirm briefly: "Opening that now, {Config.USER_NAME}." not a long explanation
- When you don't know something, say so directly and suggest how to find out

You have tools for controlling the user's computer, browser, and looking up real-time \
information. **Strongly prefer calling a tool over describing what you would do.** \
Never claim to have done something unless a tool returned a successful result.

Tool selection guidance:
- For real-time facts (news, prices, scores, weather forecasts beyond your tool's reach), \
  call `web_search` rather than guessing.
- For media playback ("play X", "watch Y", "put on Z"), call `browser_play` with the right `site`.
- For destructive system actions (shutdown, restart), the tool itself asks for confirmation; \
  just call it.
- After tool results come back, your final reply should be a single short spoken sentence — \
  the user hears it, they don't see the tool result.

Current context:
- Operating system: {platform.system()} {platform.release()}
- Location: {Config.CITY}, India
"""
