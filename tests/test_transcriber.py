"""Tests for the transcriber — segment creation and stale chunk handling."""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from audio_capture import AudioChunk, Speaker
from transcriber import Segment, _STALE_THRESHOLD


class TestSegment:
    def test_repr_them(self):
        seg = Segment(text="Hello", speaker=Speaker.THEM, timestamp=0)
        assert repr(seg) == "[THEM] Hello"

    def test_repr_me(self):
        seg = Segment(text="Hi there", speaker=Speaker.ME, timestamp=0)
        assert repr(seg) == "[ME] Hi there"


class TestStaleThreshold:
    def test_fresh_chunk_is_not_stale(self):
        chunk = AudioChunk(
            audio=np.zeros(16000, dtype=np.float32),
            speaker=Speaker.THEM,
            timestamp=time.monotonic(),
        )
        age = time.monotonic() - chunk.timestamp
        assert age < _STALE_THRESHOLD

    def test_old_chunk_is_stale(self):
        chunk = AudioChunk(
            audio=np.zeros(16000, dtype=np.float32),
            speaker=Speaker.THEM,
            timestamp=time.monotonic() - 15,
        )
        age = time.monotonic() - chunk.timestamp
        assert age > _STALE_THRESHOLD
