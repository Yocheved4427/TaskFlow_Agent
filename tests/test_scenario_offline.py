"""End to end: both runners on scenario.json in --mock mode."""
import json
import subprocess
import sys

import pytest

from tests.conftest import ROOT


@pytest.mark.parametrize("version", ["API", "SDK"])
def test_runner_mock(tmp_path, version):
    out = tmp_path / "r.json"
    proc = subprocess.run([sys.executable, str(ROOT / version / "main.py"), "--mock", "--scenario",
                           str(ROOT / "scenario.json"), "--out", str(out), "--state", str(tmp_path / "state")],
                          capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text())
    assert data["checks_passed"] == "7/7", data["checks"]
    assert len(data["turns"]) == 6 and {t["session"] for t in data["turns"]} == {"s1", "s2"}
    for t in data["turns"]:
        for k in ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens",
                  "model_calls", "tools_called", "cost_usd", "seconds"):
            assert k in t
    assert data["loc"]


def test_checks_fail_on_bad_state(tmp_path):
    """The checks must be able to fail: an empty state passes nothing that needs state."""
    from shared.checks import run_checks
    from shared.metrics import load_scenario
    sc = load_scenario(ROOT / "scenario.json")
    turns = [{"id": "t4", "reply": "", "tools_called": []}]
    res = {c["check"]: c["passed"] for c in run_checks(tmp_path, sc["today"], turns, sc)}
    assert not any(v for k, v in res.items() if k != "contradiction_blocked")
