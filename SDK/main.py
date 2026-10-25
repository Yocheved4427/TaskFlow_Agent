"""Run scenario.json against the SDK version and write results/sdk.json.

Runs on your Claude Code login. ANTHROPIC_API_KEY must NOT be set, or billing
moves to that key.

    python SDK/main.py --scenario scenario.json --out results/sdk.json
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "SDK")]

from agent import SDKTaskFlow  # noqa: E402
from shared.checks import run_checks  # noqa: E402
from shared.metrics import load_scenario, sdk_loc, summarize, write_results  # noqa: E402


async def run(args) -> None:
    scenario = load_scenario(args.scenario)
    state = Path(args.state).resolve()
    shutil.rmtree(state, ignore_errors=True)  # every run starts clean
    state.mkdir(parents=True)
    client_cls = None
    if args.mock:
        from tests.fakes_sdk import FakeSDKClient
        client_cls = FakeSDKClient

    turns = []
    for session in scenario["sessions"]:
        print(f"\n=== session {session['id']} (new agent instance, resume from disk) ===")
        kw = {"client_cls": client_cls} if client_cls else {}
        agent = SDKTaskFlow(state, scenario["today"], args.model, args.effort, **kw)
        await agent.connect()
        try:
            for turn in session["turns"]:
                print(f"\n--- {turn['id']} user: {turn['user']}")
                result = await agent.ask(turn["user"])
                print(f"--- {turn['id']} assistant: {result['reply']}")
                turns.append({"id": turn["id"], "session": session["id"], **result})
        finally:
            await agent.close()

    checks = run_checks(state, scenario["today"], turns, scenario)
    payload = {
        "version": "sdk", "mode": "mock" if args.mock else "live",
        "model": args.model, "effort": args.effort,
        "turns": turns, "totals": summarize(turns),
        "checks": checks, "checks_passed": f"{sum(c['passed'] for c in checks)}/{len(checks)}",
        "loc": sdk_loc(),
    }
    write_results(args.out, payload)
    print(f"\nchecks: {payload['checks_passed']}  cost: ${payload['totals']['cost_usd']}  -> {args.out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="scenario.json")
    ap.add_argument("--out", default="results/sdk.json")
    ap.add_argument("--state", default=".state/sdk")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--mock", action="store_true", help="fake SDK client, no login")
    args = ap.parse_args()
    if os.environ.pop("ANTHROPIC_API_KEY", None):
        print("[SDK/main.py] ANTHROPIC_API_KEY was set; removed it so the run uses your Claude Code login")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
