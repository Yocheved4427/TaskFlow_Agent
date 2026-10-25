"""Conversation history, persisted append-only as JSONL.

Each line is either {"type": "message", ...} or {"type": "compaction", ...}.
Nothing is ever rewritten: compaction appends a summary record, and loading
replays the file, starting over from the latest summary.
"""
from __future__ import annotations

import json
from pathlib import Path

from harness import logger

log = logger(__file__)


class History:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.messages: list[dict] = []
        self.compactions = 0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            log(f"new conversation at {self.path.name}")
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if rec["type"] == "compaction":
                self.messages = self._summary_messages(rec["summary"])
                self.compactions += 1
            else:
                self.messages.append(rec["message"])
        log(f"loaded {len(self.messages)} messages from disk ({self.compactions} compactions)")

    @staticmethod
    def _summary_messages(summary: str) -> list[dict]:
        return [
            {"role": "user", "content": [{"type": "text", "text": f"<conversation_summary>\n{summary}\n</conversation_summary>"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "Understood, I have the summary of our earlier conversation."}]},
        ]

    def _write(self, rec: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def append(self, message: dict) -> None:
        self.messages.append(message)
        self._write({"type": "message", "message": message})

    def append_compaction(self, summary: str, replaced: int) -> None:
        self._write({"type": "compaction", "summary": summary, "replaced_messages": replaced})
        self.messages = self._summary_messages(summary)
        self.compactions += 1
        log(f"appended compaction record (replaced {replaced} messages)")
