"""Turn raw stream captures into small, scrubbed adapter fixtures.

    uv run python spikes/make_fixtures.py

Keeps the event shapes and order. Removes opaque reasoning blobs and request echoes, renumbers
ids, shortens excerpts, and keeps only the first few text deltas.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CAPTURES = Path(__file__).parent / "captures"
FIXTURES = Path(__file__).parent.parent / "tests" / "adapter" / "fixtures"
EXCERPT = 700
KEEP_DELTAS = 3
DROP = {"instructions", "input", "metadata", "prompt_cache_key", "safety_identifier", "text"}

SOURCES = {
    "search_exa.sse": "responses-openai_gpt-6-luna-stream-exa-noschema-defaultreasoning",
    "search_native.sse": "responses-openai_gpt-6-luna-stream-noschema-native",
    "schema_only.sse": "responses-anthropic_claude-haiku-5.5-stream-notools",
}


class Scrubber:
    def __init__(self) -> None:
        self.ids: dict[str, str] = {}

    def scrub(self, value: Any, key: str = "") -> Any:
        if isinstance(value, dict):
            return {
                k: self.scrub(v, k) for k, v in value.items() if not (k in DROP and key == "response")
            }
        if isinstance(value, list):
            return [self.scrub(v, key) for v in value]
        if isinstance(value, str):
            if key in ("encrypted_content", "signature"):
                return "REDACTED"
            if key in ("id", "item_id"):
                return self.ids.setdefault(value, f"id-{len(self.ids) + 1}")
            if key == "content" and len(value) > EXCERPT:
                return value[:EXCERPT]
        return value


def convert(name: str, source: str) -> None:
    scrubber = Scrubber()
    out: list[str] = []
    deltas = 0
    for line in (CAPTURES / f"{source}.response.sse").read_text().splitlines():
        if line.startswith(":"):
            if not any(kept.startswith(":") for kept in out):
                out.append(line)
            continue
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            out.append(line)
            continue
        event = json.loads(payload)
        if event.get("type", "").endswith(".delta"):
            deltas += 1
            if deltas > KEEP_DELTAS:
                continue
        if event.get("type") in ("response.output_text.done", "response.content_part.done"):
            continue
        out.append("data: " + json.dumps(scrubber.scrub(event), ensure_ascii=False))
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / name).write_text("\n\n".join(out) + "\n\n")
    print(name, len(out), "lines", (FIXTURES / name).stat().st_size, "bytes")


for fixture, capture in SOURCES.items():
    convert(fixture, capture)
