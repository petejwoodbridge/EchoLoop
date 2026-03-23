"""
EchoLoop · Main
───────────────
Orchestrator that wires AudioCapture → Transcriber → Engine → UI
and manages the async event loop alongside the Tkinter main loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
import queue
import sys
import threading
from datetime import datetime
from pathlib import Path

from audio_capture import AudioCapture
from config import AppConfig
from engine import EchoLoopEngine, Insight
from transcriber import Segment, Transcriber
from ui import EchoLoopUI

# ── Logging ──────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-22s  %(levelname)-5s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("echoloop")


# ── Session file logger ──────────────────────────────────────────────

class SessionLogger:
    """
    Appends timestamped transcript lines and insights to a log file.
    Disabled when log_dir is empty.
    """

    def __init__(self, log_dir: str) -> None:
        self._file = None
        if not log_dir:
            return
        path = Path(log_dir)
        path.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self._path = path / f"echoloop_{stamp}.log"
        self._file = open(self._path, "a", encoding="utf-8", buffering=1)
        log.info("Session log: %s", self._path)

    def log_segment(self, seg: Segment) -> None:
        if not self._file:
            return
        tag = "[ME]" if seg.speaker.name == "ME" else "[THEM]"
        ts = datetime.now().strftime("%H:%M:%S")
        self._file.write(f"{ts}  {tag} {seg.text}\n")

    def log_insight(self, insight: Insight) -> None:
        if not self._file:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        self._file.write(f"{ts}  [INSIGHT] {insight.text}\n")

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None


# ── Device picker (interactive) ──────────────────────────────────────

def pick_device_interactive() -> str | None:
    """If no system device is configured, let the user pick one."""
    devices = AudioCapture.list_input_devices()
    if not devices:
        log.error("No input audio devices found!")
        sys.exit(1)

    print("\n┌─ Available input devices ───────────────────────────┐")
    for d in devices:
        print(f"│  [{d['index']:>2}]  {d['name']:<44} ch={d['channels']}")
    print("└────────────────────────────────────────────────────┘")
    print()
    print("  Enter the INDEX of your virtual cable / loopback device")
    print("  (this captures what others say in the meeting).")
    print("  Press Enter to skip (will use default input).\n")

    choice = input("  System audio device index: ").strip()
    if not choice:
        return None

    try:
        idx = int(choice)
        match = next((d for d in devices if d["index"] == idx), None)
        if match:
            return match["name"]
    except ValueError:
        pass

    print("  → Invalid choice, using default device.")
    return None


# ── Async engine runner ──────────────────────────────────────────────

def _run_async_loop(
    transcriber: Transcriber,
    engine: EchoLoopEngine,
    stop_event: threading.Event,
    session_logger: SessionLogger,
) -> None:
    """Runs in a daemon thread – hosts the asyncio event loop."""

    async def _main() -> None:
        # Wrap the transcriber to also log segments
        original_seg_q = engine._seg_q

        t_task = asyncio.create_task(transcriber.run())
        e_task = asyncio.create_task(engine.run())

        # Wait until the stop event is set (from the main/UI thread)
        while not stop_event.is_set():
            await asyncio.sleep(0.25)

        transcriber.stop()
        engine.stop()
        t_task.cancel()
        e_task.cancel()
        try:
            await asyncio.gather(t_task, e_task, return_exceptions=True)
        except Exception:
            pass

    asyncio.run(_main())


# ── Entry point ──────────────────────────────────────────────────────

def main() -> None:
    cfg = AppConfig()

    # Interactive device selection if not set via env
    if cfg.audio.system_device is None:
        chosen = pick_device_interactive()
        if chosen:
            cfg.audio.system_device = chosen

    # Session logger
    session_logger = SessionLogger(cfg.log_dir)

    # Shared pause event (set = running, clear = paused)
    pause_event = threading.Event()
    pause_event.set()

    # Components — use AudioCapture's own chunk_queue
    audio = AudioCapture(cfg.audio)
    chunk_queue = audio.chunk_queue

    # Wrap the segment queue to intercept segments for logging
    segment_queue: asyncio.Queue[Segment] = asyncio.Queue(maxsize=500)
    insight_queue: queue.Queue[Insight] = queue.Queue(maxsize=100)

    # Tap into insight queue for logging
    class _LoggingInsightQueue:
        """Proxy that logs insights as they flow through."""

        def __init__(self, real_q: queue.Queue[Insight], logger: SessionLogger):
            self._q = real_q
            self._logger = logger

        def put_nowait(self, item: Insight) -> None:
            self._logger.log_insight(item)
            self._q.put_nowait(item)

        def get_nowait(self) -> Insight:
            return self._q.get_nowait()

        def __getattr__(self, name):
            return getattr(self._q, name)

    logging_insight_q = _LoggingInsightQueue(insight_queue, session_logger)

    transcriber = Transcriber(cfg.transcriber, chunk_queue, segment_queue)
    engine = EchoLoopEngine(
        cfg.llm, segment_queue, logging_insight_q, pause_event=pause_event
    )

    stop_event = threading.Event()

    def shutdown() -> None:
        log.info("Shutting down…")
        stop_event.set()
        audio.stop()
        session_logger.close()

    # Start audio capture threads
    audio.start()

    # Start async loop (transcriber + engine) in a background thread
    async_thread = threading.Thread(
        target=_run_async_loop,
        args=(transcriber, engine, stop_event, session_logger),
        daemon=True,
        name="async-loop",
    )
    async_thread.start()

    # Run UI on the main thread (blocks until window is closed)
    log.info("EchoLoop is live. Close the overlay window to exit.")
    ui = EchoLoopUI(cfg.ui, insight_queue, pause_event=pause_event, on_close=shutdown)
    ui.run()

    # Cleanup
    stop_event.set()
    audio.stop()
    session_logger.close()
    async_thread.join(timeout=3)
    log.info("EchoLoop stopped.")


if __name__ == "__main__":
    main()
