#!/usr/bin/env python3
"""Claude Code の machine_check.py 呼出しを安全な固定引数形に限定する。"""

from __future__ import annotations

import json
import re
import sys


COMMAND_RE = re.compile(
    r"python scripts/machine_check\.py --candidate "
    r"output/(?P<path_set>[0-9]{8}-[0-9]{6}-[a-z0-9]{4})/review/"
    r"q[0-9]+\.(?P<path_generation>gen[0-9]+)\.candidate\.json "
    r"--set-id (?P<set_id>[0-9]{8}-[0-9]{6}-[a-z0-9]{4}) "
    r"--generation (?P<generation>gen[0-9]+) "
    r"--expected-format [a-z][a-z0-9_]* "
    r"--expected-level [A-Za-z0-9._-]+ "
    r"--requested-count [0-9]+"
)


def deny(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        deny(f"機械検査権限ガードの入力を解析できません: {exc}")

    if event.get("tool_name") != "Bash":
        return
    command = event.get("tool_input", {}).get("command")
    if not isinstance(command, str) or "scripts/machine_check.py" not in command:
        return
    match = COMMAND_RE.fullmatch(command)
    if match is None:
        deny("machine_check.pyは固定順の安全な単一コマンド形式だけ実行できます")
    if match.group("path_set") != match.group("set_id"):
        deny("candidate監査パスのset_idと--set-idが一致しません")
    if match.group("path_generation") != match.group("generation"):
        deny("candidate監査パスの世代と--generationが一致しません")

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": (
                    "固定監査パスと固定引数順の機械検査コマンド"
                ),
            }
        },
        sys.stdout,
        ensure_ascii=False,
    )


if __name__ == "__main__":
    main()
