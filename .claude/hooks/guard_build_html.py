#!/usr/bin/env python3
"""Claude Code の build_html.py 呼出しを標準出力先の固定形式だけに限定する。"""

from __future__ import annotations

import json
import re
import sys


COMMAND_RE = re.compile(
    r"python scripts/build_html\.py --set "
    r"output/[0-9]{8}-[0-9]{6}-[a-z0-9]{4}/set\.json"
)


def deny(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        deny(f"HTML生成権限ガードの入力を解析できません: {exc}")

    if event.get("tool_name") != "Bash":
        return
    command = event.get("tool_input", {}).get("command")
    if not isinstance(command, str) or "scripts/build_html.py" not in command:
        return
    if COMMAND_RE.fullmatch(command) is None:
        deny(
            "build_html.pyは固定set.jsonパス1件を指定し、"
            "既定のindex.htmlへ出力する標準形式だけ実行できます"
        )

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": (
                    "固定set.jsonパスから既定のindex.htmlを生成"
                ),
            }
        },
        sys.stdout,
        ensure_ascii=False,
    )


if __name__ == "__main__":
    main()
