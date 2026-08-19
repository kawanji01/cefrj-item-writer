from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.support import (
    FIXTURES,
    GOLDEN,
    ROOT,
    output_set,
    run_cli,
    stderr_json,
    stdout_json,
    strip_generated_at,
)


@pytest.mark.parametrize(
    ("arguments", "expected_code"),
    [
        (("scripts/build_normalized.py", "--source-dir"), "E-INPUT-01"),
        (("scripts/machine_check.py",), "E-INPUT-01"),
        (("scripts/lookup.py",), "E-INPUT-01"),
        (("scripts/set_check.py",), "E-INPUT-01"),
        (("scripts/finalize_set.py",), "E-INPUT-01"),
        (("scripts/build_html.py",), "E-INPUT-01"),
        (("scripts/validate.py",), "E-INPUT-01"),
        (("scripts/doctor.py", "--unknown-m8-option"), "E-INPUT-01"),
    ],
    ids=("build", "machine", "lookup", "set", "finalize", "html", "validate", "doctor"),
)
def test_ci_cli_01_argument_errors(arguments: tuple[str, ...], expected_code: str) -> None:
    """CI-CLI-01: 全8 CLIが引数不正を定義済みコードと日本語対処で停止する。"""

    completed = run_cli(*arguments)
    assert completed.returncode == 1
    error = stderr_json(completed)
    assert error["error_code"] == expected_code
    assert error["message"] and error["remedy"]
    assert any("ぁ" <= character <= "龥" for character in error["remedy"])


@pytest.mark.parametrize(
    "arguments",
    [
        ("scripts/build_normalized.py", "--source-dir", "tests/fixtures/does-not-exist"),
        (
            "scripts/machine_check.py", "--candidate", "tests/fixtures/does-not-exist.json",
            "--set-id", "20990101-030303-cli1", "--generation", "gen1",
            "--expected-format", "grammar_cloze", "--expected-level", "A1.2",
            "--requested-count", "1",
        ),
        ("scripts/set_check.py", "--set-dir", "output/20990101-030303-none"),
        ("scripts/finalize_set.py", "--set-dir", "output/20990101-030303-none"),
        ("scripts/build_html.py", "--set", "tests/fixtures/does-not-exist.json"),
        ("scripts/validate.py", "--schema", "candidate", "--file", "tests/fixtures/does-not-exist.json"),
    ],
    ids=("build", "machine", "set", "finalize", "html", "validate"),
)
def test_ci_cli_01_missing_paths(arguments: tuple[str, ...]) -> None:
    """CI-CLI-01: パス入力6 CLIが存在しないパスを定義済みエラーで拒否する。"""

    completed = run_cli(*arguments, stdin=b"{}\n" if arguments[0].endswith("finalize_set.py") else None)
    assert completed.returncode == 1
    error = stderr_json(completed)
    assert error["error_code"].startswith(("E-INPUT", "E-CONTRACT", "E-DATA"))
    assert error["remedy"]


@pytest.mark.parametrize(
    "arguments",
    [
        (
            "scripts/machine_check.py", "--candidate", "-",
            "--set-id", "20990101-030303-cli1", "--generation", "gen1",
            "--expected-format", "grammar_cloze", "--expected-level", "A1.2",
            "--requested-count", "1",
        ),
        ("scripts/finalize_set.py", "--set-dir", "output/20990101-030303-none"),
        ("scripts/validate.py", "--schema", "candidate", "--file", "-"),
    ],
    ids=("machine", "finalize", "validate"),
)
def test_ci_cli_01_invalid_json_stdin(arguments: tuple[str, ...]) -> None:
    """CI-CLI-01: stdin JSON経路3 CLIがパース不能JSONを拒否する。"""

    completed = run_cli(*arguments, stdin=b"{\n")
    assert completed.returncode == 1
    error = stderr_json(completed)
    assert error["error_code"] == "E-INPUT-03"
    assert error["remedy"]


def test_ci_cli_02_machine_compatibility_golden() -> None:
    """CI-CLI-02: 互換候補のmachine出力がCI-R-02の意味でゴールデン一致する。"""

    completed = run_cli(
        "scripts/machine_check.py",
        "--candidate", "tests/fixtures/candidates/compat/grammar_cloze.json",
        "--set-id", "20990101-000000-rpl1",
        "--generation", "gen1",
        "--expected-format", "grammar_cloze",
        "--expected-level", "A1.2",
        "--requested-count", "1",
    )
    assert completed.returncode == 0
    golden = (GOLDEN / "machine" / "grammar_cloze.machine.json").read_bytes()
    assert strip_generated_at(completed.stdout) == strip_generated_at(golden)


def clone_for_doctor(tmp_path: Path) -> Path:
    clone = tmp_path / "repo"
    subprocess.run(
        ["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(clone)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    os.symlink(ROOT / ".venv", clone / ".venv", target_is_directory=True)
    return clone


def test_ci_cli_03_doctor_complete_environment() -> None:
    """CI-CLI-03: 完全な現行環境でdoctorが全項目passする。"""

    completed = run_cli("scripts/doctor.py")
    assert completed.returncode == 0, completed.stderr.decode()
    result = stdout_json(completed)
    assert result["summary"]["fail"] == 0
    assert all(check["status"] == "pass" for check in result["checks"])


@pytest.mark.parametrize("variant", ("normalized", "source", "limits"))
def test_ci_cli_03_doctor_failure_modes(tmp_path: Path, variant: str) -> None:
    """CI-CLI-03: doctorが正規化欠落・原本不一致・limits欠落をE系コードで診断する。"""

    clone = clone_for_doctor(tmp_path)
    if variant == "normalized":
        shutil.rmtree(clone / "data" / "normalized")
        expected = b"E-DATA-03"
    elif variant == "source":
        source = next((clone / "data" / "source").glob("*.xlsx"))
        source.write_bytes(source.read_bytes() + b"\x00")
        expected = b"E-DATA-02"
    else:
        (clone / "data" / "config" / "limits.json").unlink()
        expected = b"E-DATA-05"
    completed = run_cli("scripts/doctor.py", cwd=clone)
    assert completed.returncode == 1
    assert expected in completed.stdout


def test_ci_cli_04_incomplete_set_state() -> None:
    """CI-CLI-04: 監査だけの中断セットを正常なincomplete状態として返す。"""

    with output_set("20990101-030304-cli4") as set_dir:
        review = set_dir / "review"
        review.mkdir()
        shutil.copyfile(
            FIXTURES / "candidates" / "compat" / "grammar_cloze.json",
            review / "q01.gen1.candidate.json",
        )
        completed = run_cli(
            "scripts/validate.py", "--set-dir", str(set_dir.relative_to(ROOT))
        )
        assert completed.returncode == 0
        assert completed.stderr == b""
        assert stdout_json(completed) == {
            "set_dir": "output/20990101-030304-cli4",
            "set_json_path": None,
            "status": "incomplete",
            "validation": None,
        }
