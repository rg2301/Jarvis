"""OS-level actions: weather, time, system stats, screenshots, timers, volume, etc."""

from __future__ import annotations

import datetime
import os
import platform
import re
import threading
import time
import webbrowser

import psutil
import requests

from .config import Config, log


class CommandHandler:
    OS = platform.system()

    # ── Web ──────────────────────────────────────────────────────────────────
    @staticmethod
    def open_url(url: str) -> str:
        webbrowser.open(url)
        return f"Opening that now, {Config.USER_NAME}."

    # ── App launcher ─────────────────────────────────────────────────────────
    APPS = {
        "spotify":    {"Windows": "start spotify",        "Darwin": "open -a Spotify",                "Linux": "spotify &"},
        "chrome":     {"Windows": "start chrome",         "Darwin": "open -a 'Google Chrome'",        "Linux": "google-chrome &"},
        "vscode":     {"Windows": "code",                 "Darwin": "open -a 'Visual Studio Code'",   "Linux": "code &"},
        "notepad":    {"Windows": "notepad",              "Darwin": "open -a TextEdit",               "Linux": "gedit &"},
        "calculator": {"Windows": "calc",                 "Darwin": "open -a Calculator",             "Linux": "gnome-calculator &"},
        "files":      {"Windows": "explorer",             "Darwin": "open ~",                         "Linux": "nautilus &"},
    }

    @staticmethod
    def open_app(name: str) -> str | None:
        cmd = CommandHandler.APPS.get(name.lower(), {}).get(CommandHandler.OS)
        if not cmd:
            return None
        os.system(cmd)
        return f"Launching {name}, {Config.USER_NAME}."

    # ── System stats ─────────────────────────────────────────────────────────
    @staticmethod
    def get_system_stats() -> str:
        cpu     = psutil.cpu_percent(interval=0.5)
        ram     = psutil.virtual_memory()
        disk    = psutil.disk_usage("/")
        battery = psutil.sensors_battery()
        bat_str = f", Battery at {int(battery.percent)}%" if battery else ""
        return (
            f"CPU is at {cpu}%, RAM at {ram.percent}% used "
            f"({ram.used // (1024**3)}GB of {ram.total // (1024**3)}GB), "
            f"disk at {disk.percent}% capacity{bat_str}, {Config.USER_NAME}."
        )

    # ── Time & date ──────────────────────────────────────────────────────────
    @staticmethod
    def get_time() -> str:
        return f"It's {datetime.datetime.now().strftime('%I:%M %p')}, {Config.USER_NAME}."

    @staticmethod
    def get_date() -> str:
        return f"Today is {datetime.datetime.now().strftime('%A, %d %B %Y')}, {Config.USER_NAME}."

    # ── Weather ──────────────────────────────────────────────────────────────
    @staticmethod
    def get_weather(city: str | None = None) -> str:
        city = city or Config.CITY
        if not Config.USE_WEATHER:
            return (
                f"Weather lookup requires an OpenWeatherMap API key, "
                f"{Config.USER_NAME}. Add it to your .env file."
            )
        try:
            url = (
                f"https://api.openweathermap.org/data/2.5/weather"
                f"?q={city}&appid={Config.OPENWEATHER_KEY}&units=metric"
            )
            r = requests.get(url, timeout=5).json()
            temp     = round(r["main"]["temp"])
            feels    = round(r["main"]["feels_like"])
            desc     = r["weather"][0]["description"].capitalize()
            humidity = r["main"]["humidity"]
            return (
                f"{desc} in {city}, {Config.USER_NAME}. "
                f"{temp}°C, feels like {feels}°C, humidity {humidity}%."
            )
        except Exception as e:
            log.error(f"Weather error: {e}")
            return f"I couldn't fetch the weather right now, {Config.USER_NAME}."

    # ── Screenshot ───────────────────────────────────────────────────────────
    @staticmethod
    def take_screenshot() -> str:
        try:
            import pyautogui

            filename = (
                f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            )
            pyautogui.screenshot(filename)
            return f"Screenshot saved as '{filename}', {Config.USER_NAME}."
        except Exception as e:
            return f"Screenshot failed: {e}"

    # ── Volume ───────────────────────────────────────────────────────────────
    @staticmethod
    def set_volume(level: int) -> str:
        level = max(0, min(100, int(level)))
        if CommandHandler.OS == "Windows":
            from ctypes import POINTER, cast

            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

            devices   = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume    = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMasterVolumeLevelScalar(level / 100, None)
        elif CommandHandler.OS == "Darwin":
            os.system(f"osascript -e 'set volume output volume {level}'")
        else:
            os.system(f"pactl set-sink-volume @DEFAULT_SINK@ {level}%")
        return f"Volume set to {level}%, {Config.USER_NAME}."

    # ── Timer ────────────────────────────────────────────────────────────────
    @staticmethod
    def parse_duration(text: str) -> int:
        """'1 hour 30 minutes 5 seconds' (any subset, any order) → total seconds."""
        total = 0
        for n, unit in re.findall(
            r"(\d+)\s*(hour|hr|minute|min|second|sec)", text.lower()
        ):
            n = int(n)
            if unit.startswith("h"):
                total += n * 3600
            elif unit.startswith("m"):
                total += n * 60
            else:
                total += n
        if total == 0:
            nums = re.findall(r"\d+", text)
            if nums:
                total = int(nums[0])
                tl = text.lower()
                if "hour" in tl:
                    total *= 3600
                elif "minute" in tl or "min" in tl:
                    total *= 60
        return total

    @staticmethod
    def set_timer(seconds: int, voice) -> str:
        def _ring():
            time.sleep(seconds)
            voice.speak(f"Timer complete, {Config.USER_NAME}.")
        threading.Thread(target=_ring, daemon=True).start()

        hours, rem = divmod(seconds, 3600)
        mins, secs = divmod(rem, 60)
        parts = []
        if hours: parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
        if mins:  parts.append(f"{mins} minute{'s' if mins > 1 else ''}")
        if secs:  parts.append(f"{secs} second{'s' if secs > 1 else ''}")
        return f"Timer set for {' '.join(parts) or '0 seconds'}, {Config.USER_NAME}."

    # ── Power ────────────────────────────────────────────────────────────────
    @staticmethod
    def shutdown_system() -> str:
        if CommandHandler.OS == "Windows":
            os.system("shutdown /s /t 5")
        else:
            os.system("shutdown -h now")
        return f"Shutting down the system in 5 seconds, {Config.USER_NAME}."

    @staticmethod
    def restart_system() -> str:
        if CommandHandler.OS == "Windows":
            os.system("shutdown /r /t 5")
        else:
            os.system("reboot")
        return f"Restarting the system, {Config.USER_NAME}."
