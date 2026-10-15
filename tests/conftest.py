"""Shared fixtures for the examfp test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from examfp.models import Paper

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "data" / "papers" / "sample.json"


@pytest.fixture
def sample_paper() -> Paper:
    """The on-disk sample paper, parsed into a :class:`Paper`."""
    return Paper.model_validate_json(SAMPLE_PATH.read_text(encoding="utf-8"))
