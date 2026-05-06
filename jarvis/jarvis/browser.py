"""Selenium-driven Chrome controller for media playback and navigation."""

from __future__ import annotations

import os
import threading
import time
import webbrowser
from urllib.parse import urlparse

from .config import Config, log


class BrowserController:
    SHORTCUTS = {
        "youtube":   "https://youtube.com",
        "gmail":     "https://mail.google.com",
        "google":    "https://google.com",
        "instagram": "https://instagram.com",
        "whatsapp":  "https://web.whatsapp.com",
        "twitter":   "https://twitter.com",
        "linkedin":  "https://linkedin.com",
        "netflix":   "https://netflix.com",
        "github":    "https://github.com",
        "amazon":    "https://amazon.in",
        "flipkart":  "https://flipkart.com",
        "maps":      "https://maps.google.com",
        "reddit":    "https://reddit.com",
        "spotify":   "https://open.spotify.com",
        "hotstar":   "https://hotstar.com",
        "prime":     "https://primevideo.com",
    }

    def __init__(self) -> None:
        self.driver     = None
        self.enabled    = False
        self._keepalive = None
        self._watching  = False
        self._setup()

    # ── Driver lifecycle ─────────────────────────────────────────────────────
    def _setup(self) -> None:
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            options = Options()
            options.add_argument("--start-maximized")
            options.add_argument("--disable-notifications")
            options.add_argument("--disable-infobars")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")

            options.add_experimental_option("detach", True)
            options.add_experimental_option(
                "excludeSwitches", ["enable-automation", "enable-logging"]
            )
            options.add_experimental_option("useAutomationExtension", False)

            options.add_argument(
                "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', "
                "{get: () => undefined})"
            )
            self.enabled = True
            log.info("Browser controller ready.")
        except Exception as e:
            log.warning(f"Browser controller unavailable: {e}")
            self.enabled = False

    def _is_alive(self) -> bool:
        if not self.driver:
            return False
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            return False

    def _ensure_alive(self) -> bool:
        if self._is_alive():
            return True
        log.warning("Selenium driver dead — re-initialising.")
        try:
            if self.driver:
                try: self.driver.quit()
                except Exception: pass
        finally:
            self.driver  = None
            self.enabled = False
        self._watching = False
        self._setup()
        return self.enabled

    # ── Internal helpers ─────────────────────────────────────────────────────
    def _wait(self, seconds: float = 1.5) -> None:
        time.sleep(seconds)

    def _current_url(self) -> str:
        try:
            return self.driver.current_url
        except Exception:
            return ""

    def _current_site(self) -> str:
        try:
            return urlparse(self._current_url()).netloc.replace("www.", "")
        except Exception:
            return ""

    def _find_and_click(self, selectors: list, timeout: int = 5) -> bool:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        for sel in selectors:
            try:
                el = WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                el.click()
                return True
            except Exception:
                continue
        return False

    def _find_and_type(self, selectors: list, text: str) -> bool:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        for sel in selectors:
            try:
                el = WebDriverWait(self.driver, 4).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                el.clear()
                el.send_keys(text)
                el.send_keys(Keys.RETURN)
                return True
            except Exception:
                continue
        return False

    def _press_key(self, key: str) -> None:
        from selenium.webdriver.common.by import By
        try:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(key)
        except Exception:
            pass

    def _js(self, script: str):
        try:
            return self.driver.execute_script(script)
        except Exception:
            return None

    # ── YouTube interruption handler ────────────────────────────────────────
    def _handle_youtube_interruptions(self) -> None:
        try:
            from selenium.webdriver.common.by import By

            for selectors, label in [
                (
                    [
                        ".ytp-skip-ad-button",
                        ".ytp-ad-skip-button",
                        "button.ytp-ad-skip-button-modern",
                        "[class*='skip-ad']",
                        "[id*='skip-ad']",
                    ],
                    "YouTube ad",
                ),
                (
                    [
                        ".yt-confirm-dialog-renderer button",
                        "paper-button[dialog-confirm]",
                        "[aria-label='Yes']",
                        ".ytd-enforcement-message-view-model button",
                    ],
                    "'Are you still watching?'",
                ),
                (
                    [
                        "button[aria-label*='Accept']",
                        "button[aria-label*='agree']",
                        ".VfPpkd-LgbsSe[jsname='b3VHJd']",
                        "#L2AGLb",
                    ],
                    "consent popup",
                ),
            ]:
                for sel in selectors:
                    try:
                        btn = self.driver.find_element(By.CSS_SELECTOR, sel)
                        if btn.is_displayed():
                            btn.click()
                            log.info(f"Dismissed {label}.")
                            time.sleep(0.5)
                            return
                    except Exception:
                        pass

            try:
                paused = self._js(
                    "var v = document.querySelector('video');"
                    "return v ? v.paused : false;"
                )
                if paused and self._watching:
                    self._js(
                        "var v = document.querySelector('video');"
                        "if(v) v.play();"
                    )
                    log.info("Auto-resumed paused video.")
            except Exception:
                pass
        except Exception as e:
            log.debug(f"Interruption handler error: {e}")

    def _start_keepalive(self) -> None:
        def _loop():
            while self._watching:
                try:
                    if "youtube.com/watch" in self._current_url():
                        self._handle_youtube_interruptions()
                except Exception:
                    pass
                time.sleep(10)

        self._watching  = True
        self._keepalive = threading.Thread(target=_loop, daemon=True)
        self._keepalive.start()
        log.info("YouTube keep-alive thread started.")

    def _stop_keepalive(self) -> None:
        self._watching = False
        log.info("YouTube keep-alive thread stopped.")

    # ── Volume ducking ──────────────────────────────────────────────────────
    def duck_volume(self, level: int = 20) -> None:
        if not self._watching or not self._ensure_alive():
            return
        try:
            self._js(
                f"var v = document.querySelector('video');"
                f"if(v) v.volume = {level / 100};"
            )
            log.info(f"Volume ducked to {level}%.")
        except Exception as e:
            log.error(f"Duck volume error: {e}")

    def restore_volume(self, level: int = 100) -> None:
        if not self._watching or not self._ensure_alive():
            return

        def _fade_up():
            try:
                current = level // 5
                while current <= level:
                    self._js(
                        f"var v = document.querySelector('video');"
                        f"if(v) v.volume = {current / 100};"
                    )
                    current += 5
                    time.sleep(0.06)
            except Exception as e:
                log.error(f"Restore volume error: {e}")

        threading.Thread(target=_fade_up, daemon=True).start()

    # ── Navigation ──────────────────────────────────────────────────────────
    def open(self, target: str) -> str:
        url = self.SHORTCUTS.get(target.lower().strip())
        if not url:
            if "." in target:
                url = target if target.startswith("http") else f"https://{target}"
            else:
                url = f"https://www.google.com/search?q={target.replace(' ', '+')}"

        if self._ensure_alive():
            try:
                self._stop_keepalive()
                self.driver.get(url)
                self._wait(1.5)
                return f"Opened {target}, {Config.USER_NAME}."
            except Exception as e:
                log.error(f"Open error: {e}")

        webbrowser.open(url)
        return f"Opened {target}, {Config.USER_NAME}."

    def go_back(self) -> str:
        if self._ensure_alive():
            try:
                self._stop_keepalive()
                self.driver.back()
                return f"Going back, {Config.USER_NAME}."
            except Exception:
                pass
        return f"Couldn't go back, {Config.USER_NAME}."

    def go_forward(self) -> str:
        if self._ensure_alive():
            try:
                self.driver.forward()
                return f"Going forward, {Config.USER_NAME}."
            except Exception:
                pass
        return f"Couldn't go forward, {Config.USER_NAME}."

    def refresh(self) -> str:
        if self._ensure_alive():
            try:
                self.driver.refresh()
                return f"Page refreshed, {Config.USER_NAME}."
            except Exception:
                pass
        return f"Couldn't refresh, {Config.USER_NAME}."

    # ── YouTube play ────────────────────────────────────────────────────────
    def _youtube_play(self, query: str) -> str:
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
            import urllib.parse

            self._stop_keepalive()
            encoded = urllib.parse.quote(query)
            self.driver.get(
                f"https://www.youtube.com/results?search_query={encoded}"
            )
            self._wait(2.5)
            self._handle_youtube_interruptions()

            wait = WebDriverWait(self.driver, 10)
            videos = wait.until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "ytd-video-renderer a#video-title")
                )
            )

            clicked_title = None
            for video in videos[:5]:
                href  = video.get_attribute("href") or ""
                title = video.get_attribute("title") or query
                if "/shorts/" in href:
                    continue
                if "list=" in href and "watch" not in href:
                    continue
                video.click()
                clicked_title = title
                break

            if not clicked_title:
                videos[0].click()
                clicked_title = query

            self._wait(2)
            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', "
                "{get: () => undefined})"
            )
            self._start_keepalive()
            log.info(f"Playing YouTube: '{clicked_title}'")
            return f"Playing '{clicked_title}' on YouTube, {Config.USER_NAME}."
        except Exception as e:
            log.error(f"YouTube play error: {e}")
            url = (
                f"https://www.youtube.com/results"
                f"?search_query={query.replace(' ', '+')}"
            )
            webbrowser.open(url)
            return (
                f"Opened YouTube for '{query}', {Config.USER_NAME}. "
                f"Please click a video to play."
            )

    # ── Search any site ─────────────────────────────────────────────────────
    SITE_SEARCH_SELECTORS = {
        "google.com":    ["input[name='q']", "textarea[name='q']"],
        "amazon.in":     ["input#twotabsearchtextbox"],
        "amazon.com":    ["input#twotabsearchtextbox"],
        "flipkart.com":  ["input[name='q']"],
        "netflix.com":   ["input[data-uia='search-input']"],
        "hotstar.com":   ["input[placeholder*='Search']"],
        "reddit.com":    ["input[name='q']"],
        "linkedin.com":  ["input[placeholder*='Search']"],
        "github.com":    ["input[name='q']"],
        "spotify.com":   ["input[data-testid='search-input']"],
    }
    GENERIC_SEARCH_SELECTORS = [
        "input[type='search']",
        "input[name='q']",
        "input[name='search']",
        "input[placeholder*='Search']",
        "input[placeholder*='search']",
        "input#search",
    ]

    def search_on_site(self, query: str, site: str | None = None) -> str:
        site = site or self._current_site()

        if "youtube" in site:
            return self._youtube_play(query)

        selectors = self.SITE_SEARCH_SELECTORS.get(
            site, self.GENERIC_SEARCH_SELECTORS
        )
        if self._ensure_alive():
            try:
                if self._find_and_type(selectors, query):
                    self._wait(1.5)
                    return f"Searched for '{query}' on {site}, {Config.USER_NAME}."
            except Exception as e:
                log.error(f"Search error: {e}")
        return f"Couldn't search on {site}, {Config.USER_NAME}."

    # ── Playback ────────────────────────────────────────────────────────────
    def play_pause(self) -> str:
        if self._ensure_alive():
            try:
                result = self._js(
                    "var v = document.querySelector('video');"
                    "if(v){ if(v.paused){ v.play(); return 'playing'; }"
                    "else{ v.pause(); return 'paused'; } }"
                    "return 'no_video';"
                )
                if result == "playing":
                    if not self._watching:
                        self._start_keepalive()
                    return f"Resuming playback, {Config.USER_NAME}."
                if result == "paused":
                    self._stop_keepalive()
                    return f"Paused, {Config.USER_NAME}."
                self._press_key(" ")
                return f"Toggled playback, {Config.USER_NAME}."
            except Exception as e:
                log.error(f"Play/pause error: {e}")
        return f"Couldn't control playback, {Config.USER_NAME}."

    def skip_forward(self) -> str:
        if self._ensure_alive():
            try:
                self._js(
                    "var v = document.querySelector('video');"
                    "if(v) v.currentTime += 10;"
                )
                return f"Skipped forward 10 seconds, {Config.USER_NAME}."
            except Exception as e:
                log.error(f"Skip forward error: {e}")
        return f"Couldn't skip forward, {Config.USER_NAME}."

    def skip_backward(self) -> str:
        if self._ensure_alive():
            try:
                self._js(
                    "var v = document.querySelector('video');"
                    "if(v) v.currentTime -= 10;"
                )
                return f"Skipped back 10 seconds, {Config.USER_NAME}."
            except Exception as e:
                log.error(f"Skip backward error: {e}")
        return f"Couldn't skip backward, {Config.USER_NAME}."

    def next_youtube(self) -> str:
        if self._ensure_alive():
            try:
                if self._find_and_click([".ytp-next-button", "a.ytp-next-button"]):
                    self._wait(2)
                    self._start_keepalive()
                    return f"Playing next video, {Config.USER_NAME}."
                if self._find_and_click([
                    "#related ytd-compact-video-renderer a",
                    "ytd-compact-video-renderer a#thumbnail",
                ]):
                    self._wait(2)
                    self._start_keepalive()
                    return f"Playing next video, {Config.USER_NAME}."
            except Exception as e:
                log.error(f"Next video error: {e}")
        return f"Couldn't skip to next, {Config.USER_NAME}."

    def volume_up(self) -> str:
        if self._ensure_alive():
            try:
                self._js(
                    "var v = document.querySelector('video');"
                    "if(v) v.volume = Math.min(1, v.volume + 0.2);"
                )
                return f"Volume up, {Config.USER_NAME}."
            except Exception as e:
                log.error(f"Volume up error: {e}")
        return f"Couldn't adjust volume, {Config.USER_NAME}."

    def volume_down(self) -> str:
        if self._ensure_alive():
            try:
                self._js(
                    "var v = document.querySelector('video');"
                    "if(v) v.volume = Math.max(0, v.volume - 0.2);"
                )
                return f"Volume down, {Config.USER_NAME}."
            except Exception as e:
                log.error(f"Volume down error: {e}")
        return f"Couldn't adjust volume, {Config.USER_NAME}."

    def mute(self) -> str:
        if self._ensure_alive():
            try:
                muted = self._js(
                    "var v = document.querySelector('video');"
                    "if(v){ v.muted = !v.muted; return v.muted; }"
                )
                state = "Muted" if muted else "Unmuted"
                return f"{state}, {Config.USER_NAME}."
            except Exception as e:
                log.error(f"Mute error: {e}")
        return f"Couldn't mute, {Config.USER_NAME}."

    def fullscreen(self) -> str:
        if self._ensure_alive():
            try:
                self._js(
                    "var v = document.querySelector('video');"
                    "if(v){"
                    "  if(!document.fullscreenElement){"
                    "    v.requestFullscreen();"
                    "  } else {"
                    "    document.exitFullscreen();"
                    "  }"
                    "}"
                )
                return f"Toggled fullscreen, {Config.USER_NAME}."
            except Exception as e:
                log.error(f"Fullscreen error: {e}")
        return f"Couldn't toggle fullscreen, {Config.USER_NAME}."

    # ── Scrolling ───────────────────────────────────────────────────────────
    def scroll(self, direction: str, amount: int = 500) -> str:
        if self._ensure_alive():
            try:
                sign = "" if direction == "down" else "-"
                self._js(f"window.scrollBy(0, {sign}{amount});")
                return f"Scrolled {direction}, {Config.USER_NAME}."
            except Exception as e:
                log.error(f"Scroll error: {e}")
        return f"Couldn't scroll, {Config.USER_NAME}."

    def scroll_top(self) -> str:
        if self._ensure_alive():
            try:
                self._js("window.scrollTo(0, 0);")
                return f"Back to top, {Config.USER_NAME}."
            except Exception:
                pass
        return f"Couldn't scroll to top, {Config.USER_NAME}."

    def scroll_bottom(self) -> str:
        if self._ensure_alive():
            try:
                self._js("window.scrollTo(0, document.body.scrollHeight);")
                return f"Scrolled to bottom, {Config.USER_NAME}."
            except Exception:
                pass
        return f"Couldn't scroll to bottom, {Config.USER_NAME}."

    # ── Tabs ────────────────────────────────────────────────────────────────
    def new_tab(self, url: str | None = None) -> str:
        if self._ensure_alive():
            try:
                self._js("window.open('');")
                self.driver.switch_to.window(self.driver.window_handles[-1])
                if url:
                    self.driver.get(url)
                return f"Opened new tab, {Config.USER_NAME}."
            except Exception as e:
                log.error(f"New tab error: {e}")
        return f"Couldn't open new tab, {Config.USER_NAME}."

    def close_tab(self) -> str:
        if self._ensure_alive():
            try:
                self.driver.close()
                if self.driver.window_handles:
                    self.driver.switch_to.window(self.driver.window_handles[-1])
                return f"Closed tab, {Config.USER_NAME}."
            except Exception as e:
                log.error(f"Close tab error: {e}")
        return f"Couldn't close tab, {Config.USER_NAME}."

    def next_tab(self) -> str:
        if self._ensure_alive():
            try:
                handles = self.driver.window_handles
                idx     = handles.index(self.driver.current_window_handle)
                self.driver.switch_to.window(handles[(idx + 1) % len(handles)])
                return f"Switched tab, {Config.USER_NAME}."
            except Exception as e:
                log.error(f"Next tab error: {e}")
        return f"Couldn't switch tab, {Config.USER_NAME}."

    # ── Page reading ────────────────────────────────────────────────────────
    def read_page(self) -> str:
        if not self._ensure_alive():
            return ""
        try:
            import re
            html = self.driver.page_source
            text = re.sub(r"<[^>]+>", " ", html)
            return re.sub(r"\s+", " ", text).strip()[:3000]
        except Exception as e:
            log.error(f"Read page error: {e}")
            return ""

    def get_page_title(self) -> str:
        if self._ensure_alive():
            try:
                return self.driver.title
            except Exception:
                pass
        return ""

    # ── Cleanup ─────────────────────────────────────────────────────────────
    def cleanup(self) -> None:
        self._stop_keepalive()
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
