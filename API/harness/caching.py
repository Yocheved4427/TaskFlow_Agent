"""Prompt caching breakpoints (cache_control).

Render order is tools -> system -> messages, so:
  1. last system block   -> caches tools + system (identical on every call)
  2. last message block  -> rolling breakpoint, caches the whole history so the
                            next call (next tool iteration or next turn) reads it.
The history stored on disk is never modified: breakpoints go on a copy.
"""
from __future__ import annotations

import copy

from harness import logger

log = logger(__file__)
EPHEMERAL = {"type": "ephemeral"}


def apply(system: list[dict], messages: list[dict]) -> tuple[list[dict], list[dict]]:
    system = copy.deepcopy(system)
    system[-1]["cache_control"] = EPHEMERAL
    messages = copy.deepcopy(messages)
    if messages:
        last = messages[-1]
        if isinstance(last["content"], str):
            last["content"] = [{"type": "text", "text": last["content"]}]
        last["content"][-1]["cache_control"] = EPHEMERAL
    log(f"2 breakpoints: system, message #{len(messages)}")
    return system, messages
