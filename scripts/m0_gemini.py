"""Milestone 0: ask Gemini web to describe a local image. Confirms cookies work."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from onshape_mcp.vision import GeminiWeb


async def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python scripts/m0_gemini.py <image_path>")
        raise SystemExit(2)
    img = Path(sys.argv[1]).resolve()
    if not img.exists():
        raise SystemExit(f"image not found: {img}")
    g = GeminiWeb()
    answer = await g.ask_with_image(
        "Describe what you see in one short paragraph.", img
    )
    print(answer)
    await g.close()


if __name__ == "__main__":
    asyncio.run(main())
