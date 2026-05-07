"""Text-to-speech with Edge / ElevenLabs / pyttsx3 backends."""

from __future__ import annotations

import os
import platform
import re
import subprocess
import threading
import time
from pathlib import Path

import requests

# Strip pictographic codepoints before they reach TTS. Some engines (notably
# Edge-TTS) verbalise them — e.g. "🙂" is read aloud as "slightly smiling face".
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"   # emoticons
    "\U0001F300-\U0001F5FF"   # symbols & pictographs
    "\U0001F680-\U0001F6FF"   # transport & map
    "\U0001F700-\U0001F77F"   # alchemical
    "\U0001F780-\U0001F7FF"   # geometric
    "\U0001F800-\U0001F8FF"   # supplemental arrows
    "\U0001F900-\U0001F9FF"   # supplemental symbols
    "\U0001FA00-\U0001FA6F"   # chess / symbols
    "\U0001FA70-\U0001FAFF"   # symbols & pictographs ext-A
    "\U00002700-\U000027BF"   # dingbats
    "\U0001F1E0-\U0001F1FF"   # flag emoji
    "☀-⛿"            # misc symbols
    "⌀-⏿"            # misc technical
    "️"                   # variation selector
    "‍"                   # zero-width joiner
    "]+",
    flags=re.UNICODE,
)
# Markdown noise that some voices spell out as "asterisk", "underscore", etc.
_MARKDOWN_RE = re.compile(r"[*_`#~]+")


def _sanitize_for_speech(text: str) -> str:
    """Remove emojis and stray markdown markers without altering meaning."""
    text = _EMOJI_RE.sub(" ", text)
    text = _MARKDOWN_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


# ── Mood-based prosody ──────────────────────────────────────────────────────
#
# Claude prefixes each reply with one of these mood tags. The voice engine
# strips the tag and applies the matching TTS prosody so the *voice* — not
# just the words — carries the emotion.
#
# Per mood:
#   edge_rate / edge_pitch  → kwargs to edge_tts.Communicate (whole utterance)
#   eleven_stability        → ElevenLabs voice_settings.stability (lower = more variation)
MOODS: dict[str, dict] = {
    "dry":       {"edge_rate": "-2%",  "edge_pitch": "-3Hz", "eleven_stability": 0.55},
    "calm":      {"edge_rate": "-6%",  "edge_pitch": "-4Hz", "eleven_stability": 0.65},
    "amused":    {"edge_rate": "+6%",  "edge_pitch": "+4Hz", "eleven_stability": 0.35},
    "concerned": {"edge_rate": "-8%",  "edge_pitch": "-6Hz", "eleven_stability": 0.55},
    "urgent":    {"edge_rate": "+14%", "edge_pitch": "+6Hz", "eleven_stability": 0.30},
    "curious":   {"edge_rate": "+3%",  "edge_pitch": "+4Hz", "eleven_stability": 0.40},
}
_DEFAULT_MOOD = "dry"
_MOOD_RE = re.compile(r"^\s*\[([a-z_]+)\]\s*", re.IGNORECASE)


def _extract_mood(text: str) -> tuple[str, str]:
    """Pull a leading `[mood]` tag off the text. Unknown moods fall back to the default."""
    m = _MOOD_RE.match(text)
    if not m:
        return _DEFAULT_MOOD, text
    mood = m.group(1).lower()
    rest = text[m.end():]
    return (mood if mood in MOODS else _DEFAULT_MOOD), rest

try:
    import pyttsx3
except ImportError as e:
    raise SystemExit(f"[ERROR] Missing dependency: {e}. pip install -r requirements.txt")

from .config import Config, log
from .events import bus


class VoiceEngine:
    """Edge-TTS by default; falls back to ElevenLabs (if keyed) or pyttsx3."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._done.set()                    # idle = "done"
        self.edge_voice = "en-GB-RyanNeural"

        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", Config.SPEECH_RATE)
        self.engine.setProperty("volume", Config.SPEECH_VOLUME)
        for v in self.engine.getProperty("voices"):
            name = v.name.lower()
            if "male" in name or "david" in name or "daniel" in name:
                self.engine.setProperty("voice", v.id)
                break

        log.info(f"Voice engine ready. ElevenLabs: {Config.USE_ELEVENLABS}")

    @property
    def speaking(self) -> bool:
        return not self._done.is_set()

    # ── Public API ───────────────────────────────────────────────────────────
    def speak(self, text: str, stop_event: threading.Event | None = None) -> None:
        if not text or not text.strip():
            return
        mood, text = _extract_mood(text)
        spoken = _sanitize_for_speech(text)
        if not spoken:
            return
        # Print what we'll actually say (clean), but flag the mood so logs are debuggable.
        print(f"\n  Jarvis [{mood}]: {spoken}\n")
        bus.emit("speak_start", text=spoken, mood=mood)
        with self._lock:
            self._done.clear()
            try:
                if Config.USE_ELEVENLABS:
                    self._elevenlabs_speak(spoken, mood, stop_event)
                else:
                    self._edge_speak(spoken, mood, stop_event)
            finally:
                self._done.set()
                bus.emit("speak_end")

    def wait_until_done(self, settle: float = 0.2) -> None:
        self._done.wait()
        if settle > 0:
            time.sleep(settle)

    # ── Backends ─────────────────────────────────────────────────────────────
    def _local_speak(self, text: str, stop_event=None) -> None:
        try:
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            log.error(f"pyttsx3 error: {e}")

    def _play_file(self, path: str, stop_event: threading.Event | None) -> None:
        system = platform.system()
        if system == "Darwin":
            cmd = ["afplay", path]
        elif system == "Windows":
            abs_path = os.path.abspath(path)
            cmd = [
                "powershell", "-NoProfile", "-Command",
                f"(New-Object Media.SoundPlayer '{abs_path}').PlaySync()",
            ]
        else:
            cmd = ["mpg123", "-q", path]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError as e:
            log.warning(f"Audio player missing ({cmd[0]}): {e}")
            return

        while proc.poll() is None:
            if stop_event and stop_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except Exception:
                    proc.kill()
                return
            time.sleep(0.05)

    def _edge_speak(self, text: str, mood: str = _DEFAULT_MOOD, stop_event=None) -> None:
        try:
            import asyncio
            import edge_tts

            path = "_tts_edge.mp3"
            params = MOODS.get(mood, MOODS[_DEFAULT_MOOD])

            async def _generate():
                await edge_tts.Communicate(
                    text,
                    self.edge_voice,
                    rate=params["edge_rate"],
                    pitch=params["edge_pitch"],
                ).save(path)

            asyncio.run(_generate())
            if stop_event and stop_event.is_set():
                return
            self._play_file(path, stop_event)
        except Exception as e:
            log.warning(f"Edge TTS failed: {e}. Using pyttsx3.")
            self._local_speak(text, stop_event)

    def _elevenlabs_speak(
        self,
        text: str,
        mood: str = _DEFAULT_MOOD,
        stop_event=None,
    ) -> None:
        try:
            url = (
                f"https://api.elevenlabs.io/v1/text-to-speech/"
                f"{Config.ELEVENLABS_VOICE_ID}/stream"
            )
            stability = MOODS.get(mood, MOODS[_DEFAULT_MOOD])["eleven_stability"]
            r = requests.post(
                url,
                headers={
                    "xi-api-key": Config.ELEVENLABS_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_turbo_v2",
                    "voice_settings": {
                        "stability": stability,
                        "similarity_boost": 0.8,
                    },
                },
                timeout=30,
                stream=True,
            )
            if r.status_code != 200:
                log.warning(f"ElevenLabs {r.status_code}, falling back.")
                self._edge_speak(text, mood, stop_event)
                return

            audio_file = Path("_tts_temp.mp3")
            with open(audio_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=4096):
                    if chunk:
                        f.write(chunk)
            if stop_event and stop_event.is_set():
                return
            self._play_file(str(audio_file), stop_event)
        except requests.exceptions.Timeout:
            log.warning("ElevenLabs timed out, falling back.")
            self._edge_speak(text, mood, stop_event)
        except Exception as e:
            log.error(f"ElevenLabs error: {e}. Falling back.")
            self._edge_speak(text, mood, stop_event)
