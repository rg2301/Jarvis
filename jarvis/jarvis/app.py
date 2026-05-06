"""Top-level Jarvis main loop. Wires every subsystem together."""

from __future__ import annotations

import datetime
import os
import platform
import sys
import threading
import time
from pathlib import Path

from .browser import BrowserController
from .config import Config, log
from .brain import AIBrain
from .identifier import VoiceIdentifier
from .memory import Memory
from .router import EXIT, SLEEP, STOP, fast_route
from .speech import SpeechRecogniser, WakeWordDetector
from .tools import ToolExecutor
from .voice import VoiceEngine
from .web import WebBrain


class Jarvis:
    def __init__(self) -> None:
        self.running     = False
        self._stop_event = threading.Event()
        self._interaction_count = 0

        log.info("Initialising Jarvis...")
        self.voice      = VoiceEngine()
        self.ears       = SpeechRecogniser()
        self.wake       = WakeWordDetector()
        self.identifier = VoiceIdentifier()
        self.memory     = Memory()
        self.web        = WebBrain()
        self.browser    = BrowserController()

        self.executor   = ToolExecutor(
            voice=self.voice,
            memory=self.memory,
            web=self.web,
            browser=self.browser,
            identifier=self.identifier,
            stop_event=self._stop_event,
        )
        # Inject the listener used for verbal confirmations inside tools.
        self.executor.listener = self.wake

        self.brain = AIBrain(self.executor)
        self.running = True
        log.info("Jarvis fully initialised.")

    # ── Keyboard interrupt listener ──────────────────────────────────────────
    def _setup_keyboard_stop(self) -> None:
        if not sys.stdin.isatty():
            log.info("stdin is not a tty — keyboard stop disabled.")
            return

        def _listen():
            try:
                if platform.system() == "Windows":
                    import msvcrt
                    while self.running:
                        if msvcrt.kbhit():
                            if msvcrt.getch() == b"q":
                                self._stop_event.set()
                        time.sleep(0.05)
                else:
                    import termios
                    import tty
                    fd = sys.stdin.fileno()
                    old = termios.tcgetattr(fd)
                    try:
                        tty.setraw(fd)
                        while self.running:
                            ch = sys.stdin.read(1)
                            if ch == "q":
                                self._stop_event.set()
                                log.info("Stop key pressed.")
                            elif ch == "\x03":
                                self.running = False
                                self._stop_event.set()
                                break
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except Exception as e:
                log.warning(f"Keyboard stop error: {e}")

        threading.Thread(target=_listen, daemon=True).start()

    # ── Main loop ────────────────────────────────────────────────────────────
    def run(self) -> None:
        self._setup_keyboard_stop()
        self._stop_event.clear()

        if self.identifier.enabled and self.identifier.voiceprint is None:
            self.identifier.enroll(self.voice)

        self.voice.speak(
            f"J.A.R.V.I.S. online. All systems nominal. "
            f"Good {self._time_of_day()}, {Config.USER_NAME}. "
            f"Say Jarvis whenever you need me.",
            self._stop_event,
        )
        self.voice.wait_until_done()

        while self.running:
            try:
                wake_audio = self.wake.wait_for_wake_word()

                # ── Speaker check on the wake word ───────────────────────────
                if wake_audio and self.identifier.enabled:
                    speaker = self.identifier.identify(wake_audio)
                    if speaker == "unknown":
                        if not self._handle_guest():
                            continue
                    elif speaker == "unclear":
                        log.warning("Voice unclear — low confidence match.")

                # ── Duck video volume if something is playing ───────────────
                video_was_playing = self.browser._watching
                if video_was_playing:
                    self.browser.duck_volume(20)

                self._stop_event.clear()
                self._announce_proactively()

                # ── Conversation loop ───────────────────────────────────────
                self._converse(video_was_playing)

            except KeyboardInterrupt:
                print("\n  [Ctrl+C — shutting down...]")
                self.running = False
                self._cleanup()
                return
            except Exception as e:
                log.error(f"Main loop error: {e}")
                time.sleep(1)

        self._cleanup()

    # ── Conversation sub-loop (stays awake until timeout/sleep/exit) ─────────
    def _converse(self, video_was_playing: bool) -> None:
        consecutive_empty = 0

        while True:
            user_input, audio_bytes = self.wake.listen_phrase()

            # Timeout — back to wake-word standby.
            if user_input is None:
                self.voice.speak(
                    f"Going to sleep. Say Jarvis when you need me, "
                    f"{Config.USER_NAME}.",
                    self._stop_event,
                )
                self.voice.wait_until_done()
                if video_was_playing:
                    self.browser.restore_volume()
                return

            # Couldn't understand.
            if user_input == "":
                consecutive_empty += 1
                if consecutive_empty >= 4:
                    self.voice.speak(
                        f"I'm having trouble hearing you, {Config.USER_NAME}. "
                        f"Going to sleep.",
                        self._stop_event,
                    )
                    self.voice.wait_until_done()
                    if video_was_playing:
                        self.browser.restore_volume()
                    return
                self.voice.speak(
                    "Still couldn't catch that. Please speak clearly."
                    if consecutive_empty == 2
                    else "Could you say that again?",
                    self._stop_event,
                )
                self.voice.wait_until_done()
                continue

            consecutive_empty = 0

            # Speaker check on each phrase.
            if audio_bytes and self.identifier.enabled:
                if self.identifier.identify(audio_bytes) == "unknown":
                    self.voice.speak(
                        f"That doesn't sound like you, {Config.USER_NAME}. "
                        f"I'll only take commands from your voice.",
                        self._stop_event,
                    )
                    self.voice.wait_until_done()
                    continue

            # ── Fast-path control phrases ───────────────────────────────────
            ctrl = fast_route(user_input)
            if ctrl == EXIT:
                self.voice.speak(
                    f"Goodbye, {Config.USER_NAME}. Jarvis signing off.",
                    self._stop_event,
                )
                self.voice.wait_until_done()
                self.running = False
                self._cleanup()
                return
            if ctrl == STOP:
                self._stop_event.set()
                time.sleep(0.3)
                self._stop_event.clear()
                self.voice.speak(
                    f"Stopped. What else, {Config.USER_NAME}?",
                    self._stop_event,
                )
                self.voice.wait_until_done()
                continue
            if ctrl == SLEEP:
                self.voice.speak(
                    f"Going to sleep. Say Jarvis when you need me, "
                    f"{Config.USER_NAME}.",
                    self._stop_event,
                )
                self.voice.wait_until_done()
                if video_was_playing:
                    self.browser.restore_volume()
                return

            # ── Track habit (rough categorisation by keyword) ───────────────
            self._track_habit(user_input)

            # ── Hand off to Claude tool-use brain ───────────────────────────
            response = self.brain.think(user_input, self.memory.get(), self.memory)

            self.memory.add("user", user_input)
            self.memory.add("assistant", response)
            self.voice.speak(response, self._stop_event)
            self.voice.wait_until_done()

            # Restore browser volume if a video is still playing and we didn't
            # just pause/stop it via tool use.
            if video_was_playing and self.browser._watching:
                self.browser.restore_volume(100)

            self._maybe_request_feedback(user_input, response)

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _handle_guest(self) -> bool:
        """Return True to continue into the awake state, False to skip."""
        self.browser.duck_volume(15)
        self.voice.speak(
            "I don't recognise that voice. What do you need?",
            self._stop_event,
        )
        self.voice.wait_until_done()
        guest_input, _ = self.wake.listen_phrase()

        if not guest_input:
            self.browser.restore_volume()
            return False

        self.voice.speak(
            f"{Config.USER_NAME}, someone is asking me to: '{guest_input}'. "
            f"Should I follow their command? Say yes or no.",
            self._stop_event,
        )
        self.voice.wait_until_done()
        self.voice.speak(
            f"Waiting for your response, {Config.USER_NAME}.",
            self._stop_event,
        )
        self.voice.wait_until_done()

        owner_wake = self.wake.wait_for_wake_word()
        if owner_wake and self.identifier.enabled:
            if self.identifier.identify(owner_wake) != "owner":
                self.voice.speak(
                    f"I couldn't verify your identity, {Config.USER_NAME}. "
                    f"Ignoring the guest request.",
                    self._stop_event,
                )
                self.voice.wait_until_done()
                self.browser.restore_volume()
                return False

        self.voice.speak(f"Yes, {Config.USER_NAME}?", self._stop_event)
        self.voice.wait_until_done()
        owner_response, _ = self.wake.listen_phrase()

        if owner_response and any(
            w in owner_response.lower()
            for w in ["yes", "allow", "let them", "go ahead", "grant", "sure", "okay", "fine"]
        ):
            self.voice.speak(
                f"Understood, {Config.USER_NAME}. Executing the request.",
                self._stop_event,
            )
            self.voice.wait_until_done()
            response = self.brain.think(guest_input, self.memory.get(), self.memory)
            self.voice.speak(response, self._stop_event)
            self.voice.wait_until_done()
        else:
            self.voice.speak(
                f"Access denied. I'll ignore that request, {Config.USER_NAME}.",
                self._stop_event,
            )
            self.voice.wait_until_done()

        self.browser.restore_volume()
        return False

    def _announce_proactively(self) -> None:
        suggestions = self.memory.get_proactive_suggestions()
        proactive_parts = []
        from .commands import CommandHandler
        for s in suggestions:
            if s == "weather":
                proactive_parts.append(CommandHandler.get_weather())
            elif s == "time":
                proactive_parts.append(CommandHandler.get_time())
            elif s == "system stats":
                proactive_parts.append(CommandHandler.get_system_stats())

        if proactive_parts:
            self.voice.speak(
                f"Good {self._time_of_day()}, {Config.USER_NAME}. "
                + " ".join(proactive_parts)
                + " How can I help you?",
                self._stop_event,
            )
        else:
            self.voice.speak(f"Yes, {Config.USER_NAME}?", self._stop_event)
        self.voice.wait_until_done()

    def _track_habit(self, user_input: str) -> None:
        t = user_input.lower()
        for keyword in (
            "weather", "time", "date", "system stats",
            "youtube", "spotify", "screenshot", "timer",
        ):
            if keyword in t:
                self.memory.track_habit(keyword)
                return

    def _maybe_request_feedback(self, user_input: str, response: str) -> None:
        self._interaction_count += 1
        if self._interaction_count % 5 != 0:
            return
        self.voice.speak(f"Was that helpful, {Config.USER_NAME}?", self._stop_event)
        self.voice.wait_until_done()
        feedback, _ = self.wake.listen_phrase()
        if feedback and any(
            w in feedback.lower()
            for w in ["yes", "good", "great", "perfect", "excellent", "helpful"]
        ):
            self.memory.save_good_response(user_input, response)
            self.voice.speak(
                f"Noted. I'll remember that style, {Config.USER_NAME}.",
                self._stop_event,
            )
            self.voice.wait_until_done()
        elif feedback and any(w in feedback.lower() for w in ["no", "wrong", "bad"]):
            self.voice.speak(
                f"I apologise. I'll do better, {Config.USER_NAME}.",
                self._stop_event,
            )
            self.voice.wait_until_done()

    @staticmethod
    def _time_of_day() -> str:
        hour = datetime.datetime.now().hour
        if hour < 12:
            return "morning"
        if hour < 17:
            return "afternoon"
        return "evening"

    # ── Cleanup ──────────────────────────────────────────────────────────────
    def _cleanup(self) -> None:
        log.info("Shutting down Jarvis...")
        self._stop_event.set()

        try:
            if hasattr(self.voice, "engine") and self.voice.engine:
                self.voice.engine.stop()
        except Exception:
            pass

        try:
            self.browser.cleanup()
        except Exception:
            pass

        try:
            if platform.system() == "Darwin":
                os.system("pkill -f afplay 2>/dev/null")
                os.system("pkill -f mpg123 2>/dev/null")
            elif platform.system() == "Linux":
                os.system("pkill -f mpg123 2>/dev/null")
            elif platform.system() == "Windows":
                os.system("taskkill /f /im wmplayer.exe 2>nul")
        except Exception:
            pass

        try:
            self.wake.cleanup()
        except Exception:
            pass

        for tmp in ("_tts_edge.mp3", "_tts_temp.mp3", "_jarvis_tts.mp3"):
            try:
                if Path(tmp).exists():
                    Path(tmp).unlink()
            except Exception:
                pass

        try:
            self.memory.save_all()
        except Exception:
            pass

        self.running = False
        log.info("Jarvis shut down cleanly.")

        def _force_exit():
            time.sleep(2)
            log.info("Force exiting.")
            os._exit(0)

        threading.Thread(target=_force_exit, daemon=True).start()


# ────────────────────────────────────────────────────────────────────────────
#  Entry point
# ────────────────────────────────────────────────────────────────────────────

def main() -> None:
    Config.validate()

    print("""
  ╔══════════════════════════════════════════════════╗
  ║           J . A . R . V . I . S                  ║
  ║     Just A Rather Very Intelligent System        ║
  ╚══════════════════════════════════════════════════╝
    """)
    jarvis = None
    try:
        jarvis = Jarvis()
        jarvis.run()
    except KeyboardInterrupt:
        print("\n  [Shutting down...]")
    except Exception as e:
        log.error(f"Fatal error: {e}")
    finally:
        if jarvis:
            jarvis._cleanup()


if __name__ == "__main__":
    main()
