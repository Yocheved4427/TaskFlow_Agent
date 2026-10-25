"""Pass/fail checks for scenario.json. Most of them read the saved state on
disk, not the reply text, so they test what the agent actually did."""
from __future__ import annotations

from datetime import date

from shared.store import TaskStore


def _by_title(store, needle):
    return [t for t in store.tasks() if needle.lower() in t["title"].lower()]


def check_tasks_saved(store, turns, spec):
    missing = []
    for want in spec["tasks"]:
        found = [t for t in _by_title(store, want["title"]) if t["due"] == want["due"]
                 and t["category"] == want["category"]]
        if not found:
            missing.append(want["title"])
    return not missing, f"missing={missing} total={len(store.tasks())}"


def check_task_completed(store, turns, spec):
    hits = _by_title(store, spec["completed"])
    return bool(hits) and all(t["status"] == "done" for t in hits), f"{[(t['id'], t['status']) for t in hits]}"


def check_rules_persisted(store, turns, spec):
    rules = {(r["weekday"], r["applies_to"]) for r in store.memory()["rules"]}
    want = {tuple(r) for r in spec["rules"]}
    return want <= rules, f"rules={sorted(rules)}"


def check_contradiction_blocked(store, turns, spec):
    bad = []
    for t in store.tasks():
        wd = date.fromisoformat(t["due"]).weekday()
        if wd == 5 or (wd == 4 and t["category"] == "work") or t["due"] in spec["forbidden_dates"]:
            bad.append(f'{t["title"]}@{t["due"]}')
    return not bad, f"violations={bad}"


def check_external_tool_used(store, turns, spec):
    called = any("check_holidays" in t["tools_called"] for t in turns)
    cache = store.holidays()
    return called and bool(cache), f"called={called} cache={ {k: v['source'] for k, v in cache.items()} }"


def check_holiday_aware_date(store, turns, spec):
    want = spec["holiday_aware"]
    hits = _by_title(store, want["title"])
    return any(t["due"] == want["due"] for t in hits), f"{[(t['title'], t['due']) for t in hits]}"


def check_session2_recall(store, turns, spec):
    turn = next(t for t in turns if t["id"] == spec["recall_turn"])
    text = turn["reply"].lower()
    ok = any(w in text for w in ("saturday", "shabbat")) and "friday" in text
    return ok, "reply mentions both rules" if ok else f"reply={turn['reply'][:120]!r}"


CHECKS = {
    "tasks_saved": check_tasks_saved,
    "task_completed": check_task_completed,
    "rules_persisted": check_rules_persisted,
    "contradiction_blocked": check_contradiction_blocked,
    "external_tool_used": check_external_tool_used,
    "holiday_aware_date": check_holiday_aware_date,
    "session2_recall": check_session2_recall,
}


def run_checks(state_dir, today, turns, scenario) -> list[dict]:
    store = TaskStore(state_dir, today)
    out = []
    for name in scenario["checks"]:
        try:
            ok, detail = CHECKS[name](store, turns, scenario["expect"])
        except Exception as exc:  # a crashing check is a failing check
            ok, detail = False, f"error: {exc}"
        out.append({"check": name, "passed": bool(ok), "detail": detail})
    return out
