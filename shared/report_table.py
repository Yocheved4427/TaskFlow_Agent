"""Print the REPORT.md comparison tables from results/api.json and results/sdk.json.

    python -m shared.report_table
"""
from __future__ import annotations

import json

from shared.metrics import HARNESS_PARTS, ROOT


def load(name):
    p = ROOT / "results" / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cell(d, key, fmt="{:,}"):
    return fmt.format(d["totals"][key]) if d else "not run yet"


def main() -> None:
    api, sdk = load("api"), load("sdk")
    rows = [("input (uncached)", "input_tokens", "{:,}"), ("cache read", "cache_read_tokens", "{:,}"),
            ("cache write", "cache_write_tokens", "{:,}"), ("output", "output_tokens", "{:,}"),
            ("cache hit %", "cache_hit_pct", "{}%"), ("model calls", "model_calls", "{}"),
            ("cost (USD)", "cost_usd", "${:.4f}"), ("time (seconds)", "seconds", "{}")]
    print("| Metric | API | SDK |\n|---|---:|---:|")
    for label, key, fmt in rows:
        print(f"| {label} | {cell(api, key, fmt)} | {cell(sdk, key, fmt)} |")
    print(f"| checks passed | {api['checks_passed'] if api else 'not run yet'} | {sdk['checks_passed'] if sdk else 'not run yet'} |")
    print("\n| Turn | API in/read/write/out | API $ | SDK in/read/write/out | SDK $ |\n|---|---|---:|---|---:|")
    for i in range(len((api or sdk)["turns"])):
        def t(d):
            if not d:
                return "pending", "-"
            x = d["turns"][i]
            return (f"{x['input_tokens']}/{x['cache_read_tokens']}/{x['cache_write_tokens']}/{x['output_tokens']}",
                    f"{x['cost_usd']:.4f}")
        a, s = t(api), t(sdk)
        print(f"| {(api or sdk)['turns'][i]['id']} | {a[0]} | {a[1]} | {s[0]} | {s[1]} |")


if __name__ == "__main__":
    main()
