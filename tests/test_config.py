"""Tests for config module."""

import os
import sys
from unittest import mock

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_default_config():
    """AppConfig should build with all defaults without error."""
    from config import AppConfig
    cfg = AppConfig()
    assert cfg.audio.sample_rate == 16000
    assert cfg.audio.channels == 1
    assert cfg.audio.chunk_duration == 3.0
    assert cfg.audio.energy_threshold == 0.005
    assert cfg.transcriber.backend == "local"
    assert cfg.transcriber.whisper_model == "base.en"
    assert cfg.llm.provider == "anthropic"
    assert cfg.llm.push_interval == 35.0
    assert cfg.llm.silence_trigger == 4.0
    assert cfg.llm.temperature == 0.4
    assert cfg.llm.meeting_context == ""
    assert cfg.ui.opacity == 0.88
    assert cfg.ui.max_lines == 200
    assert cfg.log_dir == ""


def test_env_overrides():
    """Environment variables should override defaults."""
    env = {
        "ECHOLOOP_TRANSCRIBER": "deepgram",
        "ECHOLOOP_LLM_PROVIDER": "openai",
        "ECHOLOOP_PUSH_INTERVAL": "20",
        "ECHOLOOP_ENERGY_THRESHOLD": "0.01",
        "ECHOLOOP_LLM_TEMPERATURE": "0.7",
        "ECHOLOOP_MEETING_CONTEXT": "Board meeting with investors",
        "ECHOLOOP_OPACITY": "0.5",
        "ECHOLOOP_LOG_DIR": "/tmp/echoloop",
    }
    with mock.patch.dict(os.environ, env):
        # Force reimport to pick up new env
        import importlib
        import config
        importlib.reload(config)
        cfg = config.AppConfig()

        assert cfg.transcriber.backend == "deepgram"
        assert cfg.llm.provider == "openai"
        assert cfg.llm.push_interval == 20.0
        assert cfg.audio.energy_threshold == 0.01
        assert cfg.llm.temperature == 0.7
        assert cfg.llm.meeting_context == "Board meeting with investors"
        assert cfg.ui.opacity == 0.5
        assert cfg.log_dir == "/tmp/echoloop"

    # Reload again to restore defaults for other tests
    importlib.reload(config)


def test_validate_missing_anthropic_key():
    from config import AppConfig
    cfg = AppConfig()
    cfg.llm.provider = "anthropic"
    cfg.llm.anthropic_api_key = ""
    issues = cfg.validate()
    assert any("ANTHROPIC_API_KEY" in i for i in issues)


def test_validate_missing_openai_key():
    from config import AppConfig
    cfg = AppConfig()
    cfg.llm.provider = "openai"
    cfg.llm.openai_api_key = ""
    issues = cfg.validate()
    assert any("OPENAI_API_KEY" in i for i in issues)


def test_validate_bad_opacity():
    from config import AppConfig
    cfg = AppConfig()
    cfg.llm.anthropic_api_key = "test"  # prevent key error
    cfg.ui.opacity = 1.5
    issues = cfg.validate()
    assert any("ECHOLOOP_OPACITY" in i for i in issues)


def test_validate_clean_config():
    from config import AppConfig
    cfg = AppConfig()
    cfg.llm.anthropic_api_key = "sk-test"
    issues = cfg.validate()
    assert len(issues) == 0


def test_validate_bad_provider():
    from config import AppConfig
    cfg = AppConfig()
    cfg.llm.provider = "gemini"
    issues = cfg.validate()
    assert any("ECHOLOOP_LLM_PROVIDER" in i for i in issues)
