"""Run scenario.json against the API version and write results/api.json.

    export ANTHROPIC_API_KEY=...   # in the terminal only, never in code
    python API/main.py --scenario scenario.json --out results/api.json
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "API")]

from agent import TaskFlowAgent  # noqa: E402
from shared.checks import run_checks  # noqa: E402
from shared.metrics import api_loc, load_scenario, summarize, write_results  # noqa: E402


def make_client(mock: bool):
    if mock:
        from tests.fakes import ScriptedAnthropic
        return ScriptedAnthropic()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Export it in your terminal (never in code).")
    import anthropic
    return anthropic.Anthropic()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="scenario.json")
    ap.add_argument("--out", default="results/api.json")
    ap.add_argument("--state", default=".state/api")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--compact-threshold", type=int, default=40_000)
    ap.add_argument("--mock", action="store_true", help="scripted offline client, no key")
    args = ap.parse_args()

    scenario = load_scenario(args.scenario)
    shutil.rmtree(args.state, ignore_errors=True)  # every run starts clean
    client = make_client(args.mock)

    turns = []
    for session in scenario["sessions"]:
        print(f"\n=== session {session['id']} (new agent instance, state from disk) ===")
        agent = TaskFlowAgent(client, args.state, scenario["today"], args.model, args.effort,
                                  args.compact_threshold)
        for turn in session["turns"]:
            print(f"\n--- {turn['id']} user: {turn['user']}")
            result = agent.ask(turn["user"])
            print(f"--- {turn['id']} assistant: {result['reply']}")
            turns.append({"id": turn["id"], "session": session["id"], **result})

    checks = run_checks(args.state, scenario["today"], turns, scenario)
    payload = {
        "version": "api", "mode": "mock" if args.mock else "live",
        "model": args.model, "effort": args.effort,
        "turns": turns, "totals": summarize(turns),
        "checks": checks, "checks_passed": f"{sum(c['passed'] for c in checks)}/{len(checks)}",
        "loc": api_loc(),
    }
    write_results(args.out, payload)
    print(f"\nchecks: {payload['checks_passed']}  cost: ${payload['totals']['cost_usd']}  -> {args.out}")


if __name__ == "__main__":
    main()
