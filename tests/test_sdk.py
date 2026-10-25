"""SDK configuration and wrappers, with a fake SDK client (no login needed)."""
import asyncio
import importlib.util
import re
from pathlib import Path

import tools as sdk_tools  # SDK/tools.py
from shared.prompts import SYSTEM_PROMPT
from shared.store import TaskStore
from tests.conftest import ROOT, TODAY
from tests.fakes_sdk import FakeSDKClient

spec = importlib.util.spec_from_file_location("sdk_agent", ROOT / "SDK" / "agent.py")
sdk_agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdk_agent)


def test_options(tmp_path):
    a = sdk_agent.SDKTaskFlow(tmp_path, TODAY, client_cls=FakeSDKClient)
    o = a.options
    assert o.system_prompt == SYSTEM_PROMPT
    assert o.strict_mcp_config is True
    assert o.tools == []
    assert o.allowed_tools == [f"mcp__taskflow__{n}" for n in
                               ("add_task", "list_tasks", "complete_task", "remember", "recall", "check_holidays")]
    assert o.setting_sources == ["project"] and (tmp_path / "CLAUDE.md").exists()
    assert o.model == "claude-opus-5-5" and o.effort == "medium"
    assert o.resume is None


def test_handler_wraps_result_and_errors(tmp_path):
    store = TaskStore(tmp_path, TODAY)
    handlers = {t.name: t.handler for t in sdk_tools.build_tools(store)}
    ok = asyncio.run(handlers["add_task"]({"title": "A", "due": "2027-04-13", "category": "work"}))
    assert ok == {"content": [{"type": "text", "text": '{"id":"T1","updated":false,"weekday":"tuesday"}'}]}
    bad = asyncio.run(handlers["complete_task"]({"task_id": "T9"}))
    assert bad["is_error"] is True and "no task" in bad["content"][0]["text"]


def test_second_instance_resumes_and_costs_are_per_turn(tmp_path):
    async def run():
        a = sdk_agent.SDKTaskFlow(tmp_path, TODAY, client_cls=FakeSDKClient)
        await a.connect()
        t1 = await a.ask("Hi! Remember my rules")
        t2 = await a.ask("Please add three tasks")
        await a.close()
        b = sdk_agent.SDKTaskFlow(tmp_path, TODAY, client_cls=FakeSDKClient)
        return a, b, t1, t2

    a, b, t1, t2 = asyncio.run(run())
    assert b.options.resume == t1["session_id"]
    assert t1["tools_called"] == ["remember", "remember", "remember"]
    assert t2["cost_usd"] == 0.002  # fake reports 0.001 per call; the turn has 2 calls
    assert len(TaskStore(tmp_path, TODAY).memory()["rules"]) == 2


def test_replaces_tags_cover_the_harness():
    text = "".join((ROOT / "SDK" / f).read_text() for f in ("agent.py", "tools.py"))
    tagged = {p.strip() for m in re.findall(r"#\s*replaces:\s*([\w, ]+)", text) for p in m.split(",")}
    assert {"loop", "tools", "history", "memory", "context", "tokens"} <= tagged
