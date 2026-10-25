"""Domain tools of the task manager, shared by the API and SDK versions.

Each tool is a plain function `fn(store, **args) -> dict`. Tools return small,
compact dicts (ids, counts, short rows) instead of echoing full records, so
tool results stay cheap in tokens. Invalid input raises ToolError; the harness
turns it into an `is_error` tool result the model can react to.
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from shared.store import CATEGORIES, MEMORY_KINDS, PRIORITIES, TaskStore

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
HOLIDAY_API = "https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"
FALLBACK_DIR = Path(__file__).parent / "data"


class ToolError(Exception):
    """Raised for bad tool input; reported back to the model as is_error."""


def _date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ToolError(f"{field} must be YYYY-MM-DD, got {value!r}")


def _weekday(d: date) -> str:
    return WEEKDAYS[d.weekday()]


def _holiday_names(store: TaskStore) -> dict[str, str]:
    return {h["date"]: h["name"] for entry in store.holidays().values() for h in entry["items"]}


def rule_violation(store: TaskStore, due: date, category: str) -> str | None:
    """Return the saved rule that forbids this task, if any."""
    for r in store.memory()["rules"]:
        if r["weekday"] == _weekday(due) and r["applies_to"] in ("all", category):
            return f"{r['applies_to']} tasks are not allowed on {r['weekday']} (saved rule: {r['text']})"
    return None


# --------------------------------------------------------------------------
# tasks
# --------------------------------------------------------------------------
def add_task(store: TaskStore, title: str, due: str, category: str, priority: str = "medium") -> dict:
    title = title.strip()
    if not title:
        raise ToolError("title is empty")
    if category not in CATEGORIES:
        raise ToolError(f"category must be one of {list(CATEGORIES)}")
    if priority not in PRIORITIES:
        raise ToolError(f"priority must be one of {list(PRIORITIES)}")
    due_d = _date(due, "due")
    if due_d < store.today:
        raise ToolError(f"due {due} is in the past (today is {store.today})")
    if why := rule_violation(store, due_d, category):
        raise ToolError(f"refused: {why}. Ask the user for another date.")

    tasks = store.tasks()
    existing = next((t for t in tasks if t["title"].lower() == title.lower() and t["status"] == "open"), None)
    if existing:
        existing.update(due=due, category=category, priority=priority)
        task_id = existing["id"]
    else:
        task_id = f"T{len(tasks) + 1}"
        tasks.append({"id": task_id, "title": title, "due": due, "category": category,
                      "priority": priority, "status": "open"})
    store.save_tasks(tasks)
    out = {"id": task_id, "updated": bool(existing), "weekday": _weekday(due_d)}
    if holiday := _holiday_names(store).get(due):
        out["warning"] = f"{due} is a public holiday ({holiday})"
    return out


def list_tasks(store: TaskStore, category: str | None = None, status: str = "open",
               due_within_days: int | None = None) -> dict:
    rows = []
    for t in sorted(store.tasks(), key=lambda t: (t["due"], t["id"])):
        if category and t["category"] != category:
            continue
        if status != "all" and t["status"] != status:
            continue
        if due_within_days is not None and date.fromisoformat(t["due"]) > store.today + timedelta(days=due_within_days):
            continue
        rows.append(f'{t["id"]}|{t["title"]}|{t["due"]}|{t["category"]}|{t["priority"]}|{t["status"]}')
    return {"count": len(rows), "tasks": rows}


def complete_task(store: TaskStore, task_id: str) -> dict:
    tasks = store.tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if task is None:
        raise ToolError(f"no task {task_id!r}; call list_tasks to see ids")
    if task["status"] == "done":
        return {"id": task_id, "already_done": True}
    task["status"] = "done"
    task["done_on"] = store.today.isoformat()
    store.save_tasks(tasks)
    return {"id": task_id, "status": "done", "open_left": sum(t["status"] == "open" for t in tasks)}


# --------------------------------------------------------------------------
# memory
# --------------------------------------------------------------------------
def remember(store: TaskStore, kind: str, text: str, weekday: str | None = None,
             applies_to: str | None = None) -> dict:
    if kind not in MEMORY_KINDS:
        raise ToolError(f"kind must be one of {list(MEMORY_KINDS)}")
    text = text.strip()
    if not text:
        raise ToolError("text is empty")
    mem = store.memory()
    if kind == "rule":
        weekday = (weekday or "").strip().lower()
        applies_to = (applies_to or "all").strip().lower()
        if weekday not in WEEKDAYS:
            raise ToolError("a rule needs weekday: an English weekday name like 'saturday'")
        if applies_to != "all" and applies_to not in CATEGORIES:
            raise ToolError(f"applies_to must be 'all' or one of {list(CATEGORIES)}")
        for r in mem["rules"]:
            if r["weekday"] == weekday and r["applies_to"] == applies_to:
                r.update(text=text, date=store.today.isoformat())
                store.save_memory(mem)
                return {"saved": "rule", "replaced": True, "rules": len(mem["rules"])}
        mem["rules"].append({"weekday": weekday, "applies_to": applies_to, "text": text,
                             "date": store.today.isoformat()})
        store.save_memory(mem)
        return {"saved": "rule", "replaced": False, "rules": len(mem["rules"])}
    mem["notes"].append({"kind": kind, "text": text, "date": store.today.isoformat()})
    store.save_memory(mem)
    return {"saved": kind, "notes": len(mem["notes"])}


def recall(store: TaskStore, query: str = "") -> dict:
    mem = store.memory()
    words = {w for w in re.findall(r"\w+", query.lower()) if len(w) > 2}
    notes = [f'{n["kind"]}: {n["text"]}' for n in mem["notes"]
             if not words or words & set(re.findall(r"\w+", n["text"].lower()))]
    rules = [f'no {r["applies_to"]} on {r["weekday"]}' for r in mem["rules"]]
    return {"rules": rules, "notes": notes[-5:]}


# --------------------------------------------------------------------------
# external: public holidays (internet, with offline fallback file)
# --------------------------------------------------------------------------
def _http_get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "taskflow-agent/1.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


# Tests replace this to stay offline.
HTTP_GET = _http_get_json


def check_holidays(store: TaskStore, year: int, country: str = "IL", month: int | None = None) -> dict:
    year, country = int(year), country.upper()
    cache = store.holidays()
    key = f"{country}-{year}"
    if key not in cache:
        try:
            raw = HTTP_GET(HOLIDAY_API.format(year=year, country=country))
            # The API returns ~10 fields per holiday; keep only date and name.
            items = [{"date": h["date"], "name": h.get("name") or h.get("localName")} for h in raw]
            source = "nager.date"
        except Exception as exc:  # network down or blocked: use bundled data
            fb = FALLBACK_DIR / f"holidays_{country}_{year}.json"
            if not fb.exists():
                raise ToolError(f"holiday API unreachable ({exc.__class__.__name__}) and no fallback for {key}")
            items = json.loads(fb.read_text(encoding="utf-8"))
            source = "fallback-file"
        cache[key] = {"source": source, "items": items}
        store.save_holidays(cache)
    entry = cache[key]
    items = entry["items"]
    if month:
        items = [h for h in items if int(h["date"][5:7]) == int(month)]
    return {"source": entry["source"],
            "holidays": [f'{h["date"]} {_weekday(date.fromisoformat(h["date"]))[:3]} {h["name"]}' for h in items]}


# --------------------------------------------------------------------------
# registry: JSON schemas (used as-is by both harnesses)
# --------------------------------------------------------------------------
TOOL_FUNCS = {f.__name__: f for f in (add_task, list_tasks, complete_task, remember, recall, check_holidays)}

TOOL_SPECS = [
    {
        "name": "add_task",
        "description": ("Add a task, or update an open task with the same title. Refuses (error) a date that breaks "
                        "a saved weekday rule. Warns if the date is a known public holiday."),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "due": {"type": "string", "description": "YYYY-MM-DD"},
                "category": {"type": "string", "enum": list(CATEGORIES)},
                "priority": {"type": "string", "enum": list(PRIORITIES)},
            },
            "required": ["title", "due", "category"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List tasks as compact rows 'id|title|due|category|priority|status', sorted by due date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": list(CATEGORIES)},
                "status": {"type": "string", "enum": ["open", "done", "all"], "description": "Default open"},
                "due_within_days": {"type": "integer"},
            },
        },
    },
    {
        "name": "complete_task",
        "description": "Mark a task as done by id.",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "e.g. T3"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "remember",
        "description": ("Save long-term memory about the user. kind=rule is a weekday restriction and needs weekday "
                        "(English name) and applies_to ('all' or a category); add_task enforces rules. "
                        "kind=preference or decision stores a free-text note."),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(MEMORY_KINDS)},
                "text": {"type": "string", "description": "The fact in a short sentence"},
                "weekday": {"type": "string", "enum": WEEKDAYS},
                "applies_to": {"type": "string", "enum": ["all", *CATEGORIES]},
            },
            "required": ["kind", "text"],
        },
    },
    {
        "name": "recall",
        "description": "Read long-term memory: all weekday rules plus notes matching the query (empty query: all).",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        },
    },
    {
        "name": "check_holidays",
        "description": "Get public holidays from the internet (date.nager.at), cached on disk. Rows 'date weekday name'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "country": {"type": "string", "description": "ISO code, default IL"},
                "month": {"type": "integer", "description": "Optional month filter 1-12"},
            },
            "required": ["year"],
        },
    },
]


def call_tool(store: TaskStore, name: str, args: dict) -> dict:
    """Run one tool by name. Raises ToolError for unknown tools or bad args."""
    fn = TOOL_FUNCS.get(name)
    if fn is None:
        raise ToolError(f"unknown tool {name!r}")
    try:
        return fn(store, **args)
    except TypeError as exc:  # missing / unexpected arguments
        raise ToolError(f"bad arguments for {name}: {exc}")


def compact(result: dict) -> str:
    """Serialize a tool result with no whitespace (cheaper in tokens)."""
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
