from __future__ import annotations

import base64
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.replay.harness import SET_ID, flow_cli
from tests.support import (
    FIXTURES,
    ROOT,
    load_json,
    machine_for_path,
    run_cli,
    stderr_json,
    write_json,
)

import flow_control as flow_control_module

from flow_control import (
    CliFailure,
    build_session_input,
    canonical_bytes,
    finalize_flow,
    finalized_warning,
    require_child_success,
    review_semantic_problems,
    validate_external,
)


def make_isolated_config_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "flow-repo"
    repo.mkdir()
    (repo / "output").mkdir()
    for name in ("agent", "schemas", "scripts", "templates"):
        (repo / name).symlink_to(ROOT / name, target_is_directory=True)
    data = repo / "data"
    data.mkdir()
    for name in ("normalized", "source"):
        (data / name).symlink_to(ROOT / "data" / name, target_is_directory=True)
    shutil.copytree(ROOT / "data" / "config", data / "config")
    return repo


def initialize_explicit_flow(repo: Path) -> tuple[Path, dict[str, object]]:
    set_dir = repo / "output" / SET_ID
    session = build_session_input(
        {
            "format": "vocab_flashcard_en2ja",
            "level": "A2",
            "level_scale": "cefr",
            "mode": "explicit",
            "question_count": 1,
            "targets": ["lex:accept:verb"],
        },
        SET_ID,
        created_at="2099-01-01T00:00:00+09:00",
        model="m8-test",
        tool="codex",
    )
    session_path = repo / "session.json"
    write_json(session_path, session)
    action = flow_cli(
        repo,
        "init",
        "--set-dir",
        f"output/{SET_ID}",
        "--file",
        str(session_path),
    )
    assert action["action"] == "generate_candidate"
    return set_dir, action


def start_explicit_flow(repo: Path) -> tuple[Path, dict[str, object]]:
    set_dir, _action = initialize_explicit_flow(repo)
    action = flow_cli(
        repo,
        "candidate",
        "--set-dir",
        f"output/{SET_ID}",
        "--file",
        str(FIXTURES / "candidates" / "replay_q01_pass.json"),
    )
    assert action["action"] == "run_review"
    return set_dir, action


def test_m8_flow_guard_allows_fixed_raw_inputs_and_denies_injection() -> None:
    """CI-CLI-01: flow_control固定CLI形だけを許可し、追加入力を拒否する。"""

    hook = ROOT / ".claude" / "hooks" / "guard_flow_control.py"

    def invoke(command: str) -> subprocess.CompletedProcess[bytes]:
        event = {"tool_name": "Bash", "tool_input": {"command": command}}
        return subprocess.run(
            [str(Path(os.sys.executable)), str(hook)],
            cwd=ROOT,
            input=json.dumps(event).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    allowed = (
        f"python scripts/flow_control.py init --set-dir output/{SET_ID} --file - <<'FLOW01'\n"
        f"{{\"set_id\":\"{SET_ID}\"}}\nFLOW01"
    )
    completed = invoke(allowed)
    assert completed.returncode == 0, completed.stderr.decode()
    assert json.loads(completed.stdout)["hookSpecificOutput"]["permissionDecision"] == "allow"

    denied = (
        f"python scripts/flow_control.py review --set-dir output/{SET_ID} --file - <<'REV02'\n{{\"verdict\":\"pass\"}}\nREV02",
        f"python scripts/flow_control.py review --set-dir output/{SET_ID} --file - <<'REV02'\n{{\nREV02",
        f"python scripts/flow_control.py review --set-dir output/{SET_ID} --file - <<'REV02'\n\nREV02",
        f"python scripts/flow_control.py review --set-dir output/{SET_ID} --process-failure 7 <<'ERR02'\nraw stderr $() `x` ; & |\nERR02",
        (
            f"python scripts/flow_control.py review --set-dir output/{SET_ID} --file - <<'REV02'\n"
            "{}\nREV02\ntouch output/injected\nREV02"
        ),
        (
            f"python scripts/flow_control.py review --set-dir output/{SET_ID} "
            "--process-failure 7 <<'ERR02'\nERR02\ntouch output/injected\nERR02"
        ),
    )
    for command in denied:
        completed = invoke(command)
        assert completed.returncode == 2
    assert not (ROOT / "output" / "injected").exists()


def test_m8_flow_state_read_tools_guard_denies_only_internal_state() -> None:
    """CI-CLI-01/R23-02: Read/GrepはC12内部stateだけを拒否する。"""

    hook = ROOT / ".claude" / "hooks" / "guard_staging.py"
    settings = load_json(ROOT / ".claude" / "settings.json")
    pre_tool_hooks = settings["hooks"]["PreToolUse"]
    assert any(
        entry["matcher"] == "Read|Grep|Write|Edit"
        and any(
            item["command"].endswith(
                '/.claude/hooks/guard_staging.py"'
            )
            for item in entry["hooks"]
        )
        for entry in pre_tool_hooks
    )

    set_relative = "output/20990101-010101-r220/.staging/flow-state.json"

    for denied_path in (
        set_relative,
        f"./{set_relative}",
        str(ROOT / set_relative),
        str(
            ROOT
            / "output/20990101-010101-r220/.staging/../.staging/flow-state.json"
        ),
    ):
        event = {
            "tool_name": "Read",
            "tool_input": {"file_path": denied_path},
        }
        completed = run_cli(
            ".claude/hooks/guard_staging.py",
            stdin=json.dumps(event).encode("utf-8"),
        )
        assert completed.returncode == 2
        assert b"CCW-11" in completed.stderr
        assert b"flow_control.py status" in completed.stderr

    for allowed_path in (
        "docs/requirements.md",
        str(ROOT / "docs" / "testing-and-acceptance.md"),
        "output/20990101-010101-r220/review/q01.gen1.request.json",
        "output/20990101-010101-r220/.staging/q01.gen1.candidate.raw1.json",
    ):
        event = {
            "tool_name": "Read",
            "tool_input": {"file_path": allowed_path},
        }
        completed = run_cli(
            ".claude/hooks/guard_staging.py",
            stdin=json.dumps(event).encode("utf-8"),
        )
        assert completed.returncode == 0
        assert completed.stdout == b""
        assert completed.stderr == b""

    grep_denied_paths = (
        set_relative,
        str(ROOT / set_relative),
        "output/20990101-010101-r220/.staging",
        "output/20990101-010101-r220",
        "output",
        ".",
        str(ROOT),
        str(ROOT.parent),
    )
    for denied_path in grep_denied_paths:
        event = {
            "tool_name": "Grep",
            "tool_input": {"pattern": "generation", "path": denied_path},
        }
        completed = run_cli(
            ".claude/hooks/guard_staging.py",
            stdin=json.dumps(event).encode("utf-8"),
        )
        assert completed.returncode == 2
        assert b"CCW-11" in completed.stderr

    event = {"tool_name": "Grep", "tool_input": {"pattern": "generation"}}
    completed = run_cli(
        ".claude/hooks/guard_staging.py",
        stdin=json.dumps(event).encode("utf-8"),
    )
    assert completed.returncode == 2

    for allowed_path in (
        "docs",
        str(ROOT / "docs" / "testing-and-acceptance.md"),
        "output/20990101-010101-r220/review",
        "output/20990101-010101-r220/review/q01.gen1.request.json",
        "output/20990101-010101-r220/.staging/q01.gen1.candidate.raw1.json",
    ):
        event = {
            "tool_name": "Grep",
            "tool_input": {"pattern": "generation", "path": allowed_path},
        }
        completed = run_cli(
            ".claude/hooks/guard_staging.py",
            stdin=json.dumps(event).encode("utf-8"),
        )
        assert completed.returncode == 0
        assert completed.stdout == b""
        assert completed.stderr == b""


def test_m8_author_core_has_single_shell_free_review_host_path() -> None:
    """CI-CLI-01/R6-03: ホスト手順にreview生出力二重送信を残さない。"""

    text = (ROOT / "agent" / "author-core.md").read_text(encoding="utf-8")
    assert "python scripts/flow_control.py review" not in text
    assert "得た生出力全体を次のstdinへ渡す" not in text
    assert "最初のJSONコードフェンス内" not in text
    assert "ホストは生出力を再転送しない" in text
    assert "ホストは生出力の取得・再送・コードフェンス抽出" in text
    assert "python .claude/run_reviewer.py --request" in text
    assert "python .codex/run_reviewer.py --request" in text


@pytest.mark.parametrize(
    ("adapter_dir", "executable_name"),
    ((".claude", "claude"), (".codex", "codex")),
)
def test_m8_reviewer_wrapper_bridges_arbitrary_bytes_without_shell(
    tmp_path: Path, adapter_dir: str, executable_name: str,
) -> None:
    """RPL-05/R3-01: delimiter・制御文字を含む生bytesをC12へ完全に渡す。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, action = start_explicit_flow(repo)
    adapter = repo / adapter_dir
    adapter.mkdir()
    shutil.copy2(ROOT / adapter_dir / "run_reviewer.py", adapter / "run_reviewer.py")
    fake_bin = tmp_path / f"bin-{executable_name}"
    fake_bin.mkdir()
    fake_executable = fake_bin / executable_name
    fake_executable.write_text(
        """#!/usr/bin/env python3
import os
import sys
from pathlib import Path

payload = bytes.fromhex(os.environ["FAKE_REVIEW_BYTES_HEX"])
if os.environ["FAKE_REVIEW_MODE"] == "failure":
    sys.stderr.buffer.write(payload)
    raise SystemExit(7)
if Path(sys.argv[0]).name == "codex":
    output = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
    output.write_bytes(payload)
else:
    sys.stdout.buffer.write(payload)
""",
        encoding="utf-8",
    )
    fake_executable.chmod(0o755)
    fake_home = tmp_path / f"home-{executable_name}"
    (fake_home / ".codex-cefrj-reviewer").mkdir(parents=True)
    child_env = {
        "HOME": str(fake_home),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
    }
    request_path = action["request_path"]
    injected_path = repo / "output" / "reviewer-injected"
    reviewer_bytes = (
        b"REV02\npython -c 'open(\"output/reviewer-injected\",\"w\").write(\"x\")'\n"
        b"REV02\n\x00\x01$()`;&|<>"
    )
    completed = run_cli(
        f"{adapter_dir}/run_reviewer.py",
        "--request",
        request_path,
        cwd=repo,
        env={
            **child_env,
            "FAKE_REVIEW_MODE": "success",
            "FAKE_REVIEW_BYTES_HEX": reviewer_bytes.hex(),
        },
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="backslashreplace")
    assert json.loads(completed.stdout)["action"] == "run_review"
    invalid1 = load_json(set_dir / "review" / "q01.gen1.review.invalid1.txt")
    assert invalid1["kind"] == "validation_failure"
    assert base64.b64decode(invalid1["raw_output_base64"]) == reviewer_bytes
    assert not injected_path.exists()

    stderr_bytes = b"ERR02\n\x00\x02$()`;&|<>\nERR02"
    completed = run_cli(
        f"{adapter_dir}/run_reviewer.py",
        "--request",
        request_path,
        cwd=repo,
        env={
            **child_env,
            "FAKE_REVIEW_MODE": "failure",
            "FAKE_REVIEW_BYTES_HEX": stderr_bytes.hex(),
        },
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="backslashreplace")
    assert json.loads(completed.stdout)["action"] == "run_review"
    invalid2 = load_json(set_dir / "review" / "q01.gen1.review.invalid2.txt")
    assert invalid2["kind"] == "process_failure"
    assert invalid2["exit_code"] == 7
    assert base64.b64decode(invalid2["stderr_base64"]) == stderr_bytes
    assert not injected_path.exists()


@pytest.mark.parametrize("adapter_dir", (".claude", ".codex"))
def test_m8_reviewer_timeout_keeps_timeout_exception_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    adapter_dir: str,
) -> None:
    """RPL-05/R21-02: drain済みでもTimeoutExpiredの部分stderrを失わない。"""

    module_name = f"test_{adapter_dir.removeprefix('.')}_run_reviewer"
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / adapter_dir / "run_reviewer.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)

    partial_stderr = b"partial-timeout-stderr\x00\xff\n"

    class FakeProcess:
        returncode = None
        calls = 0

        def communicate(
            self,
            input: bytes | None = None,
            timeout: int | None = None,
        ) -> tuple[bytes, bytes]:
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(
                    ["reviewer"],
                    timeout,
                    output=b"partial stdout is discarded",
                    stderr=partial_stderr,
                )
            return b"", b""

    fake_process = FakeProcess()
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda *args, **kwargs: fake_process,
    )
    monkeypatch.setattr(module, "_stop_process_group", lambda process: None)

    arguments: tuple[object, ...] = (
        (["reviewer"], b"prompt", 1, tmp_path, {})
        if adapter_dir == ".codex"
        else (["reviewer"], b"prompt", 1, tmp_path)
    )
    result = module.run_with_timeout(*arguments)

    assert result.returncode == 124
    assert result.stdout == b""
    assert result.stderr == partial_stderr
    assert module._merge_timeout_stderr(
        partial_stderr, partial_stderr + b"tail"
    ) == partial_stderr + b"tail"
    assert module._merge_timeout_stderr(b"prefix-overlap", b"overlap-tail") == (
        b"prefix-overlap-tail"
    )


@pytest.mark.parametrize(
    ("adapter_dir", "executable_name"),
    ((".claude", "claude"), (".codex", "codex")),
)
def test_m8_reviewer_wrapper_timeout_preserves_raw_stderr(
    tmp_path: Path,
    adapter_dir: str,
    executable_name: str,
) -> None:
    """RPL-05/R5-03: timeout停止後にpipeをdrainし、生stderrをAUD-09へ渡す。"""

    repo = make_isolated_config_repo(tmp_path)
    limits_path = repo / "data" / "config" / "limits.json"
    limits = load_json(limits_path)
    limits["review_timeout_seconds"] = 10
    write_json(limits_path, limits)
    set_dir, action = start_explicit_flow(repo)

    adapter = repo / adapter_dir
    adapter.mkdir()
    shutil.copy2(ROOT / adapter_dir / "run_reviewer.py", adapter / "run_reviewer.py")
    fake_bin = tmp_path / f"bin-timeout-{executable_name}"
    fake_bin.mkdir()
    fake_executable = fake_bin / executable_name
    fake_executable.write_text(
        r"""#!/bin/sh
trap '' TERM
printf 'timeout-stderr\000\377\n' >&2
touch "$FAKE_REVIEW_READY"
sleep 30
""",
        encoding="utf-8",
    )
    fake_executable.chmod(0o755)
    fake_home = tmp_path / f"home-timeout-{executable_name}"
    (fake_home / ".codex-cefrj-reviewer").mkdir(parents=True)
    raw_stderr = b"timeout-stderr\x00\xff\n"
    ready_path = tmp_path / f"ready-{executable_name}"

    def invoke_timeout_wrapper() -> subprocess.CompletedProcess[bytes]:
        return run_cli(
            f"{adapter_dir}/run_reviewer.py",
            "--request",
            action["request_path"],
            cwd=repo,
            env={
                "HOME": str(fake_home),
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                "FAKE_REVIEW_READY": str(ready_path),
            },
        )

    with ThreadPoolExecutor(max_workers=1) as executor:
        completed_future = executor.submit(invoke_timeout_wrapper)
        ready_deadline = time.monotonic() + 5
        while not ready_path.exists() and time.monotonic() < ready_deadline:
            time.sleep(0.01)
        assert ready_path.exists(), "reviewer child did not signal stderr readiness"
        completed = completed_future.result(timeout=15)
    assert completed.returncode == 0, completed.stderr.decode(errors="backslashreplace")
    assert json.loads(completed.stdout)["retry_number"] == 1
    invalid = load_json(set_dir / "review" / "q01.gen1.review.invalid1.txt")
    assert invalid["kind"] == "process_failure"
    assert invalid["exit_code"] == 124
    assert base64.b64decode(invalid["stderr_base64"]) == raw_stderr


@pytest.mark.parametrize(
    ("adapter_dir", "executable_name"),
    ((".claude", "claude"), (".codex", "codex")),
)
@pytest.mark.parametrize(
    ("config_variant", "expected_code"),
    (("snapshot_mismatch", "E-DATA-08"), ("schema_invalid", "E-DATA-05")),
)
def test_m8_reviewer_preflight_rejects_config_before_child_launch(
    tmp_path: Path,
    adapter_dir: str,
    executable_name: str,
    config_variant: str,
    expected_code: str,
) -> None:
    """RPL-05/R11-01: 設定不一致・不当を子起動前のC12 preflightで拒否する。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, action = start_explicit_flow(repo)
    candidate_path = set_dir / "review" / "q01.gen1.candidate.json"
    request_path = set_dir / "review" / "q01.gen1.request.json"
    original_candidate = candidate_path.read_bytes()
    original_request = request_path.read_bytes()

    limits_path = repo / "data" / "config" / "limits.json"
    limits = load_json(limits_path)
    if config_variant == "snapshot_mismatch":
        limits["review_timeout_seconds"] = 1
    else:
        limits["review_timeout_seconds"] = 10_000_000
        limits["set_question_max"] = 21
    write_json(limits_path, limits)

    adapter = repo / adapter_dir
    adapter.mkdir()
    shutil.copy2(ROOT / adapter_dir / "run_reviewer.py", adapter / "run_reviewer.py")
    fake_bin = tmp_path / f"bin-preflight-config-{executable_name}-{config_variant}"
    fake_bin.mkdir()
    fake_executable = fake_bin / executable_name
    fake_executable.write_text(
        "#!/bin/sh\n: > \"$FAKE_REVIEW_MARKER\"\nexit 0\n",
        encoding="utf-8",
    )
    fake_executable.chmod(0o755)
    fake_home = tmp_path / f"home-preflight-config-{executable_name}-{config_variant}"
    (fake_home / ".codex-cefrj-reviewer").mkdir(parents=True)
    marker = tmp_path / f"launched-{executable_name}-{config_variant}"

    completed = run_cli(
        f"{adapter_dir}/run_reviewer.py",
        "--request",
        action["request_path"],
        cwd=repo,
        env={
            "FAKE_REVIEW_MARKER": str(marker),
            "HOME": str(fake_home),
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        },
    )
    assert completed.returncode == 1
    assert stderr_json(completed)["error_code"] == expected_code
    assert not marker.exists()
    assert not (set_dir / ".staging" / "flow-state.json").exists()
    assert candidate_path.read_bytes() == original_candidate
    assert request_path.read_bytes() == original_request


@pytest.mark.parametrize(
    ("adapter_dir", "executable_name"),
    ((".claude", "claude"), (".codex", "codex")),
)
@pytest.mark.parametrize(
    "request_variant",
    ("invalid_schema", "candidate", "machine_report", "constraints_snapshot"),
)
def test_m8_reviewer_preflight_rejects_tampered_request_before_child_launch(
    tmp_path: Path,
    adapter_dir: str,
    executable_name: str,
    request_variant: str,
) -> None:
    """RPL-05/R12-01: 改変requestをC12で再検証・再構築照合して起動前拒否する。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, action = start_explicit_flow(repo)
    candidate_path = set_dir / "review" / "q01.gen1.candidate.json"
    machine_path = set_dir / "review" / "q01.gen1.machine.json"
    request_path = repo / action["request_path"]
    original_candidate = candidate_path.read_bytes()
    original_machine = machine_path.read_bytes()

    if request_variant == "invalid_schema":
        tampered_request: dict[str, object] = {}
    else:
        tampered_request = load_json(request_path)
        if request_variant == "candidate":
            tampered_request["candidate"]["body"]["gloss"] = "改変された語義"
        elif request_variant == "machine_report":
            tampered_request["machine_report"]["generated_at"] = (
                "2099-01-01T00:00:00Z"
            )
        else:
            tampered_request["constraints_snapshot"]["limits"][
                "sentence_word_limit"
            ] += 1
    write_json(request_path, tampered_request)
    tampered_bytes = request_path.read_bytes()

    adapter = repo / adapter_dir
    adapter.mkdir()
    shutil.copy2(ROOT / adapter_dir / "run_reviewer.py", adapter / "run_reviewer.py")
    fake_bin = tmp_path / f"bin-preflight-request-{executable_name}-{request_variant}"
    fake_bin.mkdir()
    fake_executable = fake_bin / executable_name
    fake_executable.write_text(
        "#!/bin/sh\n: > \"$FAKE_REVIEW_MARKER\"\nexit 0\n",
        encoding="utf-8",
    )
    fake_executable.chmod(0o755)
    fake_home = tmp_path / f"home-preflight-request-{executable_name}-{request_variant}"
    (fake_home / ".codex-cefrj-reviewer").mkdir(parents=True)
    marker = tmp_path / f"launched-request-{executable_name}-{request_variant}"

    completed = run_cli(
        f"{adapter_dir}/run_reviewer.py",
        "--request",
        action["request_path"],
        cwd=repo,
        env={
            "FAKE_REVIEW_MARKER": str(marker),
            "HOME": str(fake_home),
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        },
    )
    assert completed.returncode == 1
    error = stderr_json(completed)
    assert error["error_code"] == "E-CONTRACT-01"
    assert completed.stderr == canonical_bytes(error)
    assert not marker.exists()
    assert not (set_dir / ".staging" / "flow-state.json").exists()
    assert candidate_path.read_bytes() == original_candidate
    assert machine_path.read_bytes() == original_machine
    assert request_path.read_bytes() == tampered_bytes


def test_m8_review_preflight_cli_help_required_arguments_and_success(
    tmp_path: Path,
) -> None:
    """CI-CLI-01/R13-01: preflightのhelp・必須引数・正常2フィールドを固定する。"""

    help_result = run_cli("scripts/flow_control.py", "--help")
    assert help_result.returncode == 0
    assert b"review-preflight" in help_result.stdout

    missing_arguments = run_cli("scripts/flow_control.py", "review-preflight")
    assert missing_arguments.returncode == 1
    assert stderr_json(missing_arguments)["error_code"] == "E-INPUT-01"

    repo = make_isolated_config_repo(tmp_path)
    set_dir, action = start_explicit_flow(repo)
    completed = run_cli(
        "scripts/flow_control.py",
        "review-preflight",
        "--set-dir",
        f"output/{SET_ID}",
        "--request",
        action["request_path"],
        cwd=repo,
    )
    assert completed.returncode == 0, completed.stderr.decode()
    assert json.loads(completed.stdout) == {
        "request_path": action["request_path"],
        "review_timeout_seconds": load_json(
            repo / "data" / "config" / "limits.json"
        )["review_timeout_seconds"],
    }
    assert (set_dir / ".staging" / "flow-state.json").is_file()


@pytest.mark.parametrize(
    ("failure_variant", "expected_code"),
    (("missing_request", "E-CONTRACT-03"), ("action_mismatch", "E-CONTRACT-01")),
)
def test_m8_review_preflight_cli_rejects_missing_or_mismatched_request(
    tmp_path: Path, failure_variant: str, expected_code: str,
) -> None:
    """CI-CLI-01/R13-01: request欠落・直前action不一致を監査保持で停止する。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, action = start_explicit_flow(repo)
    candidate_path = set_dir / "review" / "q01.gen1.candidate.json"
    machine_path = set_dir / "review" / "q01.gen1.machine.json"
    original_candidate = candidate_path.read_bytes()
    original_machine = machine_path.read_bytes()
    request_argument = action["request_path"]
    if failure_variant == "missing_request":
        (repo / request_argument).unlink()
    else:
        request_argument = request_argument.replace("q01.gen1", "q02.gen1")

    completed = run_cli(
        "scripts/flow_control.py",
        "review-preflight",
        "--set-dir",
        f"output/{SET_ID}",
        "--request",
        request_argument,
        cwd=repo,
    )
    assert completed.returncode == 1
    assert stderr_json(completed)["error_code"] == expected_code
    assert not (set_dir / ".staging" / "flow-state.json").exists()
    assert candidate_path.read_bytes() == original_candidate
    assert machine_path.read_bytes() == original_machine


@pytest.mark.parametrize("work_file_mode", ("missing", "empty", "directory", "symlink"))
def test_m8_codex_wrapper_preserves_real_process_failure_for_bad_work_file(
    tmp_path: Path, work_file_mode: str,
) -> None:
    """RPL-05/R4-03: Codex作業ファイル不成立でも生stderrをAUD-09へ渡す。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, action = start_explicit_flow(repo)
    adapter = repo / ".codex"
    adapter.mkdir()
    shutil.copy2(ROOT / ".codex" / "run_reviewer.py", adapter / "run_reviewer.py")
    fake_bin = tmp_path / "bin-codex-work-file"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        """#!/usr/bin/env python3
import os
import sys
from pathlib import Path

output = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
mode = os.environ["FAKE_WORK_FILE_MODE"]
if mode == "empty":
    output.touch()
elif mode == "directory":
    output.mkdir()
elif mode == "symlink":
    target = output.with_name(output.name + ".target")
    target.write_bytes(b"untrusted target")
    output.symlink_to(target)
sys.stderr.buffer.write(bytes.fromhex(os.environ["FAKE_REVIEW_STDERR_HEX"]))
""",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    fake_home = tmp_path / "home-codex-work-file"
    (fake_home / ".codex-cefrj-reviewer").mkdir(parents=True)
    raw_stderr = b"raw-codex-stderr\x00\x01\n"
    completed = run_cli(
        ".codex/run_reviewer.py",
        "--request",
        action["request_path"],
        cwd=repo,
        env={
            "FAKE_REVIEW_STDERR_HEX": raw_stderr.hex(),
            "FAKE_WORK_FILE_MODE": work_file_mode,
            "HOME": str(fake_home),
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        },
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="backslashreplace")
    assert json.loads(completed.stdout)["action"] == "run_review"
    invalid = load_json(set_dir / "review" / "q01.gen1.review.invalid1.txt")
    assert invalid["kind"] == "process_failure"
    assert invalid["exit_code"] == 0
    assert base64.b64decode(invalid["stderr_base64"]) == raw_stderr


@pytest.mark.parametrize(
    ("adapter_dir", "executable_name"),
    ((".claude", "claude"), (".codex", "codex")),
)
@pytest.mark.parametrize("launch_mode", ("missing_command", "popen_failure"))
def test_m8_reviewer_prelaunch_failure_is_audited_and_converges(
    tmp_path: Path,
    adapter_dir: str,
    executable_name: str,
    launch_mode: str,
) -> None:
    """RPL-05/R6-02: コマンド欠落・Popen失敗もC12で3回監査して中止する。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, action = start_explicit_flow(repo)
    adapter = repo / adapter_dir
    adapter.mkdir()
    shutil.copy2(ROOT / adapter_dir / "run_reviewer.py", adapter / "run_reviewer.py")
    fake_bin = tmp_path / f"bin-prelaunch-{executable_name}-{launch_mode}"
    fake_bin.mkdir()
    if launch_mode == "popen_failure":
        fake_executable = fake_bin / executable_name
        fake_executable.write_text("#!/definitely/missing/interpreter\n", encoding="utf-8")
        fake_executable.chmod(0o755)
    fake_home = tmp_path / f"home-prelaunch-{executable_name}-{launch_mode}"
    (fake_home / ".codex-cefrj-reviewer").mkdir(parents=True)
    for attempt in range(1, 4):
        completed = run_cli(
            f"{adapter_dir}/run_reviewer.py",
            "--request",
            action["request_path"],
            cwd=repo,
            env={"HOME": str(fake_home), "PATH": str(fake_bin)},
        )
        assert completed.returncode == 0, completed.stderr.decode(
            errors="backslashreplace"
        )
        action = json.loads(completed.stdout)
        invalid = load_json(
            set_dir / "review" / f"q01.gen1.review.invalid{attempt}.txt"
        )
        assert invalid["kind"] == "process_failure"
        assert invalid["exit_code"] == 70
        assert base64.b64decode(invalid["stderr_base64"])
        if attempt < 3:
            assert action["action"] == "run_review"
            assert action["retry_number"] == attempt
            assert (set_dir / ".staging" / "flow-state.json").is_file()
        else:
            assert action["action"] == "aborted"
            assert action["reason"] == "review_invalid"
            assert not (set_dir / ".staging" / "flow-state.json").exists()


def test_m8_codex_prelaunch_work_directory_is_audited_and_converges(
    tmp_path: Path,
) -> None:
    """RPL-05/R6-02: 起動前codex-last directoryもC12を迂回しない。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, action = start_explicit_flow(repo)
    adapter = repo / ".codex"
    adapter.mkdir()
    shutil.copy2(ROOT / ".codex" / "run_reviewer.py", adapter / "run_reviewer.py")
    fake_bin = tmp_path / "bin-prelaunch-codex-directory"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_codex.chmod(0o755)
    fake_home = tmp_path / "home-prelaunch-codex-directory"
    (fake_home / ".codex-cefrj-reviewer").mkdir(parents=True)
    request_path = repo / action["request_path"]
    work_path = request_path.with_name(
        request_path.name.removesuffix(".request.json") + ".codex-last.txt"
    )
    work_path.mkdir()
    for attempt in range(1, 4):
        completed = run_cli(
            ".codex/run_reviewer.py",
            "--request",
            action["request_path"],
            cwd=repo,
            env={
                "HOME": str(fake_home),
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            },
        )
        assert completed.returncode == 0, completed.stderr.decode(
            errors="backslashreplace"
        )
        action = json.loads(completed.stdout)
        invalid = load_json(
            set_dir / "review" / f"q01.gen1.review.invalid{attempt}.txt"
        )
        assert invalid["kind"] == "process_failure"
        assert invalid["exit_code"] == 70
        assert "ディレクトリ".encode() in base64.b64decode(invalid["stderr_base64"])
    assert action["action"] == "aborted"
    assert work_path.is_dir()
    assert not (set_dir / ".staging" / "flow-state.json").exists()


def test_m8_flow_preflight_failure_removes_state_and_preserves_audits(
    tmp_path: Path,
) -> None:
    """CI-CLI-01/R4-01: S80中の共通事前検査E-ENV-04も再開不能にする。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, _action = start_explicit_flow(repo)
    candidate_path = set_dir / "review" / "q01.gen1.candidate.json"
    original_candidate = candidate_path.read_bytes()
    (repo / "schemas").unlink()
    completed = run_cli(
        "scripts/flow_control.py",
        "status",
        "--set-dir",
        f"output/{SET_ID}",
        cwd=repo,
    )
    assert completed.returncode == 1
    assert stderr_json(completed)["error_code"] == "E-ENV-04"
    assert candidate_path.read_bytes() == original_candidate
    assert not (set_dir / ".staging" / "flow-state.json").exists()

    repeated = run_cli(
        "scripts/flow_control.py",
        "status",
        "--set-dir",
        f"output/{SET_ID}",
        cwd=repo,
    )
    assert repeated.returncode == 1
    assert stderr_json(repeated)["error_code"] == "E-CONTRACT-03"


@pytest.mark.parametrize("variant", ("limits", "proper_nouns"))
def test_m8_flow_config_snapshot_mismatch_aborts_and_preserves_audits(
    tmp_path: Path, variant: str,
) -> None:
    """CI-CLI-01: 設定snapshot不一致を監査保持のまま中止する。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, _action = start_explicit_flow(repo)
    if variant == "limits":
        config_path = repo / "data" / "config" / "limits.json"
        config = load_json(config_path)
        config["set_question_max"] -= 1
        expected_path = "data/config/limits.json"
    else:
        config_path = repo / "data" / "config" / "proper_nouns.json"
        config = load_json(config_path)
        config["words"].append("Testville")
        expected_path = "data/config/proper_nouns.json"
    write_json(config_path, config)

    completed = run_cli(
        "scripts/flow_control.py",
        "status",
        "--set-dir",
        f"output/{SET_ID}",
        cwd=repo,
    )
    assert completed.returncode == 1
    error = stderr_json(completed)
    assert error["error_code"] == "E-DATA-08"
    assert expected_path in error["detail"]["differences"]
    assert not (set_dir / ".staging" / "flow-state.json").exists()
    assert (set_dir / "review" / "q01.gen1.candidate.json").is_file()


@pytest.mark.parametrize(
    "fixture_name",
    (
        "cli05_e_data_08.json",
        "cli05_e_contract_03.json",
        "cli05_e_contract_04.json",
    ),
)
def test_m8_flow_propagates_structured_child_cli_failure(fixture_name: str) -> None:
    """CI-CLI-01: 子CLIの定義済みCLI-05エラーを非改変で伝播する。"""

    error = load_json(FIXTURES / "cli" / fixture_name)
    completed = subprocess.CompletedProcess(
        args=["child"], returncode=1, stdout=b"", stderr=json.dumps(error).encode()
    )
    with pytest.raises(CliFailure) as caught:
        require_child_success(completed, "E-CONTRACT-01")
    assert caught.value.as_dict() == error


def test_m8_flow_parses_cli05_from_final_stderr_document() -> None:
    """CI-CLI-01/R5-04: 末尾CLI-05だけを定義済み子エラーとして伝播する。"""

    error = load_json(FIXTURES / "cli" / "cli05_e_data_08.json")
    completed = subprocess.CompletedProcess(
        args=["child"],
        returncode=1,
        stdout=b"",
        stderr=b"diagnostic prelude\n" + canonical_bytes(error) + b"\n",
    )
    with pytest.raises(CliFailure) as caught:
        require_child_success(completed, "E-CONTRACT-01")
    assert caught.value.as_dict() == error


@pytest.mark.parametrize(
    "fixture_name",
    (
        "invalid_cli05_unknown_code.json",
        "invalid_cli05_code_type.json",
        "invalid_cli05_missing.json",
    ),
)
def test_m8_flow_rejects_unknown_or_malformed_final_cli_error(fixture_name: str) -> None:
    """CI-CLI-01/R5-04: 未知コード・CLI-05不完全形は内部失敗として扱う。"""

    stderr = (FIXTURES / "cli" / fixture_name).read_bytes()
    completed = subprocess.CompletedProcess(
        args=["child"], returncode=1, stdout=b"", stderr=stderr
    )
    with pytest.raises(RuntimeError):
        require_child_success(completed, "E-CONTRACT-01")


@pytest.mark.parametrize(
    "completed",
    (
        subprocess.CompletedProcess(
            args=["child"], returncode=1, stdout=b"", stderr=b"not-cli05"
        ),
        subprocess.CompletedProcess(
            args=["child"], returncode=2, stdout=b"", stderr=b"internal traceback"
        ),
    ),
)
def test_m8_flow_abnormal_child_exit_is_internal(
    completed: subprocess.CompletedProcess[bytes],
) -> None:
    """CI-CLI-01/R4-02: CLI-05完全形以外の子失敗を契約違反へ変換しない。"""

    with pytest.raises(RuntimeError):
        require_child_success(completed, "E-CONTRACT-01")


@pytest.mark.parametrize(
    "boundary",
    ("machine", "incremental_set", "final_set", "finalize", "final_validate"),
)
def test_m8_flow_child_internal_error_cleans_state_at_every_call_site(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    """CI-CLI-01/R4-02: 全子CLI呼出しの終了2を内部例外として終端する。"""

    repo = make_isolated_config_repo(tmp_path)
    if boundary == "machine":
        set_dir, _action = initialize_explicit_flow(repo)
        arguments = [
            "candidate",
            "--set-dir",
            f"output/{SET_ID}",
            "--file",
            str(FIXTURES / "candidates" / "replay_q01_pass.json"),
        ]
    else:
        set_dir, _action = start_explicit_flow(repo)
        arguments = [
            "review",
            "--set-dir",
            f"output/{SET_ID}",
            "--file",
            str(FIXTURES / "reviews" / "pass_q01_gen1.json"),
        ]
    original_run_child = flow_control_module.run_child
    set_check_calls = 0

    def injected_run_child(
        repo_root: Path,
        script_name: str,
        *child_arguments: str,
        stdin: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        nonlocal set_check_calls
        should_fail = boundary == "machine" and script_name == "machine_check.py"
        if script_name == "set_check.py":
            set_check_calls += 1
            should_fail = should_fail or (
                boundary == "incremental_set" and set_check_calls == 1
            ) or (boundary == "final_set" and set_check_calls == 2)
        should_fail = should_fail or (
            boundary == "finalize" and script_name == "finalize_set.py"
        ) or (
            boundary == "final_validate"
            and script_name == "validate.py"
            and "--set-dir" in child_arguments
        )
        if should_fail:
            return subprocess.CompletedProcess(
                args=[script_name], returncode=2, stdout=b"", stderr=b"internal traceback"
            )
        return original_run_child(
            repo_root, script_name, *child_arguments, stdin=stdin
        )

    monkeypatch.setattr(flow_control_module, "run_child", injected_run_child)
    monkeypatch.chdir(repo)
    assert flow_control_module.main(arguments) == 2
    assert not (set_dir / ".staging" / "flow-state.json").exists()
    assert (set_dir / "review" / "q01.gen1.candidate.json").is_file()
    if boundary != "machine":
        assert (set_dir / "review" / "q01.gen1.review.json").is_file()


def test_m8_flow_defined_error_removes_state_and_preserves_collision(
    tmp_path: Path,
) -> None:
    """CI-SET-04/R3-03: E-DATA-07停止後は監査と衝突対象を保持する。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, _action = start_explicit_flow(repo)
    collision = set_dir / "review" / "q01.gen1.review.json"
    original = b"pre-existing collision bytes\n"
    collision.write_bytes(original)
    completed = run_cli(
        "scripts/flow_control.py",
        "review",
        "--set-dir",
        f"output/{SET_ID}",
        "--file",
        str(FIXTURES / "reviews" / "pass_q01_gen1.json"),
        cwd=repo,
    )
    assert completed.returncode == 1
    assert stderr_json(completed)["error_code"] == "E-DATA-07"
    assert collision.read_bytes() == original
    assert (set_dir / "review" / "q01.gen1.candidate.json").is_file()
    assert (set_dir / "review" / "q01.gen1.request.json").is_file()
    assert not (set_dir / ".staging" / "flow-state.json").exists()


@pytest.mark.parametrize("boundary", ("candidate", "review"))
@pytest.mark.parametrize("failure_kind", ("defined", "internal"))
def test_m8_validate_external_classifies_child_failures_and_cleans_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    failure_kind: str,
) -> None:
    """RPL-05/R3-06: provider不当以外の終了1と終了2を試行失敗へ読み替えない。"""

    repo = make_isolated_config_repo(tmp_path)
    if boundary == "candidate":
        set_dir, _action = initialize_explicit_flow(repo)
        arguments = [
            "candidate",
            "--set-dir",
            f"output/{SET_ID}",
            "--file",
            str(FIXTURES / "candidates" / "replay_q01_pass.json"),
        ]
    else:
        set_dir, _action = start_explicit_flow(repo)
        arguments = [
            "review",
            "--set-dir",
            f"output/{SET_ID}",
            "--file",
            str(FIXTURES / "reviews" / "pass_q01_gen1.json"),
        ]
    if failure_kind == "defined":
        error = load_json(FIXTURES / "cli" / "cli05_e_env_04.json")
        injected = subprocess.CompletedProcess(
            args=["validate.py"],
            returncode=1,
            stdout=b"",
            stderr=json.dumps(error).encode("utf-8"),
        )
        expected_exception = CliFailure
    else:
        injected = subprocess.CompletedProcess(
            args=["validate.py"],
            returncode=2,
            stdout=b"",
            stderr=b"internal traceback",
        )
        expected_exception = RuntimeError
    monkeypatch.setattr(flow_control_module, "run_child", lambda *_args, **_kwargs: injected)
    monkeypatch.chdir(repo)
    with pytest.raises(expected_exception) as caught:
        flow_control_module.run(arguments)
    if failure_kind == "defined":
        assert caught.value.as_dict() == error
    assert not (set_dir / ".staging" / "flow-state.json").exists()
    assert not list((set_dir / "review").glob("*.invalid*.txt"))


def test_m8_validate_external_accepts_only_provider_attributable_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RPL-05/R3-06: E-CONTRACT-01/E-INPUT-03だけをinvalid監査へ変換する。"""

    payload = b"not-json"
    for fixture_name in ("cli05_e_contract_01.json", "cli05_e_input_03.json"):
        error = load_json(FIXTURES / "cli" / fixture_name)
        injected = subprocess.CompletedProcess(
            args=["validate.py"],
            returncode=1,
            stdout=b"",
            stderr=json.dumps(error).encode("utf-8"),
        )
        monkeypatch.setattr(
            flow_control_module, "run_child", lambda *_args, **_kwargs: injected
        )
        value, diagnostic, invalid = validate_external(ROOT, "candidate", "-", payload)
        assert value is None
        assert diagnostic == error["message"]
        assert invalid["kind"] == "validation_failure"
        assert base64.b64decode(invalid["raw_output_base64"]) == payload


@pytest.mark.parametrize("boundary", ("candidate", "review"))
def test_m8_empty_provider_output_is_audited_and_retry_recovers(
    tmp_path: Path,
    boundary: str,
) -> None:
    """RPL-05/RPL-06/R5-01: 空出力を監査し、次の同一境界試行で回復する。"""

    repo = make_isolated_config_repo(tmp_path)
    empty_path = repo / f"empty-{boundary}.json"
    empty_path.write_bytes(b"")
    if boundary == "candidate":
        set_dir, _action = initialize_explicit_flow(repo)
        action = flow_cli(
            repo,
            "candidate",
            "--set-dir",
            f"output/{SET_ID}",
            "--file",
            str(empty_path),
        )
        invalid_path = set_dir / "review" / "q01.gen1.candidate.invalid1.txt"
    else:
        set_dir, _action = start_explicit_flow(repo)
        action = flow_cli(
            repo,
            "review",
            "--set-dir",
            f"output/{SET_ID}",
            "--file",
            str(empty_path),
        )
        invalid_path = set_dir / "review" / "q01.gen1.review.invalid1.txt"

    assert action["action"] == ("generate_candidate" if boundary == "candidate" else "run_review")
    invalid = load_json(invalid_path)
    assert invalid == load_json(FIXTURES / "cli" / "audit_process_failure_empty.json")

    if boundary == "candidate":
        action = flow_cli(
            repo,
            "candidate",
            "--set-dir",
            f"output/{SET_ID}",
            "--file",
            str(FIXTURES / "candidates" / "replay_q01_pass.json"),
        )
        assert action["action"] == "run_review"
    action = flow_cli(
        repo,
        "review",
        "--set-dir",
        f"output/{SET_ID}",
        "--file",
        str(FIXTURES / "reviews" / "pass_q01_gen1.json"),
    )
    assert action["action"] == "completed"


def test_m8_candidate_raw_is_preserved_when_canonical_audit_collides(
    tmp_path: Path,
) -> None:
    """RPL-06/R4-04: 正準candidate監査の排他保存前にrawを削除しない。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, _action = initialize_explicit_flow(repo)
    raw_path = set_dir / ".staging" / "q01.gen1.candidate.raw1.json"
    raw_path.write_bytes(
        (FIXTURES / "candidates" / "replay_q01_pass.json").read_bytes()
    )
    collision = set_dir / "review" / "q01.gen1.candidate.json"
    collision_bytes = b"pre-existing candidate collision\n"
    collision.write_bytes(collision_bytes)
    completed = run_cli(
        "scripts/flow_control.py",
        "candidate",
        "--set-dir",
        f"output/{SET_ID}",
        "--file",
        str(raw_path),
        cwd=repo,
    )
    assert completed.returncode == 1
    assert stderr_json(completed)["error_code"] == "E-DATA-07"
    assert collision.read_bytes() == collision_bytes
    assert raw_path.is_file()
    assert not (set_dir / ".staging" / "flow-state.json").exists()


@pytest.mark.parametrize("failure_kind", ("defined", "internal"))
def test_m8_candidate_raw_is_preserved_when_validation_cannot_be_audited(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    """RPL-06/R4-04: validateの環境エラー・終了2では監査前rawを保持する。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, _action = initialize_explicit_flow(repo)
    raw_path = set_dir / ".staging" / "q01.gen1.candidate.raw1.json"
    raw_path.write_bytes(
        (FIXTURES / "candidates" / "replay_q01_pass.json").read_bytes()
    )
    if failure_kind == "defined":
        error = load_json(FIXTURES / "cli" / "cli05_e_env_04.json")
        injected = subprocess.CompletedProcess(
            args=["validate.py"],
            returncode=1,
            stdout=b"",
            stderr=json.dumps(error).encode("utf-8"),
        )
        expected_exception = CliFailure
    else:
        injected = subprocess.CompletedProcess(
            args=["validate.py"],
            returncode=2,
            stdout=b"",
            stderr=b"internal traceback",
        )
        expected_exception = RuntimeError
    monkeypatch.setattr(flow_control_module, "run_child", lambda *_args, **_kwargs: injected)
    monkeypatch.chdir(repo)
    with pytest.raises(expected_exception):
        flow_control_module.run(
            [
                "candidate",
                "--set-dir",
                f"output/{SET_ID}",
                "--file",
                str(raw_path),
            ]
        )
    assert raw_path.is_file()
    assert not list((set_dir / "review").glob("q01.gen1.candidate*"))
    assert not (set_dir / ".staging" / "flow-state.json").exists()


def test_m8_candidate_raw_cleanup_runs_only_after_canonical_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RPL-06/R4-04: raw削除失敗時にも保存済みcandidate監査を保持する。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, _action = initialize_explicit_flow(repo)
    raw_path = set_dir / ".staging" / "q01.gen1.candidate.raw1.json"
    raw_path.write_bytes(
        (FIXTURES / "candidates" / "replay_q01_pass.json").read_bytes()
    )

    def fail_cleanup(_input_path: str, _set_dir: Path) -> None:
        raise CliFailure(
            "E-ENV-05",
            "E-ENV-05 candidate一時入力を削除できません",
            detail={"path": str(raw_path)},
            remedy="権限を確認してください。",
        )

    monkeypatch.setattr(
        flow_control_module, "cleanup_candidate_provider_input", fail_cleanup
    )
    monkeypatch.chdir(repo)
    with pytest.raises(CliFailure) as caught:
        flow_control_module.run(
            [
                "candidate",
                "--set-dir",
                f"output/{SET_ID}",
                "--file",
                str(raw_path),
            ]
        )
    assert caught.value.error_code == "E-ENV-05"
    assert (set_dir / "review" / "q01.gen1.candidate.json").is_file()
    assert raw_path.is_file()
    assert not (set_dir / ".staging" / "flow-state.json").exists()


def test_m8_final_set_check_failure_returns_cli05_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CI-SET-04/RPL-08/R3-02: 最終set_check failをCLI-05完全形で終端する。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, _action = start_explicit_flow(repo)
    state = load_json(set_dir / ".staging" / "flow-state.json")
    state["accepted_slots"] = {"q01": "q01"}
    report = load_json(FIXTURES / "machine" / "set_check_failure.json")
    monkeypatch.setattr(
        flow_control_module,
        "run_child",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["set_check.py"],
            returncode=0,
            stdout=canonical_bytes(report),
            stderr=b"",
        ),
    )
    action = finalize_flow(repo, set_dir, state)
    assert action["action"] == "aborted"
    assert action["reason"] == "final_set_check"
    assert action["error"]["error_code"] == "E-CONTRACT-04"
    assert action["error"]["message"]
    assert action["error"]["remedy"]
    assert action["error"]["detail"]["set_check_violations"] == report["violations"]


def test_m8_finalize_warning_is_preserved_in_completed_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CI-SET-04/R3-04: W-CLEANUP-01を非改変でcompleted actionへ含める。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, _action = start_explicit_flow(repo)
    state = load_json(set_dir / ".staging" / "flow-state.json")
    state["accepted_slots"] = {"q01": "q01"}
    report = load_json(set_dir / "review" / "q01.gen1.machine.json")
    warning = load_json(FIXTURES / "cli" / "cleanup_warning.json")
    finalize_stdout = (
        FIXTURES / "cli" / "finalize_success.json"
    ).read_bytes()
    validate_stdout = (
        FIXTURES / "cli" / "validate_set_success.json"
    ).read_bytes()
    children = iter(
        (
            subprocess.CompletedProcess(
                args=["set_check.py"], returncode=0, stdout=canonical_bytes(report), stderr=b""
            ),
            subprocess.CompletedProcess(
                args=["finalize_set.py"], returncode=0, stdout=finalize_stdout, stderr=canonical_bytes(warning)
            ),
            subprocess.CompletedProcess(
                args=["validate.py"], returncode=0, stdout=validate_stdout, stderr=b""
            ),
        )
    )
    monkeypatch.setattr(
        flow_control_module, "run_child", lambda *_args, **_kwargs: next(children)
    )
    action = finalize_flow(repo, set_dir, state)
    assert action["action"] == "completed"
    for key, value in warning.items():
        assert action[key] == value
    completed = subprocess.CompletedProcess(
        args=["finalize_set.py"], returncode=0, stdout=finalize_stdout, stderr=canonical_bytes(warning)
    )
    assert finalized_warning(completed, repo, set_dir) == warning


def test_m8_flow_semantic_review_failure_retries_without_canonical_audit(
    tmp_path: Path,
) -> None:
    """RPL-05: 意味契約違反reviewを正準保存せず同一世代で再実行する。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, _action = start_explicit_flow(repo)
    review = load_json(FIXTURES / "reviews" / "pass_q01_gen1.json")
    review["checks"][0]["note"] = "誤って適用扱いにした意味不正fixtureです。"
    review["checks"][0]["result"] = "pass"
    review_path = repo / "semantic-invalid-review.json"
    write_json(review_path, review)

    for attempt in range(1, 4):
        action = flow_cli(
            repo,
            "review",
            "--set-dir",
            f"output/{SET_ID}",
            "--file",
            str(review_path),
        )
        assert (
            action["action"] == "run_review" if attempt < 3 else action["action"] == "aborted"
        )
    review_dir = set_dir / "review"
    assert not (review_dir / "q01.gen1.review.json").exists()
    assert len(list(review_dir.glob("q01.gen1.review.invalid*.txt"))) == 3
    assert action["reason"] == "review_invalid"
    assert set(action["error"]) == {"detail", "error_code", "message", "remedy"}
    assert action["error"]["error_code"] == "E-CONTRACT-01"
    assert action["error"]["remedy"]
    assert action["error"]["detail"]["schema"] == "review_result"
    assert not (set_dir / ".staging" / "flow-state.json").exists()


def test_m8_flow_process_failure_three_times_returns_cli05_abort(
    tmp_path: Path,
) -> None:
    """RPL-05/R3-02: process_failure 3回でE-CONTRACT-01完全形を返す。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, _action = start_explicit_flow(repo)
    for attempt in range(1, 4):
        completed = run_cli(
            "scripts/flow_control.py",
            "review",
            "--set-dir",
            f"output/{SET_ID}",
            "--process-failure",
            "70",
            stdin=f"reviewer failure {attempt}".encode(),
            cwd=repo,
        )
        assert completed.returncode == 0, completed.stderr.decode()
        action = json.loads(completed.stdout)
    assert action["action"] == "aborted"
    assert action["reason"] == "review_invalid"
    assert action["error"]["error_code"] == "E-CONTRACT-01"
    assert action["error"]["message"]
    assert action["error"]["remedy"]
    assert len(action["error"]["detail"]["invalid_audits"]) == 3
    assert not (set_dir / ".staging" / "flow-state.json").exists()


def test_m8_flow_review_semantics_cover_fail_mapping_and_level_null_rules() -> None:
    """RPL-05: reviewのfail対応・レベルnull・dispute参照意味契約を検査する。"""

    candidate = load_json(FIXTURES / "candidates" / "replay_q01_pass.json")
    review = load_json(FIXTURES / "reviews" / "fail_q01_gen1.json")
    review["violations"][0]["expected_level"] = None
    problems = review_semantic_problems(review, candidate, None)
    assert any("CHK-03のレベル値がnull" in problem for problem in problems)

    review = load_json(FIXTURES / "reviews" / "fail_q01_gen1.json")
    review["checks"][2]["result"] = "pass"
    review["verdict"] = "pass"
    problems = review_semantic_problems(review, candidate, None)
    assert any("violationがありますがcheck結果がfailではありません" in problem for problem in problems)

    review = load_json(FIXTURES / "reviews" / "fail_q01_gen1.json")
    review["checks"][2]["result"] = "pass"
    review["checks"][10]["result"] = "fail"
    review["violations"][0]["code"] = "CHK-11"
    problems = review_semantic_problems(review, candidate, None)
    assert any("非レベル違反でレベル値がnullではありません" in problem for problem in problems)

    dispute = load_json(FIXTURES / "cli" / "machine_dispute_measurement.json")
    review = load_json(FIXTURES / "reviews" / "pass_q01_gen1.json")
    review["machine_check_disputes"] = [dispute]
    completed = machine_for_path(
        FIXTURES / "candidates" / "mch_06_high_level_abandon.json",
        SET_ID,
        expected_level="A1",
    )
    assert completed.returncode == 0, completed.stderr.decode()
    machine = json.loads(completed.stdout)
    assert not review_semantic_problems(review, candidate, None, machine)
    for code, location in (
        ("V-LEN-01", dispute["location"]),
        ("V-LEX-02", "body.example.en token 3"),
    ):
        invalid_review = json.loads(json.dumps(review))
        invalid_review["machine_check_disputes"][0]["machine_violation_code"] = code
        invalid_review["machine_check_disputes"][0]["location"] = location
        problems = review_semantic_problems(invalid_review, candidate, None, machine)
        assert any("machine_report.violations[]に存在しません" in item for item in problems)
    assert any(
        "machine_report.violations[]に存在しません" in item
        for item in review_semantic_problems(
            review,
            candidate,
            None,
            load_json(FIXTURES / "machine" / "valid_question.json"),
        )
    )


def chk03_review_for_candidate(
    candidate: dict[str, object], expected_level: str, actual_level: str
) -> dict[str, object]:
    review = load_json(FIXTURES / "reviews" / "pass_q01_gen1.json")
    failure_template = load_json(FIXTURES / "reviews" / "fail_q01_gen1.json")
    for check in review["checks"]:
        check_id = check["check_id"]
        reason = flow_control_module.expected_not_applicable_reason(
            check_id, candidate, None
        )
        check["result"] = "not_applicable" if reason else "pass"
        check["note"] = reason or "テスト用記録で適用項目を確認しました。"
    review["checks"][2] = failure_template["checks"][2]
    field, span = flow_control_module.chk03_candidate_texts(candidate)[0]
    evidence = f"reviewer_estimate: {span} の構造を{actual_level}と推定しました。"
    review["sentence_grammar_inventory"] = [
        failure_template["sentence_grammar_inventory"][-1]
    ]
    inventory = review["sentence_grammar_inventory"][0]
    inventory["evidence"] = evidence
    inventory["level"] = actual_level
    inventory["span"] = span
    inventory["structure"] = "テスト用上限超過構造"
    review["verdict"] = "fail"
    review["violations"] = failure_template["violations"]
    violation = review["violations"][0]
    violation["actual_level"] = actual_level
    violation["evidence"] = evidence
    violation["expected_level"] = expected_level
    violation["location"] = f"{field}: {json.dumps(span, ensure_ascii=False)}"
    return review


@pytest.mark.parametrize(
    ("candidate_file", "expected_level", "actual_level"),
    (
        ("replay_q01_pass.json", "A2.2", "B1.1"),
        ("official_grammar_cloze.json", "A1.2", "A1.3"),
    ),
)
def test_m8_chk03_semantics_accept_real_excess_for_vocab_and_grammar_limits(
    candidate_file: str, expected_level: str, actual_level: str,
) -> None:
    """RPL-05/R4-05: 語彙ceilingと文法指定値をL_ctxとして照合する。"""

    candidate = load_json(FIXTURES / "candidates" / candidate_file)
    review = chk03_review_for_candidate(candidate, expected_level, actual_level)
    assert not review_semantic_problems(review, candidate, None)


@pytest.mark.parametrize(
    "variant",
    (
        "wrong_expected",
        "coarse_expected",
        "equal_actual",
        "coarse_actual",
        "missing_inventory",
        "bad_span",
        "missing_source",
    ),
)
def test_m8_chk03_semantics_reject_inconsistent_level_claims(variant: str) -> None:
    """RPL-05/R4-05: L_ctx不一致・非超過・scale混在をINF再実行対象にする。"""

    candidate = load_json(FIXTURES / "candidates" / "replay_q01_pass.json")
    review = chk03_review_for_candidate(candidate, "A2.2", "B1.1")
    violation = review["violations"][0]
    if variant == "wrong_expected":
        violation["expected_level"] = "A1.3"
    elif variant == "coarse_expected":
        violation["expected_level"] = "A2"
    elif variant == "equal_actual":
        violation["actual_level"] = "A2.2"
        review["sentence_grammar_inventory"][0]["level"] = "A2.2"
    elif variant == "coarse_actual":
        violation["actual_level"] = "B1"
    elif variant == "missing_inventory":
        review["sentence_grammar_inventory"] = []
    elif variant == "bad_span":
        review["sentence_grammar_inventory"][0]["span"] = "different span"
    else:
        violation["evidence"] = "推定元を識別できない根拠です。"
    assert review_semantic_problems(review, candidate, None)


@pytest.mark.parametrize(
    "variant",
    (
        "invented_span",
        "partial_word_span",
        "partial_location",
        "mismatched_evidence",
        "wrong_field",
    ),
)
def test_m8_chk03_semantics_rejects_unbound_inventory_claims(variant: str) -> None:
    """RPL-05/R5-02: CHK-03のspan・field・推定根拠をcandidateへ結び付ける。"""

    candidate = load_json(FIXTURES / "candidates" / "replay_q01_pass.json")
    review = chk03_review_for_candidate(candidate, "A2.2", "B1.1")
    inventory = review["sentence_grammar_inventory"][0]
    violation = review["violations"][0]
    if variant == "invented_span":
        inventory["span"] = "I will accept your plan tomorrow."
        violation["location"] = 'body.example.en: "I will accept your plan tomorrow."'
    elif variant == "partial_word_span":
        inventory["span"] = "accep"
        violation["location"] = 'body.example.en: "accep"'
    elif variant == "partial_location":
        violation["location"] = 'body.example.en: "I will accept your plan"'
    elif variant == "mismatched_evidence":
        violation["evidence"] = (
            "reviewer_estimate: 別の構造をB1.1と推定した根拠です。"
        )
    else:
        violation["location"] = (
            'body.gloss: "I will accept your plan today."'
        )
    assert review_semantic_problems(review, candidate, None)


def test_m8_chk03_semantics_requires_violation_for_each_excess_inventory_item() -> None:
    """RPL-05/R10-01: 同一根拠の複数超過構造も別々のCHK-03 violationへ結ぶ。"""

    candidate = load_json(FIXTURES / "candidates" / "replay_q01_pass.json")
    review = chk03_review_for_candidate(candidate, "A2.2", "B1.1")
    second = json.loads(json.dumps(review["sentence_grammar_inventory"][0]))
    second["structure"] = "テスト用の別上限超過構造"
    review["sentence_grammar_inventory"].append(second)
    problems = review_semantic_problems(review, candidate, None)
    assert any(
        "sentence_grammar_inventory[1]の上限超過構造" in item
        for item in problems
    )
    review["violations"].append(json.loads(json.dumps(review["violations"][0])))
    assert not review_semantic_problems(review, candidate, None)
    review["sentence_grammar_inventory"].pop()
    assert any(
        "上限超過構造との一対一対応で余剰" in item
        for item in review_semantic_problems(review, candidate, None)
    )


def normalized_grammar_index() -> dict[str, dict[str, object]]:
    grammar = load_json(ROOT / "data" / "normalized" / "grammar.json")
    return {entry["id"]: entry for entry in grammar["entries"]}


@pytest.mark.parametrize(
    ("grammar_item_id", "structure", "level", "evidence", "actual_level"),
    (
        (
            "gp:84",
            "受動態(助動詞+完了)",
            "B2.2",
            "教員版 gp:84 の B2.2 を引用しました。",
            "B2.2",
        ),
        (
            "gp:63-1",
            "時制・相(現在完了進行)",
            "B1.1-B2.1",
            "教員版 gp:63-1 は親 gp:63 の B1.1-B2.1 を継承しています。",
            "B1.1",
        ),
    ),
)
def test_m8_chk03_semantics_matches_normalized_kyoinban_evidence(
    grammar_item_id: str,
    structure: str,
    level: str,
    evidence: str,
    actual_level: str,
) -> None:
    """RPL-05/R6-01/R7-02: 直接付与・継承の根拠を正規化grammarへ照合する。"""

    candidate = load_json(FIXTURES / "candidates" / "replay_q01_pass.json")
    review = chk03_review_for_candidate(candidate, "A2.2", actual_level)
    inventory = review["sentence_grammar_inventory"][0]
    inventory["evidence"] = evidence
    inventory["grammar_item_id"] = grammar_item_id
    inventory["level"] = level
    inventory["level_source"] = "kyoinban"
    inventory["structure"] = structure
    review["violations"][0]["evidence"] = evidence
    assert not review_semantic_problems(
        review,
        candidate,
        None,
        grammar_index=normalized_grammar_index(),
    )


@pytest.mark.parametrize(
    "variant",
    (
        "missing_id",
        "prefix_id",
        "wrong_level",
        "missing_parent",
        "missing_inheritance",
        "false_structure",
        "level_suffix",
        "range_prefix",
    ),
)
def test_m8_chk03_semantics_rejects_false_kyoinban_evidence(variant: str) -> None:
    """RPL-05/R6-01/R7-02: 架空ID・偽名称・部分level・継承不整合を拒否する。"""

    candidate = load_json(FIXTURES / "candidates" / "replay_q01_pass.json")
    if variant in {"missing_parent", "missing_inheritance", "range_prefix"}:
        review = chk03_review_for_candidate(candidate, "A2.2", "B1.1")
        inventory = review["sentence_grammar_inventory"][0]
        evidence = "教員版 gp:63-1 は B1.1-B2.1 を引用しました。"
        if variant == "missing_inheritance":
            evidence = "教員版 gp:63-1 と親 gp:63 の B1.1-B2.1 を引用しました。"
        elif variant == "range_prefix":
            evidence = "教員版 gp:63-1 は親 gp:63 の XB1.1-B2.1 を継承しています。"
        inventory["evidence"] = evidence
        inventory["grammar_item_id"] = "gp:63-1"
        inventory["level"] = "B1.1-B2.1"
        inventory["level_source"] = "kyoinban"
        inventory["structure"] = "時制・相(現在完了進行)"
    else:
        review = chk03_review_for_candidate(candidate, "A2.2", "B2.2")
        inventory = review["sentence_grammar_inventory"][0]
        grammar_item_id = "gp:999" if variant == "missing_id" else "gp:84"
        evidence = (
            "教員版 gp:840 の B2.2 を引用しました。"
            if variant == "prefix_id"
            else f"教員版 {grammar_item_id} の B2.2 を引用しました。"
        )
        if variant == "level_suffix":
            evidence = f"教員版 {grammar_item_id} の B2.20 を引用しました。"
        inventory["evidence"] = evidence
        inventory["grammar_item_id"] = grammar_item_id
        inventory["level"] = "B2.1" if variant == "wrong_level" else "B2.2"
        inventory["level_source"] = "kyoinban"
        inventory["structure"] = (
            "教員版には存在しない偽の構造名"
            if variant == "false_structure"
            else "受動態(助動詞+完了)"
        )
    review["violations"][0]["evidence"] = inventory["evidence"]
    assert review_semantic_problems(
        review,
        candidate,
        None,
        grammar_index=normalized_grammar_index(),
    )


@pytest.mark.parametrize("variant", ("level_suffix", "missing_japanese_reason"))
def test_m8_chk03_semantics_rejects_incomplete_reviewer_estimate_evidence(
    variant: str,
) -> None:
    """RPL-05/R7-02: reviewer_estimateに完全level引用と日本語根拠を求める。"""

    candidate = load_json(FIXTURES / "candidates" / "replay_q01_pass.json")
    review = chk03_review_for_candidate(candidate, "A2.2", "B1.1")
    inventory = review["sentence_grammar_inventory"][0]
    if variant == "level_suffix":
        inventory["evidence"] = "reviewer_estimate: この構造をB1.10と推定しました。"
    else:
        inventory["evidence"] = "reviewer_estimate: B1.1"
    review["violations"][0]["evidence"] = inventory["evidence"]
    assert review_semantic_problems(review, candidate, None)


def test_m8_empty_grammar_inventory_retries_three_times_and_aborts(
    tmp_path: Path,
) -> None:
    """RPL-05/R7-01: 空インベントリを保存・世代消費せず3回で中止する。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, _action = start_explicit_flow(repo)
    review = load_json(FIXTURES / "reviews" / "pass_q01_gen1.json")
    review["sentence_grammar_inventory"] = []
    review_path = repo / "empty-inventory-review.json"
    write_json(review_path, review)
    for retry in range(1, 4):
        action = flow_cli(
            repo,
            "review",
            "--set-dir",
            f"output/{SET_ID}",
            "--file",
            str(review_path),
        )
        assert (set_dir / "review" / f"q01.gen1.review.invalid{retry}.txt").is_file()
        if retry < 3:
            assert action["action"] == "run_review"
            assert action["retry_number"] == retry
        else:
            assert action["action"] == "aborted"
            assert action["reason"] == "review_invalid"
    assert not (set_dir / "review" / "q01.gen1.review.json").exists()
    assert not (set_dir / ".staging" / "flow-state.json").exists()


def test_m8_inventory_excess_cannot_pass_and_retries_three_times(
    tmp_path: Path,
) -> None:
    """RPL-05/R8-01: 列挙済み上限超過をpassにしたreviewを3回で監査付き中止する。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, _action = start_explicit_flow(repo)
    candidate = load_json(FIXTURES / "candidates" / "replay_q01_pass.json")
    review = load_json(FIXTURES / "reviews" / "pass_q01_gen1.json")
    inventory = review["sentence_grammar_inventory"][0]
    inventory["evidence"] = "教員版 gp:84 のレベル B2.2 を引用しました。"
    inventory["grammar_item_id"] = "gp:84"
    inventory["level"] = "B2.2"
    inventory["span"] = "I"
    inventory["structure"] = "受動態(助動詞+完了)"
    problems = review_semantic_problems(
        review,
        candidate,
        None,
        grammar_index=normalized_grammar_index(),
    )
    assert any("L_ctx=A2.2を超えていますがCHK-03がfailではありません" in item for item in problems)
    assert any("上限超過構造に対応する" in item for item in problems)

    review_path = repo / "excess-inventory-pass-review.json"
    write_json(review_path, review)
    for retry in range(1, 4):
        action = flow_cli(
            repo,
            "review",
            "--set-dir",
            f"output/{SET_ID}",
            "--file",
            str(review_path),
        )
        assert (set_dir / "review" / f"q01.gen1.review.invalid{retry}.txt").is_file()
        if retry < 3:
            assert action["action"] == "run_review"
            assert action["retry_number"] == retry
        else:
            assert action["action"] == "aborted"
            assert action["reason"] == "review_invalid"
    assert not (set_dir / "review" / "q01.gen1.review.json").exists()
    assert not (set_dir / ".staging" / "flow-state.json").exists()


def test_m8_false_kyoinban_claim_retries_without_canonical_review(
    tmp_path: Path,
) -> None:
    """RPL-05/R6-01: 架空教員版根拠を保存・世代消費せずINF再実行へ送る。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, _action = start_explicit_flow(repo)
    candidate = load_json(FIXTURES / "candidates" / "replay_q01_pass.json")
    review = chk03_review_for_candidate(candidate, "A2.2", "B1.1")
    inventory = review["sentence_grammar_inventory"][0]
    inventory["evidence"] = "教員版 gp:999 の B1.1 を引用しました。"
    inventory["grammar_item_id"] = "gp:999"
    inventory["level_source"] = "kyoinban"
    review["violations"][0]["evidence"] = inventory["evidence"]
    review_path = repo / "false-kyoinban-review.json"
    write_json(review_path, review)
    action = flow_cli(
        repo,
        "review",
        "--set-dir",
        f"output/{SET_ID}",
        "--file",
        str(review_path),
    )
    assert action["action"] == "run_review"
    assert action["retry_number"] == 1
    assert not (set_dir / "review" / "q01.gen1.review.json").exists()
    assert (set_dir / "review" / "q01.gen1.review.invalid1.txt").is_file()


def test_m8_chk03_inconsistent_claim_retries_without_canonical_review(
    tmp_path: Path,
) -> None:
    """RPL-05/R4-05: 不整合CHK-03を正準受理せずINF再実行へ送る。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir, _action = start_explicit_flow(repo)
    candidate = load_json(FIXTURES / "candidates" / "replay_q01_pass.json")
    review = chk03_review_for_candidate(candidate, "A1.3", "B1.1")
    review_path = repo / "bad-chk03-review.json"
    write_json(review_path, review)
    action = flow_cli(
        repo,
        "review",
        "--set-dir",
        f"output/{SET_ID}",
        "--file",
        str(review_path),
    )
    assert action["action"] == "run_review"
    assert not (set_dir / "review" / "q01.gen1.review.json").exists()
    assert (set_dir / "review" / "q01.gen1.review.invalid1.txt").is_file()


def test_m8_flow_regeneration_separates_sources_and_counts_disputes(
    tmp_path: Path,
) -> None:
    """RPL-02/RPL-07: 再生成指摘源を分離しmachine disputeを保持する。"""

    repo = make_isolated_config_repo(tmp_path)
    set_dir = repo / "output" / SET_ID
    session = build_session_input(
        {
            "format": "vocab_flashcard_en2ja",
            "level": "A1",
            "level_scale": "cefr",
            "mode": "explicit",
            "question_count": 1,
            "targets": ["lex:book:noun"],
        },
        SET_ID,
        created_at="2099-01-01T00:00:00+09:00",
        model="m8-test",
        tool="codex",
    )
    session_path = repo / "session.json"
    write_json(session_path, session)
    flow_cli(
        repo,
        "init",
        "--set-dir",
        f"output/{SET_ID}",
        "--file",
        str(session_path),
    )
    action = flow_cli(
        repo,
        "candidate",
        "--set-dir",
        f"output/{SET_ID}",
        "--file",
        str(FIXTURES / "candidates" / "mch_06_high_level_abandon.json"),
    )
    machine = load_json(set_dir / "review" / "q01.gen1.machine.json")
    disputed_violation = next(
        item for item in machine["violations"] if item["code"] == "V-LEX-02"
    )
    review = load_json(
        FIXTURES / "reviews" / "pass_machine_fail_q01_gen1.json"
    )
    dispute = load_json(FIXTURES / "cli" / "machine_dispute_pos_tagging.json")
    dispute["location"] = disputed_violation["location"]
    dispute["machine_violation_code"] = disputed_violation["code"]
    review["machine_check_disputes"] = [dispute]
    review_path = repo / "review-gen1.json"
    write_json(review_path, review)
    action = flow_cli(
        repo,
        "review",
        "--set-dir",
        f"output/{SET_ID}",
        "--file",
        str(review_path),
    )
    regeneration = action["regeneration"]
    assert regeneration["previous_candidate"]["question_id"] == "q01"
    assert "V-LEX-02" in {item["code"] for item in regeneration["machine_violations"]}
    assert regeneration["review_violations"] == []
    assert regeneration["set_check_violations"] == []
    assert regeneration["machine_check_disputes"] == review["machine_check_disputes"]
    assert "機械検査違反は回避対象" in regeneration["machine_check_dispute_instruction"]

    for generation in (2, 3):
        action = flow_cli(
            repo,
            "candidate",
            "--set-dir",
            f"output/{SET_ID}",
            "--file",
            str(FIXTURES / "candidates" / "mch_06_high_level_abandon.json"),
        )
        assert action["action"] == "run_review"
        action = flow_cli(
            repo,
            "review",
            "--set-dir",
            f"output/{SET_ID}",
            "--file",
            str(
                FIXTURES
                / "reviews"
                / f"pass_machine_fail_q01_gen{generation}.json"
            ),
        )
    assert action["action"] == "teacher_consult"
    assert action["machine_check_dispute_count"] == 1
