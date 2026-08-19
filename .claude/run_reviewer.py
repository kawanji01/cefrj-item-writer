#!/usr/bin/env python3
"""Claude Code独立レビュアーを壁時計期限付きで1回だけ実行する。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


REQUEST_PATH_RE = re.compile(
    r"output/[0-9]{8}-[0-9]{6}-[a-z0-9]{4}/review/"
    r"q(?:0[1-9]|1[0-9]|20)\.gen[123]\.request\.json"
)
TIMEOUT_EXIT_CODE = 124
LAUNCH_ERROR_EXIT_CODE = 70
TERMINATION_GRACE_SECONDS = 1.0


class ReviewerTimeoutError(TimeoutError):
    """レビュアーのプロセスグループを期限超過で停止した。"""

    def __init__(self, pid: int) -> None:
        super().__init__(f"reviewer process {pid} timed out")
        self.pid = pid


@dataclass(frozen=True)
class ReviewerProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


def fail(message: str, exit_code: int = 2) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(exit_code)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="独立Claudeレビュアーを設定済み壁時計期限で1回実行します。"
    )
    parser.add_argument("--request", required=True)
    return parser.parse_args()


def _require_regular_path(path: Path, repo_root: Path) -> None:
    relative = path.relative_to(repo_root)
    current = repo_root
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            fail(f"レビュアー入力パスを確認できません: {exc}")
        if current != path and (not stat.S_ISDIR(mode) or current.is_symlink()):
            fail(f"レビュアー入力の親が実ディレクトリではありません: {current}")
    if not stat.S_ISREG(path.lstat().st_mode) or path.is_symlink():
        fail("レビュアー入力は通常ファイルでなければなりません")


def checked_request_path(raw_path: str, repo_root: Path) -> Path:
    if REQUEST_PATH_RE.fullmatch(raw_path) is None:
        fail("入力封筒パスが固定監査名に一致しません")
    path = repo_root / raw_path
    _require_regular_path(path, repo_root)
    return path


def load_timeout_seconds(repo_root: Path) -> int:
    limits_path = repo_root / "data/config/limits.json"
    try:
        limits = json.loads(limits_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"review_timeout_secondsを読み取れません: {exc}")
    value = limits.get("review_timeout_seconds") if isinstance(limits, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        fail("review_timeout_secondsは1以上の整数でなければなりません")
    return value


def build_prompt(request_path: str) -> bytes:
    prompt = (
        "agent/reviewer-core.md を読み、その指示に完全に従ってください。\n"
        f"入力封筒: {request_path}\n"
        "最終メッセージは review_result JSON 本文のみとし、"
        "JSON以外の文章を出力しないでください。\n"
    )
    return prompt.encode("utf-8", errors="strict")


def build_command(claude_path: str) -> list[str]:
    return [
        claude_path,
        "--safe-mode",
        "--print",
        "--system-prompt-file",
        "agent/reviewer-core.md",
        "--tools",
        "Read,Grep,Glob",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--no-chrome",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--output-format",
        "text",
    ]


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process.poll() is None:
        process.wait()


def run_with_timeout(
    command: Sequence[str], prompt: bytes, timeout_seconds: int, cwd: Path
) -> ReviewerProcessResult:
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(input=prompt, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _stop_process_group(process)
        raise ReviewerTimeoutError(process.pid) from None
    return ReviewerProcessResult(process.returncode, stdout, stderr)


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    checked_request_path(args.request, repo_root)
    timeout_seconds = load_timeout_seconds(repo_root)
    claude_path = shutil.which("claude")
    if claude_path is None:
        fail("claudeコマンドがPATH上にありません", LAUNCH_ERROR_EXIT_CODE)

    try:
        result = run_with_timeout(
            build_command(claude_path),
            build_prompt(args.request),
            timeout_seconds,
            repo_root,
        )
    except ReviewerTimeoutError:
        fail(
            f"独立レビュアーが{timeout_seconds}秒の壁時計期限を超過したため停止しました",
            TIMEOUT_EXIT_CODE,
        )
    except OSError as exc:
        fail(f"独立レビュアーを起動できません: {exc}", LAUNCH_ERROR_EXIT_CODE)

    if result.returncode != 0:
        if result.stderr:
            sys.stderr.buffer.write(result.stderr)
        raise SystemExit(result.returncode if result.returncode > 0 else LAUNCH_ERROR_EXIT_CODE)
    if not result.stdout:
        fail("独立レビュアーのstdoutが空です", LAUNCH_ERROR_EXIT_CODE)
    sys.stdout.buffer.write(result.stdout)


if __name__ == "__main__":
    main()
