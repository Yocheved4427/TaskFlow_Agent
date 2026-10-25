"""TaskFlow agent on the Claude Agent SDK. Claude Code runs the harness;
this file only configures it. Lines tagged '# replaces: <part>' stand in for
the matching file in API/harness/."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, ToolUseBlock

import tools as sdk_tools
from shared.prompts import SYSTEM_PROMPT
from shared.store import TaskStore

HERE = Path(__file__).resolve().parent


class SDKTaskFlow:
    def __init__(self, state_dir: str | Path, today: str, model: str = "claude-opus-5-5",
                 effort: str = "medium", client_cls=ClaudeSDKClient):
        self.state_dir = Path(state_dir)
        self.store = TaskStore(state_dir, today)
        self.session_file = self.state_dir / "sdk_session.json"
        saved = json.loads(self.session_file.read_text()) if self.session_file.exists() else {}  # replaces: history
        resume = saved.get("session_id")  # replaces: history
        # total_cost_usd is cumulative over the whole (resumed) session; keep
        # the last value to turn it into a per-turn cost.
        self.cost_so_far = saved.get("total_cost_usd", 0.0)  # replaces: tokens
        shutil.copy(HERE / "CLAUDE.md", self.state_dir / "CLAUDE.md")  # replaces: memory
        self.tools = sdk_tools.build_tools(self.store)
        self.options = ClaudeAgentOptions(
            model=model,
            effort=effort,
            system_prompt=SYSTEM_PROMPT,  # replaces: context
            tools=[],  # no built-in Claude Code tools  # replaces: tools
            mcp_servers={sdk_tools.SERVER_NAME: sdk_tools.build_server(self.tools)},  # replaces: tools
            allowed_tools=sdk_tools.allowed_names(),  # replaces: tools
            strict_mcp_config=True,  # replaces: tools
            setting_sources=["project"],  # loads CLAUDE.md from cwd  # replaces: memory
            cwd=str(self.state_dir),  # replaces: memory
            resume=resume,  # replaces: history
            max_turns=15,  # replaces: loop
        )
        self.client = client_cls(options=self.options)
        print(f"[SDK/agent.py] options built (model={model}, effort={effort}, resume={resume})", flush=True)

    async def connect(self) -> None:
        await self.client.connect()

    async def close(self) -> None:
        await self.client.disconnect()

    async def ask(self, user_text: str) -> dict:
        start = time.perf_counter()
        prompt = f"[today: {self.store.today.isoformat()} ({self.store.today.strftime('%A')})]\n{user_text}"  # replaces: context
        await self.client.query(prompt)  # replaces: loop
        tools_called, message_ids, reply, result = [], set(), "", None
        async for msg in self.client.receive_response():  # replaces: loop
            if isinstance(msg, AssistantMessage):
                message_ids.add(msg.message_id)
                tools_called += [b.name.split("__")[-1] for b in msg.content if isinstance(b, ToolUseBlock)]
            elif isinstance(msg, ResultMessage):
                result = msg
        reply = result.result or ""
        total = result.total_cost_usd or 0.0  # replaces: tokens
        self.session_file.write_text(json.dumps({"session_id": result.session_id, "total_cost_usd": total}))  # replaces: history
        u = result.usage or {}  # replaces: tokens
        turn = {
            "reply": reply,
            "tools_called": tools_called,
            "input_tokens": u.get("input_tokens", 0),  # replaces: tokens
            "cache_read_tokens": u.get("cache_read_input_tokens", 0),  # replaces: tokens
            "cache_write_tokens": u.get("cache_creation_input_tokens", 0),  # replaces: tokens
            "output_tokens": u.get("output_tokens", 0),  # replaces: tokens
            "model_calls": len(message_ids - {None}) or result.num_turns,
            "num_turns": result.num_turns,
            "cost_usd": round(total - self.cost_so_far, 6),  # replaces: tokens
            "total_cost_usd_reported": total,
            "seconds": round(time.perf_counter() - start, 2),
            "session_id": result.session_id,
        }
        self.cost_so_far = total
        print(f"[SDK/agent.py] turn: {turn['model_calls']} calls, in={turn['input_tokens']} "
              f"cache_read={turn['cache_read_tokens']} out={turn['output_tokens']} ${turn['cost_usd']:.4f}", flush=True)
        return turn
