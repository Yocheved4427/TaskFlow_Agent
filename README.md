# TaskFlow Agent: one agent, two harnesses

A personal task-manager agent built **twice** with the same model, tools and system prompt, once on the raw Anthropic API and once on the Claude Agent SDK, to measure what each approach costs and what it takes away from the developer.

Both versions passed all 7 scenario checks. On the measured run the API version cost **$0.10** against **$0.15** for the SDK version (31% cheaper) and ran about 45% faster. The API harness is 283 lines; the SDK equivalent is 32.

The full write-up, with per-turn tables and an explanation of where the tokens went, is in [REPORT.md](REPORT.md).

## What the agent does

TaskFlow manages tasks (due date, category, priority) and remembers standing scheduling rules such as "nothing on Saturday" or "no work on Friday". Before it sets a deadline it checks Israeli holidays.

| Part | How it works |
|---|---|
| **Tools (6)** | `add_task`, `list_tasks`, `complete_task`, `remember`, `recall`, `check_holidays` (date.nager.at API, cached on disk, with an offline fallback file) |
| **Memory** | Rules and notes persisted to disk; `add_task` itself rejects a task that breaks a rule, so the guarantee does not depend on the model |
| **Context engineering** | The API version builds a short `<context>` block per turn (date, rules, relevant notes, upcoming deadlines) instead of sending everything |
| **Token optimization** | Compact tool output, only the needed fields from the holiday API, per-call token and cost measurement |
| **Prompt caching** | About 86% cache hit rate in the API version |

## Measured results

Same model, same effort, same scenario (six turns across two sessions, fixed date), state cleared before each run.

| | API | SDK |
|---|---:|---:|
| Checks passed | 7/7 | 7/7 |
| Cost (USD) | **0.1031** | 0.1504 |
| Time (s) | **44.4** | 64.2 |
| Cache hit | 86.3% | 87.8% |
| Harness lines of code | 283 | **32** |

These come from a single run of each version, on one machine. Treat them as a measured example, not a statistical benchmark. The report lists the caveats, including that the holiday lookup used the offline fallback file in both runs.

## Project structure

```
API/        raw-API version: loop, tools, history, memory, context, compaction, caching, token accounting
SDK/        Claude Agent SDK version
shared/     domain code used by both: tools, store, prompts, checks, metrics, report tables
tests/      29 offline tests (no API key needed)
results/    api.json, sdk.json (real runs); results/mock/ holds scripted-client runs, not measurements
scenario.json   the six-turn scenario
REPORT.md   the full comparison
```

## Run it

```bash
pip install -r requirements.txt
python -m pytest -q tests                      # offline, no key needed

# API version (key only as an environment variable)
export ANTHROPIC_API_KEY=...                   # PowerShell: $env:ANTHROPIC_API_KEY="..."
python API/main.py --scenario scenario.json --out results/api.json

# SDK version (uses a Claude Code login, no key)
python SDK/main.py --scenario scenario.json --out results/sdk.json

python -m shared.report_table                  # regenerate the tables
```

## Tech

Python, Anthropic API, Claude Agent SDK, pytest.
