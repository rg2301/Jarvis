"""Persistent conversation history, facts, habits, and rated responses — all cached in-memory."""

from __future__ import annotations

import datetime
import json
import os
import threading
from pathlib import Path

from .config import Config, log


class Memory:
    def __init__(self, filepath: str | None = None, max_history: int | None = None):
        self.filepath    = Path(filepath or Config.MEMORY_FILE)
        self.max_history = max_history or Config.MAX_HISTORY
        self.history: list[dict] = []
        self.facts: list[dict]   = []
        self.habits: dict        = {}
        self.good:  list[dict]   = []
        self._lock = threading.Lock()
        self._load_all()

    # ── Loading ──────────────────────────────────────────────────────────────
    def _read_json(self, path: Path, default):
        if not path.exists():
            return default
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"Could not read {path}: {e}")
            return default

    def _load_all(self) -> None:
        data = self._read_json(self.filepath, {})
        self.history = data.get("history", []) if isinstance(data, dict) else []
        self.facts   = self._read_json(Path(Config.FACTS_FILE), [])
        self.habits  = self._read_json(Path(Config.HABITS_FILE), {})
        self.good    = self._read_json(Path(Config.GOOD_RESPONSES_FILE), [])
        log.info(
            f"Memory loaded: {len(self.history)} msgs, {len(self.facts)} facts, "
            f"{len(self.habits)} habits, {len(self.good)} good responses."
        )

    # ── Atomic writes ────────────────────────────────────────────────────────
    def _write_json(self, path: Path, data) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, path)
        except Exception as e:
            log.warning(f"Could not save {path}: {e}")

    def save(self) -> None:
        with self._lock:
            self._write_json(self.filepath, {"history": self.history})

    def save_all(self) -> None:
        with self._lock:
            self._write_json(self.filepath, {"history": self.history})
            self._write_json(Path(Config.FACTS_FILE), self.facts)
            self._write_json(Path(Config.HABITS_FILE), self.habits)
            self._write_json(Path(Config.GOOD_RESPONSES_FILE), self.good)

    # ── History ──────────────────────────────────────────────────────────────
    def add(self, role: str, content) -> None:
        """Append a message and trim on (user, assistant) pair boundaries."""
        self.history.append({"role": role, "content": content})
        if len(self.history) > self.max_history:
            excess = len(self.history) - self.max_history
            if excess % 2:
                excess += 1
            self.history = self.history[excess:]
            if self.history and self.history[0].get("role") != "user":
                self.history = self.history[1:]
        self.save()

    def clear(self) -> None:
        self.history = []
        self.save()
        log.info("Memory cleared.")

    def get(self) -> list[dict]:
        return self.history.copy()

    # ── Facts ────────────────────────────────────────────────────────────────
    def save_fact(self, fact: str) -> None:
        self.facts.append({
            "fact": fact,
            "timestamp": datetime.datetime.now().isoformat(),
        })
        self._write_json(Path(Config.FACTS_FILE), self.facts)
        log.info(f"Fact saved: {fact}")

    def get_facts_as_text(self) -> str:
        if not self.facts:
            return ""
        return "Facts about the user:\n" + "\n".join(
            f"- {f['fact']}" for f in self.facts
        )

    # ── Habits ───────────────────────────────────────────────────────────────
    def track_habit(self, command: str) -> None:
        hour = datetime.datetime.now().hour
        key = f"{command}_{hour}"
        self.habits[key] = self.habits.get(key, 0) + 1
        self._write_json(Path(Config.HABITS_FILE), self.habits)

    def get_proactive_suggestions(self) -> list[str]:
        hour = datetime.datetime.now().hour
        suffix = f"_{hour}"
        return [
            key[: -len(suffix)]
            for key, count in self.habits.items()
            if key.endswith(suffix) and count >= 3
        ]

    # ── Good responses ───────────────────────────────────────────────────────
    def save_good_response(self, question: str, response: str) -> None:
        self.good.append({
            "question": question,
            "response": response,
            "saved_at": datetime.datetime.now().isoformat(),
        })
        self.good = self.good[-20:]
        self._write_json(Path(Config.GOOD_RESPONSES_FILE), self.good)
        log.info(f"Good response saved. Total: {len(self.good)}")

    def get_good_responses_as_text(self) -> str:
        if not self.good:
            return ""
        lines = [
            f"Q: {ex['question']}\nA: {ex['response']}"
            for ex in self.good[-5:]
        ]
        return (
            "Examples of responses this user has rated as excellent "
            "(use these as style guidance):\n\n"
            + "\n\n".join(lines)
        )
