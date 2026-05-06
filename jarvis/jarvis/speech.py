"""Speech-to-text and wake-word detection."""

from __future__ import annotations

import time
from typing import Optional

try:
    import speech_recognition as sr
except ImportError as e:
    raise SystemExit(f"[ERROR] Missing dependency: {e}. pip install -r requirements.txt")

from .config import Config, log


class SpeechRecogniser:
    """One-shot mic listener (used for ad-hoc captures)."""

    def __init__(self) -> None:
        self.recogniser = sr.Recognizer()
        self.recogniser.energy_threshold = 300
        self.recogniser.dynamic_energy_threshold = True
        self.recogniser.pause_threshold = 0.8
        log.info("Speech recogniser ready.")

    def listen(self) -> Optional[str]:
        with sr.Microphone() as source:
            print("  [Listening...]")
            self.recogniser.adjust_for_ambient_noise(source, duration=0.3)
            try:
                audio = self.recogniser.listen(
                    source,
                    timeout=Config.LISTEN_TIMEOUT,
                    phrase_time_limit=Config.PHRASE_LIMIT,
                )
            except sr.WaitTimeoutError:
                return None

        try:
            text = self.recogniser.recognize_google(audio, language="en-IN")
            print(f"  You: {text}")
            log.info(f"Heard: '{text}'")
            return text.strip()
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            log.error(f"Google STT error: {e}")
            return None


class WakeWordDetector:
    """Listens for the wake word ('Jarvis') then captures phrases until idle."""

    SLEEP_AFTER_SECONDS = 20

    def __init__(self) -> None:
        self.recogniser = sr.Recognizer()
        self.recogniser.energy_threshold = 150
        self.recogniser.dynamic_energy_threshold = True
        self.recogniser.dynamic_energy_adjustment_damping = 0.10
        self.recogniser.pause_threshold = 1.0
        self.recogniser.phrase_threshold = 0.1
        self.recogniser.non_speaking_duration = 0.5
        log.info("Wake word active. Say 'Jarvis' to activate.")

    def wait_for_wake_word(self) -> Optional[bytes]:
        print("\n  [Sleeping — say 'Jarvis' to wake me up...]")
        while True:
            try:
                with sr.Microphone() as source:
                    self.recogniser.adjust_for_ambient_noise(source, duration=0.3)
                    audio = self.recogniser.listen(
                        source, timeout=3, phrase_time_limit=3
                    )
                try:
                    text = self.recogniser.recognize_google(
                        audio, language="en-IN"
                    ).lower()
                    log.info(f"Wake word check: '{text}'")
                    if "jarvis" in text:
                        print("  [Jarvis activated!]")
                        return audio.get_wav_data()
                except sr.UnknownValueError:
                    pass
                except sr.RequestError as e:
                    log.warning(f"STT error: {e}")
                    time.sleep(1)
            except sr.WaitTimeoutError:
                pass
            except Exception as e:
                log.error(f"Wake word error: {e}")
                time.sleep(1)

    def listen_phrase(self) -> tuple[Optional[str], Optional[bytes]]:
        try:
            with sr.Microphone() as source:
                self.recogniser.adjust_for_ambient_noise(source, duration=0.2)
                print("  [Listening...]")
                try:
                    self.recogniser.listen(source, timeout=0.2, phrase_time_limit=0.2)
                except Exception:
                    pass
                audio = self.recogniser.listen(
                    source,
                    timeout=self.SLEEP_AFTER_SECONDS,
                    phrase_time_limit=30,
                )
            raw_bytes = audio.get_wav_data()
            text = self.recogniser.recognize_google(audio, language="en-IN").strip()
            print(f"  You: {text}")
            log.info(f"Heard: '{text}'")
            return text, raw_bytes
        except sr.WaitTimeoutError:
            return None, None
        except sr.UnknownValueError:
            return "", None
        except sr.RequestError as e:
            log.warning(f"STT error: {e}")
            return "", None
        except Exception as e:
            log.error(f"listen_phrase error: {e}")
            return "", None

    def cleanup(self) -> None:
        pass
