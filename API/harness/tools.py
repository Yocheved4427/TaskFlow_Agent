"""Tool schemas for the API request, dispatch by name, and errors as is_error."""
from __future__ import annotations

from harness import logger
from shared.store import TaskStore
from shared.tools import TOOL_SPECS, ToolError, call_tool, compact

log = logger(__file__)


class ToolRegistry:
    def __init__(self, store: TaskStore):
        self.store = store

    def schemas(self) -> list[dict]:
        # Fixed order and content: the tool list is part of the cached prefix.
        return [dict(spec) for spec in TOOL_SPECS]

    def run(self, block) -> dict:
        """Execute one tool_use block and return its tool_result block."""
        args = dict(block.input or {})
        try:
            result = call_tool(self.store, block.name, args)
            text, is_error = compact(result), False
        except ToolError as exc:
            text, is_error = f"error: {exc}", True
        except Exception as exc:  # a bug in a tool must not kill the loop
            text, is_error = f"error: internal {exc.__class__.__name__}: {exc}", True
        log(f"{block.name}({compact(args)}) -> {'ERROR ' if is_error else ''}{text[:160]}")
        out = {"type": "tool_result", "tool_use_id": block.id, "content": text}
        if is_error:
            out["is_error"] = True
        return out
