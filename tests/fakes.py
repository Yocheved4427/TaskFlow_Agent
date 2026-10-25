"""Offline stand-ins for the model. No key, no network.

ScriptedAnthropic mimics `anthropic.Anthropic().messages.create` and plays a
fixed script per scenario turn: which tools to call, then a final reply.
The script is recognised from keywords in the latest user text, and the step
from how many assistant messages already followed it.
"""
from __future__ import annotations

import json
import itertools

from anthropic.types import Message

SCRIPT = [
    ("Remember my rules", [
        [("remember", {"kind": "rule", "text": "No tasks at all on Saturday (Shabbat)", "weekday": "saturday", "applies_to": "all"}),
         ("remember", {"kind": "rule", "text": "No work tasks on Friday", "weekday": "friday", "applies_to": "work"}),
         ("remember", {"kind": "preference", "text": "High priority tasks early in the week"})],
        "Saved: no tasks on Saturday, no work on Friday, and high priority early in the week.",
    ]),
    ("three tasks", [
        [("add_task", {"title": "Quarterly report", "due": "2027-04-13", "category": "work", "priority": "high"}),
         ("add_task", {"title": "Buy a gift for Mom", "due": "2027-04-15", "category": "personal", "priority": "medium"}),
         ("add_task", {"title": "Team presentation draft", "due": "2027-04-14", "category": "work", "priority": "medium"})],
        "Added three tasks.",
    ]),
    ("I finished the presentation", [
        [("complete_task", {"task_id": "T3"}), ("check_holidays", {"year": 2027, "country": "IL", "month": 4})],
        "Marked as done. In April: Passover on 22.4 and the Seventh day of Passover on 28.4.",
    ]),
    ("Which rules", [
        [("recall", {"query": ""}), ("list_tasks", {})],
        "Your rules: no tasks on Saturday, no work on Friday. Open: Quarterly report, Buy a gift for Mom.",
    ]),
    ("Budget meeting with client", [
        [("add_task", {"title": "Budget meeting with client", "due": "2027-04-17", "category": "work", "priority": "high"}),
         ("add_task", {"title": "Server migration", "due": "2027-04-16", "category": "work", "priority": "high"})],
        "Not added: 17.4 is a Saturday and 16.4 is a Friday, both break your rules. Maybe 18.4?",
    ]),
    ("You're right", [
        [("check_holidays", {"year": 2027, "country": "IL", "month": 4})],
        [("add_task", {"title": "Budget meeting with client", "due": "2027-04-18", "category": "work", "priority": "high"}),
         ("add_task", {"title": "Server migration", "due": "2027-04-25", "category": "work", "priority": "high"})],
        "Scheduled: budget meeting on 18.4, server migration on 25.4 (22.4 is a holiday, 23.4 Friday, 24.4 Saturday).",
    ]),
]


def script_for(user_text: str):
    for key, steps in SCRIPT:
        if key in user_text:
            return steps
    return ["(no script)"]


def _text_of(msg: dict) -> str:
    content = msg["content"]
    if isinstance(content, str):
        return content
    return " ".join(b.get("text", "") for b in content if b.get("type") == "text")


class _Messages:
    def __init__(self, owner):
        self.owner = owner

    def create(self, **kw):
        self.owner.requests.append(kw)
        msgs = kw["messages"]
        if isinstance(kw.get("system"), str):  # compaction summary request
            return self.owner.message([{"type": "text", "text": "Summary: tasks and preferences so far."}], "end_turn", kw)
        # latest real user turn = last user message that has text (not only tool results)
        idx = max(i for i, m in enumerate(msgs) if m["role"] == "user" and _text_of(m).strip())
        step = sum(1 for m in msgs[idx + 1:] if m["role"] == "assistant")
        steps = script_for(_text_of(msgs[idx]))
        item = steps[min(step, len(steps) - 1)]
        if isinstance(item, str):
            return self.owner.message([{"type": "text", "text": item}], "end_turn", kw)
        blocks = [{"type": "tool_use", "id": f"toolu_{next(self.owner.ids)}", "name": n, "input": a} for n, a in item]
        return self.owner.message(blocks, "tool_use", kw)


class ScriptedAnthropic:
    def __init__(self):
        self.requests: list[dict] = []
        self.ids = itertools.count(1)
        self.messages = _Messages(self)
        self._prev_prompt = 0

    def message(self, content, stop_reason, kw) -> Message:
        prompt = len(json.dumps(kw, ensure_ascii=False, default=str)) // 4
        cached = min(self._prev_prompt, prompt)  # pretend the previous prefix was cached
        self._prev_prompt = prompt
        return Message.model_validate({
            "id": f"msg_{next(self.ids)}", "type": "message", "role": "assistant", "model": kw["model"],
            "content": content, "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": prompt - cached, "output_tokens": 40,
                      "cache_read_input_tokens": cached, "cache_creation_input_tokens": prompt - cached},
        })
