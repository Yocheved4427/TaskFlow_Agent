"""What goes into each turn.

Stable parts (system prompt, tool list) never change, so they stay cached.
The per-turn part is a short <context> block in front of the user's text:
today's date, relevant memory, and a one-line view of upcoming deadlines.
Full task lists and holidays are NOT sent; the model pulls them
with tools when it needs them.
"""
from __future__ import annotations

from datetime import date, timedelta

from harness import logger
from harness.memory import Memory
from shared.prompts import SYSTEM_PROMPT
from shared.store import TaskStore

log = logger(__file__)
HORIZON_DAYS = 21


def system_blocks() -> list[dict]:
    return [{"type": "text", "text": SYSTEM_PROMPT}]


def upcoming(store: TaskStore) -> str:
    limit = store.today + timedelta(days=HORIZON_DAYS)
    soon = sorted((t for t in store.tasks() if t["status"] == "open" and date.fromisoformat(t["due"]) <= limit),
                  key=lambda t: t["due"])
    if not soon:
        return "none"
    return f"{len(soon)} open, nearest {soon[0]['id']} due {soon[0]['due']} (use list_tasks for all)"


def user_turn(user_text: str, store: TaskStore, memory: Memory) -> dict:
    mem_lines = memory.relevant(user_text)
    ctx = "\n".join([
        "<context>",
        f"today: {store.today.isoformat()} ({store.today.strftime('%A')})",
        "memory:" + ("".join(f"\n- {m}" for m in mem_lines) if mem_lines else " empty"),
        f"deadlines next {HORIZON_DAYS}d: {upcoming(store)}",
        "</context>",
    ])
    log(f"turn context: {len(ctx)} chars ({len(mem_lines)} memory lines)")
    return {"role": "user", "content": [{"type": "text", "text": ctx}, {"type": "text", "text": user_text}]}
