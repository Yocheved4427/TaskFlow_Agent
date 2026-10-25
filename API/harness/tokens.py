"""Token usage and cost per model call and per user turn."""
from __future__ import annotations

from harness import logger

log = logger(__file__)

# USD per million tokens. Cache writes (5 minute TTL) cost 1.25x input.
PRICES = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 5.00},
}


def cost(model: str, u: dict) -> float:
    p = PRICES[model]
    return (u["input_tokens"] * p["input"] + u["output_tokens"] * p["output"]
            + u["cache_read_tokens"] * p["cache_read"] + u["cache_write_tokens"] * p["cache_write"]) / 1e6


class TokenMeter:
    def __init__(self, model: str):
        self.model = model
        self.calls: list[dict] = []
        self.last_prompt_tokens = 0  # size of the last request; drives compaction

    def record(self, usage, purpose: str = "turn") -> dict:
        u = {
            "input_tokens": usage.input_tokens or 0,
            "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            "output_tokens": usage.output_tokens or 0,
            "purpose": purpose,
        }
        u["cost_usd"] = cost(self.model, u)
        self.calls.append(u)
        self.last_prompt_tokens = u["input_tokens"] + u["cache_read_tokens"] + u["cache_write_tokens"]
        log(f"{purpose} call: in={u['input_tokens']} cache_read={u['cache_read_tokens']} "
            f"cache_write={u['cache_write_tokens']} out={u['output_tokens']} ${u['cost_usd']:.4f}")
        return u

    def mark(self) -> int:
        return len(self.calls)

    def since(self, mark: int) -> dict:
        calls = self.calls[mark:]
        keys = ["input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens"]
        out = {k: sum(c[k] for c in calls) for k in keys}
        out["model_calls"] = len(calls)
        out["cost_usd"] = round(sum(c["cost_usd"] for c in calls), 6)
        log(f"turn total: {out['model_calls']} calls, ${out['cost_usd']:.4f}")
        return out
