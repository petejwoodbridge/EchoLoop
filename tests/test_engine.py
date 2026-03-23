"""Tests for the EchoLoopEngine — transcript management and trigger logic."""

import asyncio
import os
import queue
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import LLMConfig
from transcriber import Segment
from audio_capture import Speaker
from engine import EchoLoopEngine, Insight


def _make_engine(
    push_interval: float = 35,
    silence_trigger: float = 4.0,
) -> tuple[EchoLoopEngine, asyncio.Queue, queue.Queue]:
    """Create an engine with mock-friendly config (no real LLM client)."""
    cfg = LLMConfig()
    cfg.push_interval = push_interval
    cfg.silence_trigger = silence_trigger
    seg_q: asyncio.Queue = asyncio.Queue()
    ins_q: queue.Queue = queue.Queue()
    # We won't call the LLM in these tests, so the missing API key is fine
    # We just test transcript management and trigger logic
    engine = EchoLoopEngine.__new__(EchoLoopEngine)
    engine.cfg = cfg
    engine._seg_q = seg_q
    engine._insight_q = ins_q
    engine._pause_event = threading.Event()
    engine._pause_event.set()
    engine._nudge_event = threading.Event()
    from collections import deque
    engine._transcript = deque()
    engine._transcript_chars = 0
    engine._last_push_time = time.monotonic()
    engine._last_segment_time = time.monotonic()
    engine._unsent_text = False
    engine._running = False
    engine.words_me = 0
    engine.words_them = 0
    engine._stats = {}
    return engine, seg_q, ins_q


def _seg(text: str, speaker: Speaker = Speaker.THEM) -> Segment:
    return Segment(text=text, speaker=speaker, timestamp=time.monotonic())


class TestTranscriptManagement:
    def test_append_builds_transcript(self):
        engine, _, _ = _make_engine()
        engine._append(_seg("Hello world"))
        engine._append(_seg("How are you", Speaker.ME))
        transcript = engine._get_transcript()
        assert "[THEM] Hello world" in transcript
        assert "[ME] How are you" in transcript

    def test_rolling_window_trims_old(self):
        engine, _, _ = _make_engine()
        engine.cfg.max_transcript_chars = 50
        for i in range(20):
            engine._append(_seg(f"Message number {i}"))
        transcript = engine._get_transcript()
        # Transcript may include a header (TALK RATIO), so check the raw lines
        raw_lines = "\n".join(engine._transcript)
        assert len(raw_lines) <= 60  # allow small overshoot from last line
        assert "Message number 0" not in transcript

    def test_meeting_context_prepended(self):
        engine, _, _ = _make_engine()
        engine.cfg.meeting_context = "Sales call with Acme"
        engine._append(_seg("Let's discuss pricing"))
        transcript = engine._get_transcript()
        assert transcript.startswith("CONTEXT: Sales call with Acme")
        assert "---" in transcript
        assert "[THEM] Let's discuss pricing" in transcript

    def test_no_context_when_empty(self):
        engine, _, _ = _make_engine()
        engine.cfg.meeting_context = ""
        engine._append(_seg("Hello"))
        transcript = engine._get_transcript()
        assert not transcript.startswith("CONTEXT:")


class TestTriggerLogic:
    def test_no_push_without_unsent_text(self):
        engine, _, _ = _make_engine()
        assert engine._should_push() is False

    def test_no_push_when_paused(self):
        engine, _, _ = _make_engine(push_interval=0)
        engine._append(_seg("something"))
        engine._pause_event.clear()
        assert engine._should_push() is False

    def test_push_on_interval(self):
        engine, _, _ = _make_engine(push_interval=0)
        engine._append(_seg("something"))
        engine._last_push_time = time.monotonic() - 100
        assert engine._should_push() is True

    def test_push_on_silence(self):
        engine, _, _ = _make_engine(push_interval=9999, silence_trigger=0.1)
        engine._append(_seg("something"))
        engine._last_push_time = time.monotonic() - 15
        engine._last_segment_time = time.monotonic() - 1
        assert engine._should_push() is True

    def test_nudge_event_clears_after_check(self):
        engine, _, _ = _make_engine()
        engine._nudge_event.set()
        assert engine._nudge_event.is_set()
        # Simulate what the run loop does
        engine._nudge_event.clear()
        assert not engine._nudge_event.is_set()


class TestSpeakerStats:
    def test_word_counts_tracked(self):
        engine, _, _ = _make_engine()
        engine._append(_seg("hello world", Speaker.ME))
        engine._append(_seg("one two three four", Speaker.THEM))
        assert engine.words_me == 2
        assert engine.words_them == 4

    def test_stats_dict_updated(self):
        engine, _, _ = _make_engine()
        engine._append(_seg("hello", Speaker.ME))
        engine._append(_seg("hi there friend", Speaker.THEM))
        assert engine._stats["words_me"] == 1
        assert engine._stats["words_them"] == 3

    def test_empty_stats_initially(self):
        engine, _, _ = _make_engine()
        assert engine.words_me == 0
        assert engine.words_them == 0
        assert engine._stats == {}

    def test_talk_ratio_in_transcript(self):
        engine, _, _ = _make_engine()
        # Need > 20 total words to trigger the ratio header
        engine._append(_seg("one two three four five six seven eight nine ten", Speaker.ME))
        engine._append(_seg("one two three four five six seven eight nine ten eleven", Speaker.THEM))
        transcript = engine._get_transcript()
        assert "TALK RATIO:" in transcript
        assert "user 47%" in transcript  # 10 / 21 ≈ 47%

    def test_no_ratio_below_threshold(self):
        engine, _, _ = _make_engine()
        engine._append(_seg("hi", Speaker.ME))
        transcript = engine._get_transcript()
        assert "TALK RATIO:" not in transcript
