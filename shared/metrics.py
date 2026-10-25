"""Helpers shared by both runners: scenario loading, line counts, result file."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS_PARTS = ["loop", "tools", "history", "memory", "context", "compaction", "caching", "tokens"]


def load_scenario(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def code_lines(path: Path) -> int:
    """Non-blank, non-comment lines (docstrings count as code)."""
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.strip().startswith("#"))


def api_loc() -> dict:
    harness = ROOT / "API" / "harness"
    out = {part: code_lines(harness / f"{part}.py") for part in HARNESS_PARTS}
    out["agent+main"] = code_lines(ROOT / "API" / "agent.py") + code_lines(ROOT / "API" / "main.py")
    return out


def sdk_loc() -> dict:
    """Count lines tagged '# replaces: <part>' in the SDK files."""
    out = {part: 0 for part in HARNESS_PARTS}
    pattern = re.compile(r"#\s*replaces:\s*([\w, ]+)")
    total = 0
    for f in ("agent.py", "tools.py", "main.py"):
        for line in (ROOT / "SDK" / f).read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.strip().startswith("#"):
                total += 1
            m = pattern.search(line)
            if m:
                for part in m.group(1).split(","):
                    part = part.strip()
                    if part in out:
                        out[part] += 1
    out["all_sdk_code"] = total
    return out


def summarize(turns: list[dict]) -> dict:
    keys = ["input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens", "model_calls"]
    total = {k: sum(t[k] for t in turns) for k in keys}
    total["cost_usd"] = round(sum(t["cost_usd"] for t in turns), 5)
    total["seconds"] = round(sum(t["seconds"] for t in turns), 2)
    prompt = total["input_tokens"] + total["cache_read_tokens"] + total["cache_write_tokens"]
    total["cache_hit_pct"] = round(100 * total["cache_read_tokens"] / prompt, 1) if prompt else 0.0
    return total


def write_results(out_path, payload: dict) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
