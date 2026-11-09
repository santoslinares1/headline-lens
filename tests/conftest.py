from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture
def now():
    return datetime(2026, 11, 6, 12, tzinfo=timezone.utc)


@pytest.fixture
def rss():
    return (Path(__file__).parent / "fixtures/sample.xml").read_bytes()
