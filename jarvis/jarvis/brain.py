"""Claude tool-use loop: the brain that turns speech into action + reply."""

from __future__ import annotations

import datetime
import sys

try:
    import anthropic
except ImportError as e:
    raise SystemExit(f"[ERROR] Missing dependency: {e}. pip install -r requirements.txt")

from .config import Config, SYSTEM_PROMPT, log
from .memory import Memory
from .tools import TOOLS, ToolExecutor


class AIBrain:
    """Runs an agentic tool-use loop against Claude.

    Each call to `think()`:
      1. Sends the user message + history + tool schemas.
      2. If Claude responds with `tool_use`, executes each tool via the
         injected `ToolExecutor` and feeds `tool_result` back.
      3. Loops until Claude returns a final text response (or a hop cap is hit).
    """

    def __init__(self, executor: ToolExecutor):
        self.client   = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        self.executor = executor
        log.info(f"AI brain ready. Model: {Config.MODEL}")

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _build_system(self, memory: Memory | None) -> list[dict]:
        stable = SYSTEM_PROMPT
        if memory:
            facts = memory.get_facts_as_text()
            if facts:
                stable += f"\n\n{facts}"
            good = memory.get_good_responses_as_text()
            if good:
                stable += f"\n\n{good}"
        volatile_date = (
            "Current date and time: "
            + datetime.datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
        )
        return [
            {
                "type": "text",
                "text": stable,
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": volatile_date},
        ]

    @staticmethod
    def _extract_text(response) -> str:
        return "".join(
            b.text for b in response.content if getattr(b, "type", None) == "text"
        ).strip()

    # ── Main entry point ────────────────────────────────────────────────────
    def think(
        self,
        user_input: str,
        history: list[dict],
        memory: Memory | None = None,
    ) -> str:
        system = self._build_system(memory)
        messages: list[dict] = list(history) + [
            {"role": "user", "content": user_input},
        ]

        for hop in range(Config.MAX_TOOL_HOPS):
            try:
                response = self.client.messages.create(
                    model=Config.MODEL,
                    max_tokens=Config.MAX_TOKENS,
                    system=system,
                    tools=TOOLS,
                    messages=messages,
                )
            except anthropic.AuthenticationError:
                log.error("Invalid API key.")
                return f"Authentication failed, {Config.USER_NAME}."
            except anthropic.RateLimitError:
                log.warning("Rate limited.")
                return f"I'm being rate limited, {Config.USER_NAME}. Give me a moment."
            except anthropic.APIConnectionError:
                log.error("No internet connection.")
                return f"I can't reach the server, {Config.USER_NAME}."
            except Exception as e:
                log.error(f"Claude API error: {e}")
                return f"I encountered an error, {Config.USER_NAME}. Please try again."

            if response.stop_reason != "tool_use":
                return self._extract_text(response) or (
                    f"I'm not sure what to say, {Config.USER_NAME}."
                )

            # Tool round-trip: feed results back in.
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    out = self.executor.dispatch(block.name, block.input or {})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(out),
                    })

            # Append the assistant's tool-call turn and the tool results.
            # Anthropic SDK accepts content blocks directly.
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        log.warning(f"Tool-use hop cap ({Config.MAX_TOOL_HOPS}) reached.")
        return f"I had trouble completing that, {Config.USER_NAME}."
