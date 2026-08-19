#!/usr/bin/env python3
"""Claude Code の finalize_set.py 呼出しを FIN01 形式だけに限定する。"""

from __future__ import annotations

import json
import re
import sys


COMMAND_RE = re.compile(
    r"python scripts/finalize_set\.py --set-dir "
    r"output/[0-9]{8}-[0-9]{6}-[a-z0-9]{4} <<'FIN01'"
)


def deny(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        deny(f"finalize権限ガードの入力を解析できません: {exc}")

    if event.get("tool_name") != "Bash":
        return
    command = event.get("tool_input", {}).get("command")
    if not isinstance(command, str) or "scripts/finalize_set.py" not in command:
        return
    if "$(" in command or "`" in command:
        deny("finalize_set.pyの入力にコマンド置換を含めてはなりません")

    lines = command.splitlines()
    if len(lines) != 3 or COMMAND_RE.fullmatch(lines[0]) is None or lines[2] != "FIN01":
        deny("finalize_set.pyは引用付きFIN01ヒアドキュメントの固定3行形式だけ実行できます")
    try:
        metadata = json.loads(lines[1])
    except json.JSONDecodeError as exc:
        deny(f"FIN01本文は1行のJSON文書でなければなりません: {exc}")
    if not isinstance(metadata, dict):
        deny("FIN01本文はJSON objectでなければなりません")

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": "引用付きFIN01ヒアドキュメントの固定3行形式に適合",
            }
        },
        sys.stdout,
        ensure_ascii=False,
    )


if __name__ == "__main__":
    main()
