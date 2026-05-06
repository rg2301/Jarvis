"""Tool schemas and executor for Claude tool use.

The executor exposes one method per tool. `ToolExecutor.dispatch(name, args)`
routes a tool call from Claude to the right handler and returns a string
(`tool_result.content`). For destructive actions (shutdown, restart) the
executor itself runs the verbal confirmation flow before invoking the OS call.
"""

from __future__ import annotations

from .commands import CommandHandler
from .config import Config, log


# ────────────────────────────────────────────────────────────────────────────
#  Tool schemas — sent to Claude on every messages.create call
# ────────────────────────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "get_time",
        "description": "Get the current local time.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_date",
        "description": "Get today's date.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_weather",
        "description": (
            "Look up current weather for a city. "
            "Omit `city` to use the user's home city."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Optional city name.",
                },
            },
        },
    },
    {
        "name": "get_system_stats",
        "description": "Report current CPU, RAM, disk, and battery levels.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "take_screenshot",
        "description": "Capture a screenshot and save it to disk.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_timer",
        "description": (
            "Start a countdown that announces 'Timer complete' when it ends. "
            "Pass the duration in seconds (parse phrases like '1 hour 30 minutes' "
            "yourself before calling)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {"type": "integer", "minimum": 1},
            },
            "required": ["seconds"],
        },
    },
    {
        "name": "set_volume",
        "description": "Set system speaker volume to a level between 0 and 100.",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {"type": "integer", "minimum": 0, "maximum": 100},
            },
            "required": ["level"],
        },
    },
    {
        "name": "open_app",
        "description": (
            "Launch a desktop application. "
            "Supported names: spotify, chrome, vscode, notepad, calculator, files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "shutdown_system",
        "description": (
            "Shut down the computer. ALWAYS asks for verbal confirmation first; "
            "the user must say 'yes' or 'confirm' for it to proceed."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "restart_system",
        "description": (
            "Restart the computer. ALWAYS asks for verbal confirmation first."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "clear_memory",
        "description": "Wipe Jarvis's conversation memory and start fresh.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "browser_open",
        "description": (
            "Open a website or shortcut in the controlled Chrome browser. "
            "`target` may be a shortcut keyword (youtube, github, gmail, ...), "
            "a domain, or a full URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "browser_play",
        "description": (
            "Search a streaming site for a query and play the first matching video. "
            "Use this for any 'play X', 'watch Y', 'listen to Z' style request."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "site": {
                    "type": "string",
                    "enum": [
                        "youtube", "spotify", "netflix",
                        "hotstar", "prime", "amazon",
                    ],
                    "description": "Defaults to youtube.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "browser_control",
        "description": (
            "Control playback or navigation in the controlled browser. "
            "Choose one of the action enum values."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "play_pause", "stop", "skip_forward", "skip_backward",
                        "next_video", "mute", "fullscreen",
                        "volume_up", "volume_down",
                        "scroll_up", "scroll_down", "scroll_top", "scroll_bottom",
                        "back", "forward", "refresh",
                        "new_tab", "close_tab", "next_tab",
                        "read_page",
                    ],
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Search the web for real-time information (news, prices, scores, "
            "live events). Returns a summary you should base your answer on."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "news": {
                    "type": "boolean",
                    "description": (
                        "True for news/current-events queries (uses Google News RSS); "
                        "false for general lookups. Defaults to false."
                    ),
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "save_fact",
        "description": (
            "Permanently remember a personal fact the user told Jarvis "
            "(e.g. dietary restrictions, preferences, names of family members)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string"},
            },
            "required": ["fact"],
        },
    },
    {
        "name": "voice_reenroll",
        "description": "Delete the saved voiceprint and re-record the owner's voice.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


# ────────────────────────────────────────────────────────────────────────────
#  Executor
# ────────────────────────────────────────────────────────────────────────────

class ToolExecutor:
    """Executes a tool call and returns a string for the tool_result block."""

    def __init__(self, voice, memory, web, browser, identifier, stop_event):
        self.voice      = voice
        self.memory     = memory
        self.web        = web
        self.browser    = browser
        self.identifier = identifier
        self.stop_event = stop_event

    # ── Public entry ────────────────────────────────────────────────────────
    def dispatch(self, name: str, args: dict) -> str:
        handler = self._handlers().get(name)
        if not handler:
            log.warning(f"Unknown tool: {name}")
            return f"Unknown tool: {name}"
        try:
            result = handler(args or {})
            log.info(f"Tool {name} → {str(result)[:160]}")
            return result
        except Exception as e:
            log.error(f"Tool {name} error: {e}")
            return f"Error executing {name}: {e}"

    def _handlers(self) -> dict:
        return {
            "get_time":         lambda _a: CommandHandler.get_time(),
            "get_date":         lambda _a: CommandHandler.get_date(),
            "get_weather":      lambda a: CommandHandler.get_weather(a.get("city")),
            "get_system_stats": lambda _a: CommandHandler.get_system_stats(),
            "take_screenshot":  lambda _a: CommandHandler.take_screenshot(),
            "set_timer":        self._set_timer,
            "set_volume":       lambda a: CommandHandler.set_volume(int(a["level"])),
            "open_app":         self._open_app,
            "shutdown_system":  self._shutdown,
            "restart_system":   self._restart,
            "clear_memory":     self._clear_memory,
            "browser_open":     lambda a: self.browser.open(a["target"]),
            "browser_play":     self._browser_play,
            "browser_control":  self._browser_control,
            "web_search":       self._web_search,
            "save_fact":        self._save_fact,
            "voice_reenroll":   self._voice_reenroll,
        }

    # ── Handlers with non-trivial logic ─────────────────────────────────────
    def _set_timer(self, args: dict) -> str:
        return CommandHandler.set_timer(int(args["seconds"]), self.voice)

    def _open_app(self, args: dict) -> str:
        result = CommandHandler.open_app(args["name"])
        if result is None:
            return (
                f"I don't know how to open '{args['name']}' on this OS. "
                f"Supported: {', '.join(CommandHandler.APPS)}."
            )
        return result

    def _clear_memory(self, _args: dict) -> str:
        self.memory.clear()
        return f"Memory cleared, {Config.USER_NAME}."

    def _browser_play(self, args: dict) -> str:
        site  = (args.get("site") or "youtube").lower()
        query = args["query"]
        # Make sure we're on the right site first.
        if site not in self.browser._current_site():
            self.browser.open(site)
        return self.browser.search_on_site(query, site=f"{site}.com")

    # Map tool action → (BrowserController method name, positional args).
    _BROWSER_ACTION_MAP: dict = {
        "play_pause":    ("play_pause",    ()),
        "stop":          ("play_pause",    ()),     # toggling from playing → pauses
        "skip_forward":  ("skip_forward",  ()),
        "skip_backward": ("skip_backward", ()),
        "next_video":    ("next_youtube",  ()),
        "mute":          ("mute",          ()),
        "fullscreen":    ("fullscreen",    ()),
        "volume_up":     ("volume_up",     ()),
        "volume_down":   ("volume_down",   ()),
        "scroll_up":     ("scroll",        ("up",)),
        "scroll_down":   ("scroll",        ("down",)),
        "scroll_top":    ("scroll_top",    ()),
        "scroll_bottom": ("scroll_bottom", ()),
        "back":          ("go_back",       ()),
        "forward":       ("go_forward",    ()),
        "refresh":       ("refresh",       ()),
        "new_tab":       ("new_tab",       ()),
        "close_tab":     ("close_tab",     ()),
        "next_tab":      ("next_tab",      ()),
    }

    def _browser_control(self, args: dict) -> str:
        action = args["action"]
        if action == "read_page":
            return self._read_page()
        spec = self._BROWSER_ACTION_MAP.get(action)
        if not spec:
            return f"Unknown browser action: {action}"
        method_name, fn_args = spec
        return getattr(self.browser, method_name)(*fn_args)

    def _read_page(self) -> str:
        title = self.browser.get_page_title()
        text  = self.browser.read_page()
        if not text:
            return "Could not read the page."
        return f"PAGE_TITLE: {title}\nPAGE_TEXT: {text}"

    def _web_search(self, args: dict) -> str:
        query = args["query"]
        is_news = bool(args.get("news"))
        results = (
            self.web.search_news(query) if is_news else self.web.search(query)
        )
        return self.web.summarise_for_jarvis(query, results)

    def _save_fact(self, args: dict) -> str:
        self.memory.save_fact(args["fact"])
        return f"Fact saved: {args['fact']}"

    def _voice_reenroll(self, _args: dict) -> str:
        self.identifier.delete_voiceprint()
        ok = self.identifier.enroll(self.voice)
        return "Voiceprint re-enrolled." if ok else "Re-enrollment failed."

    # ── Confirmation-gated handlers ─────────────────────────────────────────
    def _confirm(self, prompt: str) -> bool:
        from .speech import WakeWordDetector
        # Use the listener owned by the app, not a fresh one — the app injects
        # via `self.listener` at runtime (set by Jarvis after construction).
        listener = getattr(self, "listener", None)
        if listener is None:
            log.warning("No listener for confirmation; treating as denial.")
            return False
        self.voice.speak(prompt, self.stop_event)
        self.voice.wait_until_done()
        reply, _ = listener.listen_phrase()
        if not reply:
            return False
        r = reply.lower()
        deny   = ["no", "cancel", "stop", "don't", "nope", "abort", "never mind"]
        affirm = ["yes", "yeah", "yep", "confirm", "do it", "go ahead", "proceed"]
        if any(d in r for d in deny):
            return False
        return any(a in r for a in affirm)

    def _shutdown(self, _args: dict) -> str:
        if self._confirm(
            f"Are you sure you want to shut down the computer, "
            f"{Config.USER_NAME}? Say yes to confirm."
        ):
            return CommandHandler.shutdown_system()
        return f"Shutdown cancelled, {Config.USER_NAME}."

    def _restart(self, _args: dict) -> str:
        if self._confirm(
            f"Are you sure you want to restart the computer, "
            f"{Config.USER_NAME}? Say yes to confirm."
        ):
            return CommandHandler.restart_system()
        return f"Restart cancelled, {Config.USER_NAME}."
