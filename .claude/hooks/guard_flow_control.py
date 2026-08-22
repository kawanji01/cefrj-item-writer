#!/usr/bin/env python3
"""Claude Codeのflow_control.py呼出しを固定イベント形へ限定する。"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path


SET_ID = r"[0-9]{8}-[0-9]{6}-[a-z0-9]{4}"
INIT_RE = re.compile(
    rf"python scripts/flow_control\.py init --set-dir output/(?P<set_id>{SET_ID}) "
    r"--file - <<'FLOW01'\n(?P<body>[\s\S]+)\nFLOW01"
)


def deny(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def allow(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
        ensure_ascii=False,
    )


def parse_object(body: str, label: str) -> dict[str, object]:
    try:
        value = json.loads(body)
    except (json.JSONDecodeError, ValueError) as exc:
        deny(f"{label}のstdinがJSON object 1個ではありません: {exc}")
    if not isinstance(value, dict):
        deny(f"{label}のstdinトップレベルはJSON objectでなければなりません")
    return value


def guard_heredoc(command: str) -> bool:
    match = INIT_RE.fullmatch(command)
    if match is not None:
        value = parse_object(match.group("body"), "flow init")
        if value.get("set_id") != match.group("set_id"):
            deny("flow initのset_idが--set-dirと一致しません")
        allow("固定FLOW01入力によるフロー初期化")
        return True
    return False


def guard_argv(command: str, repo_root: Path) -> None:
    try:
        arguments = shlex.split(command, posix=True)
    except ValueError as exc:
        deny(f"flow_control.pyコマンドを解析できません: {exc}")
    prefix = ["python", "scripts/flow_control.py"]
    if arguments[:2] != prefix or len(arguments) < 5:
        deny("flow_control.pyは固定サブコマンド形式だけ実行できます")
    subcommand = arguments[2]
    if arguments[3] != "--set-dir" or re.fullmatch(rf"output/{SET_ID}", arguments[4]) is None:
        deny("flow_control.pyの--set-dirが固定output形式ではありません")
    set_dir = arguments[4]
    if subcommand == "candidate":
        if len(arguments) != 7 or arguments[5] != "--file":
            deny("flow candidateは固定7引数形式だけ許可されます")
        expected = re.compile(
            re.escape(set_dir)
            + rf"/\.staging/q(?:0[1-9]|1[0-9]|20)\.gen[123]\.candidate\.raw[12]\.json"
        )
        if expected.fullmatch(arguments[6]) is None:
            deny("flow candidateの入力名が固定candidate raw形式ではありません")
        path = repo_root / arguments[6]
        if not path.is_file() or path.is_symlink():
            deny("flow candidateの入力が通常ファイルとして存在しません")
        allow("固定candidate raw入力によるフロー遷移")
        return
    if subcommand == "status" and len(arguments) == 5:
        allow("フロー状態の読取り専用確認")
        return
    if subcommand == "decide":
        if len(arguments) not in {7, 9} or arguments[5] != "--decision":
            deny("flow decideの引数形が不正です")
        decision = arguments[6]
        if decision in {"reduce", "abort"} and len(arguments) == 7:
            allow("提示済み教師判断のフロー入力")
            return
        if (
            decision == "alternative"
            and len(arguments) == 9
            and arguments[7] == "--target-ref"
            and arguments[8]
            and not re.search(r"[\x00-\x1f\x7f]", arguments[8])
            and not re.search(r"[$`;&|<>(){}\[\]*?!\\]", arguments[8])
        ):
            allow("照合済み代替対象のフロー入力")
            return
        deny("flow decideの判断値または代替対象が不正です")
    deny("flow_control.pyはホスト側からinit/candidate/decide/statusの固定形だけ許可されます")


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        deny(f"flow制御権限ガードの入力を解析できません: {exc}")
    if not isinstance(event, dict) or event.get("tool_name") != "Bash":
        return
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    command = tool_input.get("command")
    if not isinstance(command, str) or "scripts/flow_control.py" not in command:
        return
    if "<<" in command:
        if guard_heredoc(command):
            return
        deny("flow_control.pyのヒアドキュメント形式が固定形と一致しません")
    guard_argv(command, Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd())))


if __name__ == "__main__":
    main()
