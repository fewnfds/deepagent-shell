from __future__ import annotations

import re


async def run(ctx):
    value = ctx.inputs["text"]
    normalized = re.sub(r"\s+", " ", str(value)).strip()
    return {
        "outputs": {"result": normalized},
        "shared": {
            **dict(ctx.state.get("shared") or {}),
            "last_normalized_text": normalized,
        },
    }
