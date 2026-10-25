"""The API harness against a scripted fake client: no key, no network."""
import json

from anthropic.types import Message

from agent import TaskFlowAgent
from harness import caching, context
from harness.history import History
from harness.memory import Memory
from harness.tokens import cost
from tests.conftest import TODAY
from tests.fakes import ScriptedAnthropic

RULES = "Hi! Remember my rules: nothing on Saturday, and no work on Friday."
TASKS = "Please add three tasks"


def make_agent(tmp_path, client=None, **kw):
    return TaskFlowAgent(client or ScriptedAnthropic(), tmp_path / "s", TODAY, **kw)


def test_parallel_tool_results_go_back_in_one_message(tmp_path):
    client = ScriptedAnthropic()
    agent = make_agent(tmp_path, client)
    out = agent.ask(RULES)
    assert out["tools_called"] == ["remember", "remember", "remember"]
    assert out["model_calls"] == 2
    second = client.requests[1]["messages"]
    results = second[-1]["content"]
    assert second[-1]["role"] == "user"
    assert [b["type"] for b in results] == ["tool_result"] * 3
    assert {b["tool_use_id"] for b in results} == {b["id"] for b in second[-2]["content"] if b["type"] == "tool_use"}


def test_tool_error_returns_is_error(tmp_path):
    agent = make_agent(tmp_path)
    agent.ask(RULES)
    agent.ask("Add 'Budget meeting with client' (work) on 17.4.2027, and 'Server migration' on 16.4.2027.")
    errors = [b for m in agent.history.messages if m["role"] == "user" and isinstance(m["content"], list)
              for b in m["content"] if b.get("is_error")]
    assert len(errors) == 2 and all("refused" in b["content"] for b in errors)
    assert agent.store.tasks() == []


def test_history_is_append_only_and_reloaded(tmp_path):
    agent = make_agent(tmp_path)
    agent.ask(RULES)
    path = tmp_path / "s" / "history.jsonl"
    first = path.read_text(encoding="utf-8")
    agent.ask(TASKS)
    assert path.read_text(encoding="utf-8").startswith(first)  # nothing rewritten
    again = make_agent(tmp_path)  # new instance = new session
    assert again.history.messages == agent.history.messages


def test_cache_breakpoints_on_copy_only(tmp_path):
    client = ScriptedAnthropic()
    agent = make_agent(tmp_path, client)
    agent.ask(RULES)
    req = client.requests[-1]
    assert req["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert req["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in (tmp_path / "s" / "history.jsonl").read_text()
    sys_blocks, msgs = caching.apply(context.system_blocks(), [{"role": "user", "content": "hi"}])
    assert msgs[0]["content"][0]["cache_control"]


def test_request_uses_model_and_effort(tmp_path):
    client = ScriptedAnthropic()
    make_agent(tmp_path, client).ask(RULES)
    req = client.requests[0]
    assert req["model"] == "claude-opus-5-5" and req["output_config"] == {"effort": "medium"}
    assert [t["name"] for t in req["tools"]] == ["add_task", "list_tasks", "complete_task", "remember",
                                                 "recall", "check_holidays"]


def test_compaction_past_threshold(tmp_path):
    client = ScriptedAnthropic()
    agent = make_agent(tmp_path, client, compact_threshold=100)
    agent.ask(RULES)
    agent.ask(TASKS)  # last request was > 100 tokens -> summarize first
    lines = [json.loads(l) for l in (tmp_path / "s" / "history.jsonl").read_text().splitlines()]
    assert any(r["type"] == "compaction" for r in lines)
    assert any(c["purpose"] == "compaction" for c in agent.meter.calls)
    reloaded = History(tmp_path / "s" / "history.jsonl")
    assert "<conversation_summary>" in reloaded.messages[0]["content"][0]["text"]
    assert reloaded.messages[0]["role"] == "user" and reloaded.messages[1]["role"] == "assistant"


def test_context_sends_rules_but_not_all_tasks(tmp_path, store):
    import shared.tools as t
    t.remember(store, "rule", "No Shabbat", weekday="saturday", applies_to="all")
    t.remember(store, "decision", "Reports go to Dana")
    for i in range(5):
        t.add_task(store, f"task {i}", "2027-04-13", "work")
    msg = context.user_turn("plan my week", store, Memory(store))
    ctx = msg["content"][0]["text"]
    assert "rule: no all tasks on saturday" in ctx
    assert "Dana" not in ctx and "(1 more notes; use recall)" in ctx  # unrelated note left out
    assert "task 3" not in ctx and "5 open" in ctx  # a one-line summary, not the list
    assert msg["content"][1]["text"] == "plan my week"


def test_token_cost_per_turn(tmp_path):
    out = make_agent(tmp_path).ask(RULES)
    for k in ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens", "cost_usd", "seconds"):
        assert k in out
    u = {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_read_tokens": 1_000_000,
         "cache_write_tokens": 1_000_000}
    assert cost("claude-opus-5-5", u) == 4 + 20 + 0.2 + 5


def test_every_action_is_logged_with_file_name(tmp_path, capsys):
    make_agent(tmp_path).ask(RULES)
    out = capsys.readouterr().out
    for f in ("loop.py", "tools.py", "history.py", "memory.py", "context.py", "compaction.py", "caching.py",
              "tokens.py", "agent.py"):
        assert f"[{f}]" in out, f


def test_loop_stops_on_end_turn_and_handles_refusal(tmp_path):
    class Refuser(ScriptedAnthropic):
        def __init__(self):
            super().__init__()
            self.messages.create = self._refuse

        def _refuse(self, **kw):
            self.requests.append(kw)
            return Message.model_validate({
                "id": "m", "type": "message", "role": "assistant", "model": kw["model"], "content": [],
                "stop_reason": "refusal", "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 0}})

    out = make_agent(tmp_path, Refuser()).ask("x")
    assert out["reply"] == "" and out["model_calls"] == 1
