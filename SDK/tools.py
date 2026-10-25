"""SDK version of the tools: the shared domain functions wrapped with @tool and
served in-process by create_sdk_mcp_server."""
from __future__ import annotations

from claude_agent_sdk import create_sdk_mcp_server, tool

from shared.store import TaskStore
from shared.tools import TOOL_SPECS, ToolError, call_tool, compact

SERVER_NAME = "taskflow"


def _make_handler(store: TaskStore, name: str):
    async def handler(args: dict) -> dict:
        try:  # replaces: tools
            text = compact(call_tool(store, name, dict(args)))  # replaces: tools
            print(f"[SDK/tools.py] {name}({compact(dict(args))}) -> {text[:160]}", flush=True)
            return {"content": [{"type": "text", "text": text}]}  # replaces: tools
        except ToolError as exc:  # replaces: tools
            print(f"[SDK/tools.py] {name} -> ERROR {exc}", flush=True)
            return {"content": [{"type": "text", "text": f"error: {exc}"}], "is_error": True}  # replaces: tools
    return handler


def build_tools(store: TaskStore) -> list:
    return [tool(s["name"], s["description"], s["input_schema"])(_make_handler(store, s["name"]))  # replaces: tools
            for s in TOOL_SPECS]


def build_server(sdk_tools: list):
    return create_sdk_mcp_server(name=SERVER_NAME, version="1.0.0", tools=sdk_tools)  # replaces: tools


def allowed_names() -> list[str]:
    return [f"mcp__{SERVER_NAME}__{s['name']}" for s in TOOL_SPECS]  # replaces: tools
