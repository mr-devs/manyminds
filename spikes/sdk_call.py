"""The same streamed search call as openrouter_spike.py, made through the OpenRouter SDK.

    uv run --with openrouter python spikes/sdk_call.py
"""

from __future__ import annotations

import os
import time

from openrouter import OpenRouter
from openrouter_spike import LEAD, SYSTEM

started = time.monotonic()
counts: dict[str, int] = {}
with OpenRouter(api_key=os.environ["OPENROUTER_API_KEY"]) as client:
    stream = client.responses.send(
        model="openai/gpt-6-luna",
        instructions=SYSTEM,
        input=f"Claim to research: {LEAD}",
        max_output_tokens=4000,
        max_tool_calls=1,
        tools=[
            {
                "type": "openrouter:web_search",
                "parameters": {"engine": "exa", "max_results": 3, "max_uses": 1},
            }
        ],
        stream=True,
    )
    final = None
    for event in stream:
        name = type(event).__name__
        counts[name] = counts.get(name, 0) + 1
        if name == "StreamEventsResponseOutputItemDone":
            print("item done:", type(event.item).__name__, str(event.item)[:160])
        if name == "StreamEventsResponseCompleted":
            final = event.response
print(counts)
if final is not None:
    for item in final.output:
        for part in getattr(item, "content", None) or []:
            anns = getattr(part, "annotations", None) or []
            print("annotations:", len(anns), [type(a).__name__ for a in anns[:1]])
            if anns:
                print("  has content:", bool(getattr(anns[0], "content", None)))
    print("usage cost:", getattr(final.usage, "cost", None))
print(f"elapsed {time.monotonic() - started:.1f}s")
