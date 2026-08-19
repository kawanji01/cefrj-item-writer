#!/usr/bin/env python3
"""Claude独立レビュアー起動を固定requestパス1件へ限定する。"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


COMMAND_RE = re.compile(
    r"python \.claude/run_reviewer\.py --request "
    r"(?P<path>output/[0-9]{8}-[0-9]{6}-[a-z0-9]{4}/review/"
    r"q(?:0[1-9]|1[0-9]|20)\.gen[123]\.request\.json)"
)


def deny(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        deny(f"レビュアー起動ガードの入力を解析できません: {exc}")
    if event.get("tool_name") != "Bash":
        return
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    command = tool_input.get("command")
    if not isinstance(command, str) or ".claude/run_reviewer.py" not in command:
        return
    match = COMMAND_RE.fullmatch(command)
    if match is None:
        deny("独立レビュアーは固定requestパス1件だけを指定して起動できます")
    repo_root = Path(__file__).resolve().parents[2]
    request_path = repo_root / match.group("path")
    if not os.path.isfile(request_path) or os.path.islink(request_path):
        deny("独立レビュアーの入力封筒が通常ファイルとして存在しません")

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": "固定requestパスの期限付き独立レビュー起動",
            }
        },
        sys.stdout,
        ensure_ascii=False,
    )


if __name__ == "__main__":
    main()
