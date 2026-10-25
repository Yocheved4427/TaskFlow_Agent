"""Offline stand-in for claude_agent_sdk.ClaudeSDKClient.

It plays the same script as tests/fakes.py, but runs each tool through the
real @tool handlers built by SDK/tools.py, and emits the SDK's own message
types (AssistantMessage, ResultMessage), so SDK/agent.py is tested as is.
"""
from __future__ import annotations

import itertools
import re
import uuid

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

import tools as sdk_tools  # SDK/tools.py (SDK/ is on sys.path)
from shared.store import TaskStore
from tests.fakes import script_for


class FakeSDKClient:
    # session_id -> cumulative cost. Like the real CLI, total_cost_usd keeps
    # growing over a session, also after it is resumed by a new client.
    sessions: dict[str, float] = {}

    def __init__(self, options):
        self.options = options
        self.session_id = options.resume or str(uuid.uuid4())
        self.ids = itertools.count(1)
        self._prompt = ""
        self.handlers = {}

    def _bind(self, prompt: str) -> None:
        # The real CLI reaches the @tool handlers through the in-process MCP
        # server. The fake rebuilds the same handlers with SDK/tools.py on the
        # same state dir (options.cwd) and calls them directly.
        today = re.search(r"\[today: (\d{4}-\d{2}-\d{2})", prompt).group(1)
        store = TaskStore(self.options.cwd, today)
        self.handlers = {t.name: t.handler for t in sdk_tools.build_tools(store)}

    async def connect(self):
        FakeSDKClient.sessions.setdefault(self.session_id, 0.0)

    async def disconnect(self):
        pass

    async def query(self, prompt: str):
        self._prompt = prompt
        self._bind(prompt)

    async def receive_response(self):
        steps = script_for(self._prompt)
        calls = 0
        for item in steps:
            calls += 1
            mid = f"msg_{next(self.ids)}"
            if isinstance(item, str):
                yield AssistantMessage(content=[TextBlock(text=item)], model="fake", message_id=mid)
                reply = item
                break
            blocks = [ToolUseBlock(id=f"toolu_{next(self.ids)}", name=f"mcp__taskflow__{n}", input=a) for n, a in item]
            yield AssistantMessage(content=blocks, model="fake", message_id=mid)
            for name, args in item:
                await self.handlers[name](args)
        FakeSDKClient.sessions[self.session_id] = round(FakeSDKClient.sessions[self.session_id] + 0.001 * calls, 6)
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                            num_turns=calls, session_id=self.session_id, total_cost_usd=FakeSDKClient.sessions[self.session_id],
                            usage={"input_tokens": 10 * calls, "cache_read_input_tokens": 100 * calls,
                                   "cache_creation_input_tokens": 20, "output_tokens": 30 * calls},
                            result=reply)
