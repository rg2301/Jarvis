"""Background monitors that feed live data into the HUD event bus.

- StatsMonitor: emits CPU/RAM/disk every few seconds via psutil.
- MicMonitor:   emits an RMS amplitude (0..1) at ~30 Hz from the system mic
                so the HUD waveform reflects what Jarvis itself hears,
                not what the browser tab can see.

Both are best-effort: if the underlying library is missing or the device is
busy, the monitor logs a warning and silently goes idle.
"""

from __future__ import annotations

import math
import struct
import threading
import time

from .config import log
from .events import bus


class StatsMonitor:
    def __init__(self, interval: float = 2.0) -> None:
        self.interval = interval

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="stats-monitor").start()

    def _run(self) -> None:
        try:
            import psutil
        except ImportError:
            log.warning("psutil missing — stats monitor disabled.")
            return
        # Prime cpu_percent so the first sample is meaningful.
        psutil.cpu_percent(interval=None)
        while True:
            try:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory().percent
                disk = psutil.disk_usage("/").percent
                bus.emit("stats", cpu=cpu, mem=mem, disk=disk)
            except Exception as e:
                log.debug(f"StatsMonitor sample failed: {e}")
            time.sleep(self.interval)


class MicMonitor:
    """Continuous low-priority PyAudio sampler that emits RMS amplitude."""

    def __init__(self, rate: int = 16000, chunk: int = 512, hz: float = 30.0) -> None:
        self.rate = rate
        self.chunk = chunk
        self.min_interval = 1.0 / hz

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="mic-monitor").start()

    def _run(self) -> None:
        try:
            import pyaudio
        except ImportError:
            log.warning("pyaudio missing — mic monitor disabled.")
            return

        pa = pyaudio.PyAudio()
        fmt = f"{self.chunk}h"

        def open_stream():
            try:
                return pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.rate,
                    input=True,
                    frames_per_buffer=self.chunk,
                )
            except Exception as e:
                log.warning(f"Mic monitor could not open input device: {e}")
                return None

        stream = open_stream()
        if stream is None:
            return

        last_emit = 0.0
        # Real silence has a noise floor; an exact zero sum across a chunk means
        # the stream went stale (typically after SR's Microphone briefly grabbed
        # the device). Reopen after a short run of dead reads.
        dead_reads = 0
        DEAD_THRESHOLD = 30  # ~1 sec at 30 Hz

        while True:
            try:
                data = stream.read(self.chunk, exception_on_overflow=False)
                samples = struct.unpack(fmt, data)
                ssum = sum(s * s for s in samples)
                if ssum == 0:
                    dead_reads += 1
                    if dead_reads >= DEAD_THRESHOLD:
                        log.debug("MicMonitor stream went silent — reopening.")
                        try: stream.close()
                        except Exception: pass
                        stream = open_stream()
                        dead_reads = 0
                        if stream is None:
                            time.sleep(1.0)
                            stream = open_stream()
                            if stream is None:
                                return
                        continue
                else:
                    dead_reads = 0

                rms = math.sqrt(ssum / len(samples)) / 32768.0
                amp = min(1.0, rms * 5.0)
                now = time.time()
                if now - last_emit >= self.min_interval:
                    bus.emit("volume", amp=amp)
                    last_emit = now
            except Exception as e:
                log.debug(f"MicMonitor read error: {e}")
                try: stream.close()
                except Exception: pass
                stream = open_stream()
                if stream is None:
                    time.sleep(1.0)
                    stream = open_stream()
                    if stream is None:
                        return


def start_all() -> None:
    StatsMonitor().start()
    MicMonitor().start()
