"""Tests for SessionLogger — file writing and markdown export."""

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine import Insight


class TestSessionLogger:
    def test_disabled_when_empty_dir(self):
        from main import SessionLogger
        logger = SessionLogger("")
        # Should not raise
        logger.log_segment("hello", "ME")
        logger.close()

    def test_writes_log_file(self):
        from main import SessionLogger
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(tmpdir)
            logger.log_segment("hello world", "ME")
            logger.log_segment("hi there", "THEM")
            logger.log_insight(Insight(text="Press on budget", timestamp=time.monotonic()))
            logger.close()

            # Check .log file exists and has content
            log_files = list(Path(tmpdir).glob("*.log"))
            assert len(log_files) == 1
            content = log_files[0].read_text(encoding="utf-8")
            assert "[ME] hello world" in content
            assert "[THEM] hi there" in content
            assert "[INSIGHT] Press on budget" in content

    def test_exports_markdown(self):
        from main import SessionLogger
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(tmpdir)
            logger.log_segment("talking about pricing", "THEM")
            logger.log_insight(Insight(text="- Push back on the discount", timestamp=time.monotonic()))
            logger.close()

            md_files = list(Path(tmpdir).glob("*.md"))
            assert len(md_files) == 1
            content = md_files[0].read_text(encoding="utf-8")
            assert "# EchoLoop Session" in content
            assert "Key Insights" in content
            assert "Full Transcript" in content
            assert "talking about pricing" in content

    def test_no_markdown_when_empty(self):
        from main import SessionLogger
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(tmpdir)
            logger.close()  # no segments or insights

            md_files = list(Path(tmpdir).glob("*.md"))
            assert len(md_files) == 0
