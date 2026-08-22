#!/usr/bin/env python3
"""一時ファイル操作を限定し、CCW-11の内部state読取りを拒否する。"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


RELATIVE_STAGING_RE = re.compile(
    r"output/[0-9]{8}-[0-9]{6}-[a-z0-9]{4}/\.staging/"
    r"q(?:0[1-9]|1[0-9]|20)\.gen[123]\."
    r"(?P<kind>candidate\.raw[12]|request\.raw)\.json"
)
RELATIVE_FLOW_STATE_RE = re.compile(
    r"output/[0-9]{8}-[0-9]{6}-[a-z0-9]{4}/\.staging/flow-state\.json"
)
RELATIVE_SET_DIR_RE = re.compile(
    r"output/[0-9]{8}-[0-9]{6}-[a-z0-9]{4}"
)
RELATIVE_STAGING_DIR_RE = re.compile(
    r"output/[0-9]{8}-[0-9]{6}-[a-z0-9]{4}/\.staging"
)
CANDIDATE_VALIDATE_RE = re.compile(
    r"python scripts/validate\.py --schema candidate --file "
    r"(?P<path>output/[0-9]{8}-[0-9]{6}-[a-z0-9]{4}/\.staging/"
    r"q(?:0[1-9]|1[0-9]|20)\.gen[123]\.candidate\.raw[12]\.json)"
)
REQUEST_VALIDATE_RE = re.compile(
    r"python scripts/validate\.py --schema review_request --file "
    r"(?P<path>output/[0-9]{8}-[0-9]{6}-[a-z0-9]{4}/\.staging/"
    r"q(?:0[1-9]|1[0-9]|20)\.gen[123]\.request\.raw\.json)"
)
CLEANUP_RE = re.compile(
    r"python \.claude/cleanup_staging\.py --file "
    r"(?P<path>output/[0-9]{8}-[0-9]{6}-[a-z0-9]{4}/\.staging/"
    r"q(?:0[1-9]|1[0-9]|20)\.gen[123]\."
    r"(?:candidate\.raw[12]|request\.raw)\.json)"
)
FLOW_CANDIDATE_RE = re.compile(
    r"python scripts/flow_control\.py candidate --set-dir "
    r"(?P<set_dir>output/(?P<set_id>[0-9]{8}-[0-9]{6}-[a-z0-9]{4})) --file "
    r"(?P<path>output/(?P=set_id)/\.staging/"
    r"q(?:0[1-9]|1[0-9]|20)\.gen[123]\.candidate\.raw[12]\.json)"
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


def repo_relative(raw_path: str, repo_root: Path) -> str | None:
    path = Path(raw_path)
    if path.is_absolute():
        try:
            raw_relative = path.relative_to(repo_root).as_posix()
        except ValueError:
            return None
    else:
        raw_relative = raw_path
    normalized = os.path.normpath(raw_relative)
    if normalized.startswith("../") or normalized == "..":
        return None
    return Path(normalized).as_posix()


def guard_read(event: dict[str, object], repo_root: Path) -> None:
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    raw_path = tool_input.get("file_path")
    if not isinstance(raw_path, str):
        return
    relative = repo_relative(raw_path, repo_root)
    if (
        relative is not None
        and RELATIVE_FLOW_STATE_RE.fullmatch(relative) is not None
    ):
        deny(
            "CCW-11: flow-state.jsonはC12内部専用です。"
            "python scripts/flow_control.py statusを使用してください"
        )


def grep_scope_contains_flow_state(raw_path: str, repo_root: Path) -> bool:
    scope = Path(raw_path)
    if not scope.is_absolute():
        scope = repo_root / scope
    try:
        resolved_scope = scope.resolve(strict=False)
        resolved_root = repo_root.resolve(strict=True)
    except OSError:
        return True
    try:
        relative = resolved_scope.relative_to(resolved_root).as_posix()
    except ValueError:
        try:
            resolved_root.relative_to(resolved_scope)
        except ValueError:
            return False
        return True
    return (
        relative in {".", "output"}
        or RELATIVE_SET_DIR_RE.fullmatch(relative) is not None
        or RELATIVE_STAGING_DIR_RE.fullmatch(relative) is not None
        or RELATIVE_FLOW_STATE_RE.fullmatch(relative) is not None
    )


def guard_grep(event: dict[str, object], repo_root: Path) -> None:
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        deny("CCW-11: Grepの検索範囲を確認できません")
    raw_path = tool_input.get("path")
    if not isinstance(raw_path, str) or grep_scope_contains_flow_state(
        raw_path, repo_root
    ):
        deny(
            "CCW-11: Grepの検索範囲にC12内部専用flow-state.jsonが含まれます。"
            "公開済み成果物またはpython scripts/flow_control.py statusを使用してください"
        )


def guard_write(event: dict[str, object], repo_root: Path) -> None:
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    raw_path = tool_input.get("file_path")
    if not isinstance(raw_path, str) or ".staging" not in raw_path:
        return
    relative = repo_relative(raw_path, repo_root)
    if relative is None or RELATIVE_STAGING_RE.fullmatch(relative) is None:
        deny(".stagingへの書込みはM7D-12の固定一時ファイル名だけ許可されます")
    if os.path.lexists(repo_root / relative):
        deny(f"E-DATA-07: 一時ファイルが既に存在します: {relative}")
    allow("M7D-12の固定一時ファイルを排他的に新規作成")


def guard_bash(event: dict[str, object], repo_root: Path) -> None:
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    command = tool_input.get("command")
    if not isinstance(command, str):
        return
    if ".staging" not in command and ".claude/cleanup_staging.py" not in command:
        return
    for command_re, reason in (
        (CANDIDATE_VALIDATE_RE, "固定candidate一時ファイルの受理検証"),
        (REQUEST_VALIDATE_RE, "固定review_request一時ファイルの受理検証"),
        (CLEANUP_RE, "固定一時ファイルの専用削除"),
        (FLOW_CANDIDATE_RE, "固定candidate一時ファイルのフロー制御入力"),
    ):
        match = command_re.fullmatch(command)
        if match is None:
            continue
        relative = match.group("path")
        if not os.path.isfile(repo_root / relative) or os.path.islink(repo_root / relative):
            deny(f"一時ファイルが通常ファイルとして存在しません: {relative}")
        allow(reason)
        return
    deny(".staging操作は固定検証または専用削除コマンドだけ許可されます")


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        deny(f"staging権限ガードの入力を解析できません: {exc}")
    if not isinstance(event, dict):
        deny("staging権限ガードの入力はJSON objectでなければなりません")

    repo_root = Path(__file__).resolve().parents[2]
    tool_name = event.get("tool_name")
    if tool_name == "Read":
        guard_read(event, repo_root)
    elif tool_name == "Grep":
        guard_grep(event, repo_root)
    elif tool_name in {"Write", "Edit"}:
        guard_write(event, repo_root)
    elif tool_name == "Bash":
        guard_bash(event, repo_root)


if __name__ == "__main__":
    main()
