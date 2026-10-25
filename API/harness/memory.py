"""Long-term memory: where it lives and what gets pulled into a turn.

Memory is written by the `remember` tool into state/memory.json (shared code).
This file decides retrieval: weekday rules are always relevant to a task
manager (they are short and add_task depends on them); notes only when they
share words with the user's message.
"""
from __future__ import annotations

import re

from harness import logger
from shared.store import TaskStore

log = logger(__file__)
MAX_NOTES = 3


class Memory:
    def __init__(self, store: TaskStore):
        self.store = store

    def relevant(self, user_text: str) -> list[str]:
        mem = self.store.memory()
        lines = [f"rule: no {r['applies_to']} tasks on {r['weekday']}" for r in mem["rules"]]
        words = {w for w in re.findall(r"\w+", user_text.lower()) if len(w) > 2}
        notes = [n for n in mem["notes"] if words & set(re.findall(r"\w+", n["text"].lower()))]
        lines += [f"{n['kind']}: {n['text']}" for n in notes[-MAX_NOTES:]]
        hidden = len(mem["notes"]) - len(notes[-MAX_NOTES:])
        if hidden:
            lines.append(f"({hidden} more notes; use recall)")
        log(f"retrieved {len(lines)} memory lines ({len(mem['rules'])} rules, {len(notes)} matching notes)")
        return lines
