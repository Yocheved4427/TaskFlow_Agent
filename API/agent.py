"""TaskFlow agent built on the raw Messages API, wiring the harness parts."""
from __future__ import annotations

import time
from pathlib import Path

from harness import context, logger
from harness.compaction import Compactor
from harness.history import History
from harness.loop import run_loop
from harness.memory import Memory
from harness.tokens import TokenMeter
from harness.tools import ToolRegistry
from shared.store import TaskStore

log = logger(__file__)


class TaskFlowAgent:
    def __init__(self, client, state_dir: str | Path, today: str, model: str = "claude-opus-5-5",
                 effort: str = "medium", compact_threshold: int = 40_000):
        self.client, self.model, self.effort = client, model, effort
        self.store = TaskStore(state_dir, today)
        self.history = History(Path(state_dir) / "history.jsonl")
        self.memory = Memory(self.store)
        self.registry = ToolRegistry(self.store)
        self.meter = TokenMeter(model)
        self.compactor = Compactor(client, model, effort, compact_threshold)
        self.system = context.system_blocks()
        log(f"agent ready (model={model}, effort={effort}, {len(self.history.messages)} messages loaded)")

    def ask(self, user_text: str) -> dict:
        start, mark = time.perf_counter(), self.meter.mark()
        self.compactor.maybe_compact(self.history, self.meter)
        self.history.append(context.user_turn(user_text, self.store, self.memory))
        reply, tools_called = run_loop(self.client, self.model, self.effort, self.system,
                                       self.registry, self.history, self.meter)
        usage = self.meter.since(mark)
        return {"reply": reply, "tools_called": tools_called, **usage,
                "seconds": round(time.perf_counter() - start, 2)}
