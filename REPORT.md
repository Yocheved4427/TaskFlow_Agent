# TaskFlow: one agent, two harnesses

> **Measurement status:** Both versions were run live on the full scenario on the same computer, and both passed 7/7 checks. The tables come from `python -m shared.report_table` over `results/api.json` and `results/sdk.json`. Numbers tagged "estimate" were not measured.

## 1. The agent

**TaskFlow** is a personal task manager: tasks with a due date, category and priority, standing scheduling rules ("nothing on Saturday", "no work on Friday"), and a holiday check before setting deadlines. All the domain code is in `shared/`, and both versions use it.

| Topic | How it is implemented |
|---|---|
| **Tools** | 6 tools in `shared/tools.py`: `add_task`, `list_tasks`, `complete_task`, `remember`, `recall`, `check_holidays`. The external tool is `check_holidays`, which calls the date.nager.at API. The response is cached on disk, and if there is no network it falls back to a backup file (`shared/data/`). |
| **Memory** | `state/memory.json`: day-of-week rules (structured: day + category) and free-form notes (preferences, decisions). `add_task` enforces the rules itself and returns an error for a task that contradicts a rule. That way the contradiction is blocked even if the model misses it. |
| **Context engineering** | In the API version, `context.py` attaches a short `<context>` block to every turn: the date, the rules (always, because they are short and `add_task` depends on them), only the notes that share words with the message, and one line about upcoming deadlines. The full task list and the holidays are not sent; the model fetches them with tools. In the SDK version the model fetches everything itself, following the instruction in `CLAUDE.md`. |
| **Token optimization** | The tools return JSON without whitespace and compact rows (`T1|Quarterly report|2027-04-13|work|high|open`) instead of full records. From the holiday API only the date and name are kept (it has about 10 fields per holiday). `tokens.py` measures every call and every turn. |

## 2. The scenario and the checks

`scenario.json`: six turns in two sessions, with the date fixed to 11.4.2027 so the results are deterministic.

- **Session 1:** saving two rules and a preference (t1), adding 3 tasks (t2), marking a task as done and checking April holidays, which is the external tool (t3).
- **Session 2** (a new instance that loads from disk and continues the conversation): recalling the rules and tasks (t4), a request that contradicts the rules, i.e. a work task on Saturday and on Friday (t5), and a request that needs both memory and holidays: "the first day from 22.4 that is allowed and is not a holiday". 22.4 is Passover, 23.4 is Friday and 24.4 is Saturday, so the correct answer is 25.4 (t6).

7 checks (`shared/checks.py`). 6 of them check the state on disk:

| Check | What is checked | Type |
|---|---|---|
| `tasks_saved` | The 4 correct tasks were saved with the correct date and category | state |
| `task_completed` | The presentation draft is marked `done` | state |
| `rules_persisted` | Both rules are saved in `memory.json` | state |
| `contradiction_blocked` | No task at all on Saturday, on Friday (work) or on 22.4 | state |
| `external_tool_used` | `check_holidays` was called and there is a holiday cache on disk | state + run |
| `holiday_aware_date` | The server migration was saved for 25.4 | state |
| `session2_recall` | The t4 reply mentions both Saturday and Friday | text |

## 3. API vs. SDK

Same model (`claude-opus-5-5`), same effort (`medium`), same system prompt (`shared/prompts.py`), same tools and schemas, and pinned library versions (`requirements.txt`). Every run deletes the state folder before it starts.

| Metric | API | SDK |
|---|---:|---:|
| input (uncached) | 36 | 24 |
| cache read | 39,262 | 56,590 |
| cache write | 6,181 | 7,833 |
| output | 3,209 | 3,816 |
| cache hit % | 86.3% | 87.8% |
| model calls | 12 | 12 |
| cost (USD) | **$0.1031** | $0.1504 |
| time (seconds) | 44.4 | 64.2 |
| checks passed | **7/7** | **7/7** |

Per turn (in / cache read / cache write / out):

| Turn | API | API $ | API tools | SDK | SDK $ | SDK tools |
|---|---|---:|---|---|---:|---|
| t1 | 6 / 1,644 / 2,113 / 470 | 0.0203 | remember ×3 | 4 / 2,674 / 3,325 / 743 | 0.0420 | recall, remember ×3 |
| t2 | 8 / 7,156 / 1,075 / 771 | 0.0223 | check_holidays, add_task ×3 | 6 / 11,371 / 1,599 / 1,047 | 0.0360 | recall, check_holidays, add_task ×3 |
| t3 | 6 / 6,769 / 764 / 517 | 0.0155 | complete_task, check_holidays | 4 / 10,256 / 763 / 539 | 0.0190 | complete_task, check_holidays |
| t4 | 6 / 8,325 / 685 / 290 | 0.0109 | recall, list_tasks | 4 / 11,799 / 751 / 336 | 0.0151 | recall, list_tasks |
| t5 | 4 / 4,637 / 370 / 539 | 0.0136 | none (refused from the rules in `<context>`) | 2 / 6,438 / 324 / 426 | 0.0124 | none (refused from the rules it had already recalled) |
| t6 | 6 / 10,731 / 1,174 / 622 | 0.0205 | add_task ×2 | 4 / 14,052 / 1,071 / 725 | 0.0259 | add_task ×2 |

Overall the SDK cost 46% more than the API ($0.1504 vs $0.1031), read 42% more input tokens (64,447 vs 45,479 including cache) and took 45% longer, for the same number of model calls and the same 7/7 result. In both versions t5 refused the contradicting tasks without even calling `add_task`.

## 4. Lines of code per harness part

Counted automatically (`shared/metrics.py`): non-empty lines that are not comments. In the SDK, the lines tagged `# replaces: <part>` are counted.

| Part | API (file) | API lines | SDK (what replaces it) | SDK lines |
|---|---|---:|---|---:|
| loop | `harness/loop.py` | 45 | `client.query()` + `receive_response()`, `max_turns` | 3 |
| tools | `harness/tools.py` | 26 | `@tool` + `create_sdk_mcp_server`, `tools=[]`, `allowed_tools`, `strict_mcp_config=True` | 12 |
| history | `harness/history.py` | 46 | `resume=session_id` (the id is saved to a file) | 4 |
| memory | `harness/memory.py` | 26 | `CLAUDE.md` + `setting_sources=["project"]` + `cwd` | 3 |
| context | `harness/context.py` | 35 | `system_prompt` + date in the message | 2 |
| compaction | `harness/compaction.py` | 42 | automatic | 0 |
| caching | `harness/caching.py` | 23 | automatic | 0 |
| tokens | `harness/tokens.py` | 40 | `ResultMessage.usage`, `total_cost_usd` | 8 |
| **Total harness** | | **283** | | **32** |

In addition, `API/agent.py` and `API/main.py` are 92 lines. All the SDK code (agent, tools, main) is 164 lines.

## 5. Where the SDK used more tokens and where fewer, and why

**More:**
- **Large fixed prefix.** In t1 both versions made 2 calls. The SDK sent about 6,000 input tokens (roughly 3,000 per call), the API about 3,760 (roughly 1,900 per call). Our system prompt and the 6 tool schemas are about 3,250 characters, roughly 1,000 tokens (estimate). In the SDK, Claude Code adds the rest itself: internal instructions, the MCP wrapping of the tools, and the contents of `CLAUDE.md`. The full request cannot be seen, so this is inferred from the numbers.
- **Extra tool calls.** Because of the instruction in `CLAUDE.md` ("recall rules before adding"), the SDK called `recall` in 3 of the 6 turns. Each such call is another round trip to the model, another message in the history and more output tokens. In the API version the rules already arrive in the `<context>` block, and `recall` was called only once (t4, where the user asked for it). The model-call count came out equal (12 and 12) because the SDK batched `recall` together with the other tools in the same call, but every turn's history in the SDK still carries the extra tool calls and results.
- **More expensive cache writes.** The cost the SDK reported matches cache writes priced at twice the input price ($8 per million, 1-hour TTL), and not 1.25× ($5, 5-minute TTL) as in the API version. I checked this against each turn's `usage`. Cache writes alone cost the SDK about $0.063 (7,833 tokens) versus about $0.031 in the API (6,181 tokens), which is most of the cost gap.
- **Longer replies.** About 640 output tokens per turn in the SDK versus about 535 in the API (tables, explanations). Most of this is the model, but the SDK's extra tool calls also add output tokens.

**Fewer:**
- **Slightly higher cache hit rate (87.8% vs 86.3%).** Most of the input was read from the cache at $0.20 per million instead of $4. Claude Code's prefix is stable, so from the second call on almost all the input is a cache read. Only t1 paid to write the prefix (3,325 tokens written, 2,674 read), which makes it the most expensive turn. In an earlier run started less than an hour after another one, t1 read 11,830 tokens from the cache instead: "clean state" clears the disk, but not the server-side cache.
- **My hypothesis about the API prefix was wrong.** I expected our small prefix (about 1,000 tokens) to be below the minimum that gets cached, so the first API calls would pay full price. In fact the API version already read 1,644 tokens from the cache in t1: once the first call's request (prefix plus tool results) was written, the second call read it. A larger prefix only helps the SDK's hit rate a little, and it costs more in absolute tokens.

## 6. What I controlled in the API version and lost in the SDK

- **What the model sees each turn.** In the API version I decide exactly what goes in (`context.py`) and see the full request. In the SDK, Claude Code adds content I cannot see, and memory depends on the model choosing to call `recall`.
- **Caching.** In the API version I choose where to put the `cache_control` breakpoints and which TTL. In the SDK it is automatic, including a 1-hour TTL at double the write price.
- **Compaction.** In the API version I set the threshold, the summary instruction and what is kept. The summary is written as an extra record in an append-only file, so it can be inspected. In the SDK it is automatic, and I have no control over its content.
- **History.** In the API version it is my own JSONL file. In the SDK it is saved in Claude Code's format in Claude Code's folder, and I only keep the `session_id`.
- **The loop.** In the API version I see every iteration: `stop_reason`, handling of `refusal` and `max_tokens`, and an iteration limit. In the SDK I get finished messages, and intervening mid-turn requires hooks.
- **Measurement.** In the API version `tokens.py` computes the cost of every call. In the SDK the `total_cost_usd` value accumulates over the whole session, even after resume, so I had to compute the difference between turns to get a per-turn cost. The measurement is also less detailed, since there is no per-call breakdown.

## 7. Which version I would choose

**For this agent, for my own personal use: SDK.** It passed all the checks (7/7, $0.15 for the whole scenario) with 32 harness lines instead of 283. It runs on my login without a key, and compaction and caching work without me writing them. The tools are the same code in both versions, so I did not give up the important logic. The "no tasks on Saturday" rule is enforced inside `add_task` and does not depend on the harness.

**If the agent served other users** I would choose the API. There, what matters is control over the cost of every request, a small prefix, choosing what goes into the context, and a history in my own format that can be inspected. The measurement supports this: for the same result, the API version was 31% cheaper per scenario ($0.10 vs $0.15) and faster, and at many users that difference matters more than 250 lines of harness code.

## 8. Notes on the measurement environment

- In both runs `check_holidays` used the backup file (`"source": "fallback-file"`), meaning the request to date.nager.at failed from my computer. Both versions ran under the same conditions, on the same computer with the same tool code.
- The backup file contains Israel's 2027 holidays according to the Hebrew calendar (Passover 22.4, Seventh day of Passover 28.4, and more). They should be verified against the real API.
- `results/mock/` contains runs against a mock client. They show the structure of the results file, and the numbers in them are not measurements.

## How to run

```bash
pip install -r requirements.txt
python -m pytest -q tests                       # offline, no key (29 tests)

# API: the key only as an environment variable in the terminal
export ANTHROPIC_API_KEY=...                     # Windows PowerShell: $env:ANTHROPIC_API_KEY="..."
python API/main.py --scenario scenario.json --out results/api.json

# SDK: on the Claude Code login, no key
unset ANTHROPIC_API_KEY                          # PowerShell: Remove-Item Env:ANTHROPIC_API_KEY
python SDK/main.py --scenario scenario.json --out results/sdk.json

python -m shared.report_table                    # tables for REPORT.md
```
