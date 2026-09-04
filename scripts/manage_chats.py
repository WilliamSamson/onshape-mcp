"""Manage Gemini web conversations: list, inspect, and delete test chats.

Usage:
    python3 scripts/manage_chats.py --list
    python3 scripts/manage_chats.py --delete <cid>
    python3 scripts/manage_chats.py --delete-matching <keyword> [--force]
    python3 scripts/manage_chats.py --delete-test-chats [--force]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from onshape_mcp.vision import GeminiWeb  # noqa: E402

TEST_TITLE_KEYWORDS = [
    "onshape",
    "step",
    "reply only with a json object",
    "describe the current viewport",
    "what do you see in the onshape viewport",
    "sketch.rectangle",
    "feature.extrude",
    "task_step",
]


async def list_chats(gw: GeminiWeb) -> list:
    chats = await gw.list_chats()
    if not chats:
        print("[manage_chats] No chats found in account.")
        return []
    print(f"[manage_chats] Found {len(chats)} conversations:")
    for i, c in enumerate(chats, 1):
        cid = getattr(c, "cid", "unknown")
        title = getattr(c, "title", "(no title)")
        print(f"  {i:2d}. [{cid}] {title}")
    return chats


async def delete_single(gw: GeminiWeb, cid: str) -> None:
    ok = await gw.delete_chat(cid)
    if ok:
        print(f"[manage_chats] Successfully deleted chat: {cid}")
    else:
        print(f"[manage_chats] Failed to delete chat: {cid}", file=sys.stderr)


async def delete_matching(gw: GeminiWeb, pattern: str, force: bool = False) -> None:
    chats = await gw.list_chats()
    matches = [
        c
        for c in chats
        if pattern.lower() in getattr(c, "title", "").lower()
        or pattern.lower() in getattr(c, "cid", "").lower()
    ]
    if not matches:
        print(f"[manage_chats] No chats matched query: {pattern!r}")
        return

    print(f"[manage_chats] Matched {len(matches)} chats:")
    for m in matches:
        print(f"  - [{getattr(m, 'cid', '')}] {getattr(m, 'title', '')}")

    if not force:
        confirm = input("Proceed with deletion? [y/N]: ").strip().lower()
        if confirm != "y":
            print("[manage_chats] Aborted.")
            return

    deleted = 0
    for m in matches:
        cid = getattr(m, "cid", "")
        if cid and await gw.delete_chat(cid):
            deleted += 1
    print(f"[manage_chats] Deleted {deleted}/{len(matches)} matching chats.")


async def delete_test_chats(gw: GeminiWeb, force: bool = False) -> None:
    chats = await gw.list_chats()
    test_chats = []
    for c in chats:
        title = getattr(c, "title", "").lower()
        if any(kw in title for kw in TEST_TITLE_KEYWORDS):
            test_chats.append(c)

    if not test_chats:
        print("[manage_chats] No test/automated chats identified.")
        return

    print(f"[manage_chats] Found {len(test_chats)} automated test chats:")
    for tc in test_chats:
        print(f"  - [{getattr(tc, 'cid', '')}] {getattr(tc, 'title', '')}")

    if not force:
        confirm = input("Delete these test chats? [y/N]: ").strip().lower()
        if confirm != "y":
            print("[manage_chats] Aborted.")
            return

    deleted = 0
    for tc in test_chats:
        cid = getattr(tc, "cid", "")
        if cid and await gw.delete_chat(cid):
            deleted += 1
    print(f"[manage_chats] Cleaned up {deleted}/{len(test_chats)} test chats.")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Gemini web conversations.")
    parser.add_argument("--list", action="store_true", help="List all conversations")
    parser.add_argument("--delete", type=str, metavar="CID", help="Delete specific chat by CID")
    parser.add_argument(
        "--delete-matching", type=str, metavar="PATTERN", help="Delete chats matching keyword"
    )
    parser.add_argument(
        "--delete-test-chats", action="store_true", help="Clean up test/automated chats"
    )
    parser.add_argument("--force", "-f", action="store_true", help="Do not prompt for confirmation")

    args = parser.parse_args()
    if not (args.list or args.delete or args.delete_matching or args.delete_test_chats):
        parser.print_help()
        return 1

    gw = GeminiWeb()
    try:
        if args.list:
            await list_chats(gw)
        elif args.delete:
            await delete_single(gw, args.delete)
        elif args.delete_matching:
            await delete_matching(gw, args.delete_matching, force=args.force)
        elif args.delete_test_chats:
            await delete_test_chats(gw, force=args.force)
    finally:
        await gw.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
