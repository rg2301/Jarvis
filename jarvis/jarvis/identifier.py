"""Speaker-identification via Resemblyzer voiceprints."""

from __future__ import annotations

import time
from pathlib import Path

from .config import Config, log


class VoiceIdentifier:
    VOICEPRINT_FILE = "jarvis_voiceprint.npy"
    SAMPLE_RATE     = 16000
    RECORD_SECONDS  = 8        # Longer enrollment → denser, more stable voiceprint.

    # Class-level threshold defaults; instance reads from Config so they're tunable.
    @property
    def THRESHOLD(self) -> float:
        return Config.VOICE_OWNER_THRESHOLD

    @property
    def UNCLEAR_FLOOR(self) -> float:
        return Config.VOICE_UNCLEAR_THRESHOLD

    def __init__(self) -> None:
        self.enabled    = False
        self.encoder    = None
        self.voiceprint = None
        self.np         = None
        self._setup()

    def _setup(self) -> None:
        try:
            from resemblyzer import VoiceEncoder
            import numpy as np

            self.encoder = VoiceEncoder()
            self.np      = np
            self.enabled = True
            log.info("Voice identifier ready.")

            if Path(self.VOICEPRINT_FILE).exists():
                self.voiceprint = np.load(self.VOICEPRINT_FILE)
                log.info("Voiceprint loaded from file.")
            else:
                log.info("No voiceprint found — will enroll on first run.")
        except Exception as e:
            log.warning(
                f"Voice identifier unavailable: {e}. "
                f"Run: pip install resemblyzer sounddevice"
            )
            self.enabled = False

    def enroll(self, voice_engine) -> bool:
        if not self.enabled:
            return False
        try:
            import sounddevice as sd
            from resemblyzer import preprocess_wav

            voice_engine.speak(
                f"I don't recognise your voice yet, {Config.USER_NAME}. "
                f"Please say your name and a few sentences about yourself "
                f"so I can learn your voice. Recording in 3 seconds."
            )
            time.sleep(3)
            voice_engine.speak("Recording now — please speak.")

            audio = sd.rec(
                int(self.RECORD_SECONDS * self.SAMPLE_RATE),
                samplerate=self.SAMPLE_RATE,
                channels=1,
                dtype="float32",
            )
            sd.wait()
            audio = audio.flatten()

            wav        = preprocess_wav(audio, self.SAMPLE_RATE)
            embedding  = self.encoder.embed_utterance(wav)
            self.np.save(self.VOICEPRINT_FILE, embedding)
            self.voiceprint = embedding

            voice_engine.speak(
                f"Voiceprint saved. I'll recognise you from now on, {Config.USER_NAME}."
            )
            log.info("Voiceprint enrolled and saved.")
            return True
        except Exception as e:
            log.error(f"Enrollment error: {e}")
            return False

    def identify(self, audio_data: bytes) -> str:
        """Return 'owner', 'unknown', or 'unclear'. Fails safe to 'owner'."""
        if not self.enabled or self.voiceprint is None:
            return "owner"
        try:
            import io
            import soundfile as sf
            from resemblyzer import preprocess_wav

            audio_np, sr = sf.read(io.BytesIO(audio_data), dtype="float32")
            if len(audio_np.shape) > 1:
                audio_np = audio_np[:, 0]

            wav        = preprocess_wav(audio_np, sr)
            embedding  = self.encoder.embed_utterance(wav)
            similarity = self.np.dot(embedding, self.voiceprint) / (
                self.np.linalg.norm(embedding) * self.np.linalg.norm(self.voiceprint)
            )
            log.info(
                f"Voice similarity score: {similarity:.2f} "
                f"(owner≥{self.THRESHOLD}, unclear≥{self.UNCLEAR_FLOOR})"
            )

            if similarity >= self.THRESHOLD:
                return "owner"
            if similarity >= self.UNCLEAR_FLOOR:
                return "unclear"
            return "unknown"
        except Exception as e:
            log.error(f"Voice identification error: {e}")
            return "owner"

    def delete_voiceprint(self) -> None:
        try:
            if Path(self.VOICEPRINT_FILE).exists():
                Path(self.VOICEPRINT_FILE).unlink()
            self.voiceprint = None
            log.info("Voiceprint deleted.")
        except Exception as e:
            log.error(f"Delete voiceprint error: {e}")
