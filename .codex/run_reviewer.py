#!/usr/bin/env python3
"""Codex独立レビュアーを壁時計期限付きで1回だけ実行する。"""

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
from typing import Mapping, Sequence


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
        description="独立Codexレビュアーを設定済み壁時計期限で1回実行します。"
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


def checked_reviewer_home() -> Path:
    reviewer_home = Path.home() / ".codex-cefrj-reviewer"
    try:
        mode = reviewer_home.lstat().st_mode
    except OSError as exc:
        fail(
            f"独立レビュアー専用CODEX_HOMEを確認できません: {exc}",
            LAUNCH_ERROR_EXIT_CODE,
        )
    if not stat.S_ISDIR(mode) or reviewer_home.is_symlink():
        fail(
            "独立レビュアー専用CODEX_HOMEは実ディレクトリでなければなりません",
            LAUNCH_ERROR_EXIT_CODE,
        )
    return reviewer_home


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
        "JSON以外の文章を出力しないでください。"
    )
    return prompt.encode("utf-8", errors="strict")


def derived_last_message_path(request_path: Path) -> Path:
    suffix = ".request.json"
    if not request_path.name.endswith(suffix):
        fail("入力封筒名からCodex作業ファイル名を導出できません")
    stem = request_path.name[: -len(suffix)]
    return request_path.with_name(f"{stem}.codex-last.txt")


def build_command(codex_path: str, repo_root: Path, last_message_path: Path) -> list[str]:
    return [
        codex_path,
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--disable",
        "recommended_plugins",
        "--disable",
        "apps",
        "--disable",
        "plugins",
        "--disable",
        "workspace_dependencies",
        "-c",
        "project_doc_max_bytes=0",
        "-c",
        "include_environment_context=false",
        "--ephemeral",
        "--cd",
        str(repo_root),
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--output-last-message",
        str(last_message_path),
        "-",
    ]


def _remove_work_file(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    except OSError as exc:
        fail(f"Codex作業ファイルを確認できません: {exc}", LAUNCH_ERROR_EXIT_CODE)
    if stat.S_ISDIR(mode):
        fail("Codex作業ファイル位置にディレクトリが存在します", LAUNCH_ERROR_EXIT_CODE)
    try:
        path.unlink()
    except OSError as exc:
        fail(f"Codex作業ファイルを削除できません: {exc}", LAUNCH_ERROR_EXIT_CODE)


def _read_last_message(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        fail(f"Codex最終メッセージを開けません: {exc}", LAUNCH_ERROR_EXIT_CODE)
    try:
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISREG(mode):
            fail("Codex最終メッセージは通常ファイルではありません", LAUNCH_ERROR_EXIT_CODE)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            payload = stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not payload:
        fail("独立レビュアーの最終メッセージが空です", LAUNCH_ERROR_EXIT_CODE)
    return payload


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
    command: Sequence[str],
    prompt: bytes,
    timeout_seconds: int,
    cwd: Path,
    env: Mapping[str, str],
) -> ReviewerProcessResult:
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=dict(env),
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
    request_path = checked_request_path(args.request, repo_root)
    timeout_seconds = load_timeout_seconds(repo_root)
    reviewer_home = checked_reviewer_home()
    codex_path = shutil.which("codex")
    if codex_path is None:
        fail("codexコマンドがPATH上にありません", LAUNCH_ERROR_EXIT_CODE)

    last_message_path = derived_last_message_path(request_path)
    _remove_work_file(last_message_path)
    child_env = os.environ.copy()
    child_env["CODEX_HOME"] = str(reviewer_home)

    try:
        result = run_with_timeout(
            build_command(codex_path, repo_root, last_message_path),
            build_prompt(args.request),
            timeout_seconds,
            repo_root,
            child_env,
        )
    except ReviewerTimeoutError:
        _remove_work_file(last_message_path)
        fail(
            f"独立レビュアーが{timeout_seconds}秒の壁時計期限を超過したため停止しました",
            TIMEOUT_EXIT_CODE,
        )
    except OSError as exc:
        _remove_work_file(last_message_path)
        fail(f"独立レビュアーを起動できません: {exc}", LAUNCH_ERROR_EXIT_CODE)

    if result.returncode != 0:
        _remove_work_file(last_message_path)
        if result.stderr:
            sys.stderr.buffer.write(result.stderr)
        raise SystemExit(result.returncode if result.returncode > 0 else LAUNCH_ERROR_EXIT_CODE)

    payload = _read_last_message(last_message_path)
    sys.stdout.buffer.write(payload)


if __name__ == "__main__":
    main()
