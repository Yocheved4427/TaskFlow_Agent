import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "SDK", ROOT / "API"):  # API first: both have agent.py
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

TODAY = "2027-04-11"  # a Sunday


@pytest.fixture
def store(tmp_path):
    from shared.store import TaskStore
    return TaskStore(tmp_path / "state", TODAY)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No test may touch the network: the holiday API falls back to the file."""
    import shared.tools as t

    def blocked(url):
        raise OSError("network disabled in tests")

    monkeypatch.setattr(t, "HTTP_GET", blocked)
