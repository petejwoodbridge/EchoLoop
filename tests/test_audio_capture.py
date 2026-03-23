"""Tests for audio capture — energy gating and chunk construction."""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from audio_capture import AudioChunk, Speaker


class TestAudioChunk:
    def test_chunk_creation(self):
        audio = np.zeros(16000, dtype=np.float32)
        chunk = AudioChunk(audio=audio, speaker=Speaker.THEM, timestamp=time.monotonic())
        assert chunk.speaker is Speaker.THEM
        assert chunk.audio.shape == (16000,)

    def test_speaker_enum(self):
        assert Speaker.ME.name == "ME"
        assert Speaker.THEM.name == "THEM"


class TestEnergyGating:
    """Test the RMS energy logic that's used in the audio callback."""

    def test_silence_below_threshold(self):
        silence = np.zeros(16000, dtype=np.float32)
        rms = np.sqrt(np.mean(silence ** 2))
        assert rms < 0.005

    def test_speech_above_threshold(self):
        # Simulate speech-level signal
        t = np.linspace(0, 1, 16000, dtype=np.float32)
        signal = 0.1 * np.sin(2 * np.pi * 440 * t)
        rms = np.sqrt(np.mean(signal ** 2))
        assert rms > 0.005

    def test_quiet_noise_below_threshold(self):
        rng = np.random.default_rng(42)
        noise = rng.normal(0, 0.001, 16000).astype(np.float32)
        rms = np.sqrt(np.mean(noise ** 2))
        assert rms < 0.005

    def test_moderate_noise_above_threshold(self):
        rng = np.random.default_rng(42)
        noise = rng.normal(0, 0.05, 16000).astype(np.float32)
        rms = np.sqrt(np.mean(noise ** 2))
        assert rms > 0.005
