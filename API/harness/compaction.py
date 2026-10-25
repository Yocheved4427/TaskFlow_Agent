"""Context-window management: past a token threshold, summarize the whole
conversation into one summary record and continue from it."""
from __future__ import annotations

from harness import logger
from harness.history import History
from harness.tokens import TokenMeter

log = logger(__file__)

SUMMARY_PROMPT = """Summarize this conversation between a user and their task-manager
assistant so the assistant can continue without it. Keep: tasks and due dates
mentioned, scheduling rules and preferences, refused requests, open
questions. Under 250 words. Facts only."""


def _render(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        for b in m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]:
            if b["type"] == "text":
                lines.append(f"{m['role']}: {b['text']}")
            elif b["type"] == "tool_use":
                lines.append(f"assistant called {b['name']}({b['input']})")
            elif b["type"] == "tool_result":
                lines.append(f"tool result: {str(b['content'])[:300]}")
    return "\n".join(lines)


class Compactor:
    def __init__(self, client, model: str, effort: str, threshold: int):
        self.client, self.model, self.effort, self.threshold = client, model, effort, threshold

    def maybe_compact(self, history: History, meter: TokenMeter) -> bool:
        size = meter.last_prompt_tokens
        if size < self.threshold or len(history.messages) < 4:
            log(f"no compaction ({size} < {self.threshold} tokens)")
            return False
        log(f"context {size} >= {self.threshold} tokens: summarizing {len(history.messages)} messages")
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            output_config={"effort": "low"},
            system=SUMMARY_PROMPT,
            messages=[{"role": "user", "content": _render(history.messages)}],
        )
        meter.record(resp.usage, purpose="compaction")
        summary = "".join(b.text for b in resp.content if b.type == "text")
        history.append_compaction(summary, replaced=len(history.messages))
        return True
