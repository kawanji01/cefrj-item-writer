#!/usr/bin/env python3
"""Claude Code の review_result 検証を REV01 形式だけに限定する。"""

from __future__ import annotations

import json
import sys


FIRST_LINE = "python scripts/validate.py --schema review_result --file - <<'REV01'"


def deny(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        deny(f"review_result権限ガードの入力を解析できません: {exc}")

    if event.get("tool_name") != "Bash":
        return
    command = event.get("tool_input", {}).get("command")
    if not isinstance(command, str):
        return
    if "scripts/validate.py" not in command or "--schema review_result" not in command:
        return

    lines = command.splitlines()
    if len(lines) < 3 or lines[0] != FIRST_LINE or lines[-1] != "REV01":
        deny("review_resultは引用付きREV01ヒアドキュメントの固定形式だけ検証できます")
    if "$(" in lines[0] or "`" in lines[0]:
        deny("review_result検証コマンドにコマンド置換を含めてはなりません")

    body = "\n".join(lines[1:-1])
    try:
        review_result = json.loads(body)
    except json.JSONDecodeError as exc:
        deny(f"REV01本文はJSON文書1個でなければなりません: {exc}")
    if not isinstance(review_result, dict):
        deny("REV01本文はJSON objectでなければなりません")

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": (
                    "引用付きREV01ヒアドキュメントの固定形式に適合"
                ),
            }
        },
        sys.stdout,
        ensure_ascii=False,
    )


if __name__ == "__main__":
    main()
