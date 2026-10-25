"""On-disk state of the task manager: tasks, memory, holiday cache.

Every file is plain JSON inside one state directory, so a run can start from a
clean state by deleting that directory, and checks can read the state directly.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

CATEGORIES = ("work", "personal", "study", "health", "home")
PRIORITIES = ("low", "medium", "high")
MEMORY_KINDS = ("rule", "preference", "decision")


class TaskStore:
    def __init__(self, state_dir: str | os.PathLike, today: str):
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.today = date.fromisoformat(today)

    # -- generic json helpers ------------------------------------------------
    def _path(self, name: str) -> Path:
        return self.dir / f"{name}.json"

    def read(self, name: str, default: Any) -> Any:
        p = self._path(name)
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding="utf-8"))

    def write(self, name: str, data: Any) -> None:
        p = self._path(name)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)

    # -- tasks ---------------------------------------------------------------
    def tasks(self) -> list[dict]:
        return self.read("tasks", [])

    def save_tasks(self, tasks: list[dict]) -> None:
        self.write("tasks", tasks)

    # -- memory --------------------------------------------------------------
    def memory(self) -> dict:
        return self.read("memory", {"rules": [], "notes": []})

    def save_memory(self, mem: dict) -> None:
        self.write("memory", mem)

    # -- holidays ------------------------------------------------------------
    def holidays(self) -> dict:
        return self.read("holidays", {})

    def save_holidays(self, data: dict) -> None:
        self.write("holidays", data)
