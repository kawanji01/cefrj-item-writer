#!/usr/bin/env python3
"""Claude Code独立レビュアーを1回実行し、結果をC12へ安全に渡す。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
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


@dataclass(frozen=True)
class ReviewerProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


class ReviewerLaunchError(RuntimeError):
    """request確定後のレビュアー起動準備に失敗した。"""


def fail(message: str, exit_code: int = 2) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(exit_code)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="独立Claudeレビュアーを設定済み壁時計期限で1回実行します。"
    )
    parser.add_argument("--request", required=True)
    return parser.parse_args()


def checked_request_path(raw_path: str, repo_root: Path) -> Path:
    if REQUEST_PATH_RE.fullmatch(raw_path) is None:
        fail("入力封筒パスが固定監査名に一致しません")
    return repo_root / raw_path


def run_review_preflight(
    repo_root: Path, request_path: Path
) -> subprocess.CompletedProcess[bytes]:
    """C12に設定・snapshot・直前requestと適用timeoutを一括確定させる。"""

    relative_request = request_path.relative_to(repo_root).as_posix()
    set_dir = request_path.parents[1].relative_to(repo_root).as_posix()
    return subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "flow_control.py"),
            "review-preflight",
            "--set-dir",
            set_dir,
            "--request",
            relative_request,
        ],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def preflight_timeout_seconds(
    completed: subprocess.CompletedProcess[bytes], request_path: str
) -> int:
    try:
        result = json.loads(completed.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewerLaunchError(f"review preflight結果を読み取れません: {exc}") from exc
    if not isinstance(result, dict) or set(result) != {
        "request_path",
        "review_timeout_seconds",
    }:
        raise ReviewerLaunchError("review preflight結果の固定フィールドが不正です")
    if result["request_path"] != request_path:
        raise ReviewerLaunchError("review preflight結果のrequest_pathが一致しません")
    value = result["review_timeout_seconds"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ReviewerLaunchError("review preflight結果のtimeoutが不正です")
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


def _merge_timeout_stderr(
    partial: bytes | str | None, drained: bytes
) -> bytes:
    partial_bytes = (
        partial.encode("utf-8") if isinstance(partial, str) else partial or b""
    )
    if not partial_bytes:
        return drained
    if not drained:
        return partial_bytes
    limit = min(len(partial_bytes), len(drained))
    pattern = drained[:limit]
    prefix_lengths = [0] * limit
    matched = 0
    for index in range(1, limit):
        while matched and pattern[index] != pattern[matched]:
            matched = prefix_lengths[matched - 1]
        if pattern[index] == pattern[matched]:
            matched += 1
        prefix_lengths[index] = matched
    matched = 0
    for value in partial_bytes[-limit:]:
        while matched and value != pattern[matched]:
            matched = prefix_lengths[matched - 1]
        if value == pattern[matched]:
            matched += 1
    return partial_bytes + drained[matched:]


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
    except subprocess.TimeoutExpired as exc:
        _stop_process_group(process)
        _discarded_stdout, drained_stderr = process.communicate()
        stderr = _merge_timeout_stderr(exc.stderr, drained_stderr)
        return ReviewerProcessResult(TIMEOUT_EXIT_CODE, b"", stderr)
    return ReviewerProcessResult(process.returncode, stdout, stderr)


def submit_to_flow_control(
    repo_root: Path,
    request_path: Path,
    result: ReviewerProcessResult,
) -> subprocess.CompletedProcess[bytes]:
    """非信頼のreviewer bytesをシェルを介さずC12へ1回渡す。"""

    set_dir = request_path.parents[1].relative_to(repo_root).as_posix()
    command = [
        sys.executable,
        str(repo_root / "scripts" / "flow_control.py"),
        "review",
        "--set-dir",
        set_dir,
    ]
    if result.returncode == 0 and result.stdout:
        command.extend(["--file", "-"])
        payload = result.stdout
    else:
        command.extend(["--process-failure", str(result.returncode)])
        payload = result.stderr
    return subprocess.run(
        command,
        cwd=repo_root,
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def relay(completed: subprocess.CompletedProcess[bytes]) -> int:
    if completed.stdout:
        sys.stdout.buffer.write(completed.stdout)
    if completed.stderr:
        sys.stderr.buffer.write(completed.stderr)
    return completed.returncode


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    request_path = checked_request_path(args.request, repo_root)
    try:
        preflight = run_review_preflight(repo_root, request_path)
        if preflight.returncode != 0:
            raise SystemExit(relay(preflight))
        timeout_seconds = preflight_timeout_seconds(preflight, args.request)
        claude_path = shutil.which("claude")
        if claude_path is None:
            raise ReviewerLaunchError("claudeコマンドがPATH上にありません")
        result = run_with_timeout(
            build_command(claude_path),
            build_prompt(args.request),
            timeout_seconds,
            repo_root,
        )
    except (OSError, ReviewerLaunchError) as exc:
        result = ReviewerProcessResult(
            LAUNCH_ERROR_EXIT_CODE,
            b"",
            f"独立レビュアーを起動できません: {exc}\n".encode("utf-8"),
        )

    raise SystemExit(relay(submit_to_flow_control(repo_root, request_path, result)))


if __name__ == "__main__":
    main()
