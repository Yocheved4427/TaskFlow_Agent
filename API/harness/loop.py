"""The agent loop: call the model, run every requested tool, send all the
tool_result blocks back in ONE user message, repeat while stop_reason is tool_use."""
from __future__ import annotations

from harness import caching, logger

log = logger(__file__)
MAX_TOKENS = 16000
MAX_ITERATIONS = 15


def _dump(block) -> dict:
    # Keep every block as returned (thinking blocks included) so history can
    # be replayed unchanged.
    return block.model_dump(mode="json", exclude_none=True)


def run_loop(client, model: str, effort: str, system: list[dict], registry, history, meter) -> tuple[str, list[str]]:
    tools_called: list[str] = []

    def call():
        sys_blocks, messages = caching.apply(system, history.messages)
        log(f"model call #{meter.mark() + 1} ({len(messages)} messages)")
        resp = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            output_config={"effort": effort},
            system=sys_blocks,
            tools=registry.schemas(),
            messages=messages,
        )
        meter.record(resp.usage)
        history.append({"role": "assistant", "content": [_dump(b) for b in resp.content]})
        log(f"stop_reason={resp.stop_reason}")
        return resp

    resp = call()
    iterations = 1
    while resp.stop_reason == "tool_use":
        uses = [b for b in resp.content if b.type == "tool_use"]
        tools_called += [b.name for b in uses]
        results = [registry.run(b) for b in uses]
        history.append({"role": "user", "content": results})  # all results, one message
        log(f"returned {len(results)} tool_result block(s) in one message")
        if iterations >= MAX_ITERATIONS:
            log("iteration limit reached, stopping")
            break
        resp = call()
        iterations += 1

    if resp.stop_reason == "refusal":
        log("model refused this request")
    elif resp.stop_reason == "max_tokens":
        log("reply was cut at max_tokens")
    text = "".join(b.text for b in resp.content if b.type == "text")
    return text, tools_called
