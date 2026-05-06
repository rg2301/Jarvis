"""Text-to-speech with Edge / ElevenLabs / pyttsx3 backends."""

from __future__ import annotations

import os
import platform
import subprocess
import threading
import time
from pathlib import Path

import requests

try:
    import pyttsx3
except ImportError as e:
    raise SystemExit(f"[ERROR] Missing dependency: {e}. pip install -r requirements.txt")

from .config import Config, log


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
        print(f"\n  Jarvis: {text}\n")
        with self._lock:
            self._done.clear()
            try:
                if Config.USE_ELEVENLABS:
                    self._elevenlabs_speak(text, stop_event)
                else:
                    self._edge_speak(text, stop_event)
            finally:
                self._done.set()

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

    def _edge_speak(self, text: str, stop_event=None) -> None:
        try:
            import asyncio
            import edge_tts

            path = "_tts_edge.mp3"

            async def _generate():
                await edge_tts.Communicate(text, self.edge_voice).save(path)

            asyncio.run(_generate())
            if stop_event and stop_event.is_set():
                return
            self._play_file(path, stop_event)
        except Exception as e:
            log.warning(f"Edge TTS failed: {e}. Using pyttsx3.")
            self._local_speak(text, stop_event)

    def _elevenlabs_speak(self, text: str, stop_event=None) -> None:
        try:
            url = (
                f"https://api.elevenlabs.io/v1/text-to-speech/"
                f"{Config.ELEVENLABS_VOICE_ID}/stream"
            )
            r = requests.post(
                url,
                headers={
                    "xi-api-key": Config.ELEVENLABS_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_turbo_v2",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
                },
                timeout=30,
                stream=True,
            )
            if r.status_code != 200:
                log.warning(f"ElevenLabs {r.status_code}, falling back.")
                self._edge_speak(text, stop_event)
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
            self._edge_speak(text, stop_event)
        except Exception as e:
            log.error(f"ElevenLabs error: {e}. Falling back.")
            self._edge_speak(text, stop_event)
