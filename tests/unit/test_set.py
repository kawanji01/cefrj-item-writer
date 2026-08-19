from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from tests.support import (
    FIXTURES,
    ROOT,
    canonical_bytes,
    finalize_metadata,
    install_attempt,
    load_json,
    output_set,
    run_cli,
    run_final_check,
    run_incremental,
    stderr_json,
    stdout_json,
    write_slot_outcome,
)


def violation_codes(report: dict[str, object]) -> set[str]:
    return {item["code"] for item in report["violations"]}  # type: ignore[index]


def complete_one_question(set_dir: Path) -> tuple[dict[str, object], bytes]:
    source = FIXTURES / "candidates" / "replay_q01_pass.json"
    candidate = load_json(source)
    machine, review = install_attempt(set_dir, source)
    assert machine["verdict"] == review["verdict"] == "pass"
    assert run_incremental(set_dir, "q01", "gen1")["verdict"] == "pass"
    write_slot_outcome(set_dir, "q01", ["q01"], "q01")
    assert run_final_check(set_dir)["verdict"] == "pass"
    metadata = canonical_bytes(finalize_metadata(set_dir, candidate, ["q01"], 1))
    return candidate, metadata


def finalize(set_dir: Path, metadata: bytes):
    return run_cli(
        "scripts/finalize_set.py",
        "--set-dir",
        str(set_dir.relative_to(ROOT)),
        stdin=metadata,
    )


def test_ci_set_01_duplicate_target() -> None:
    """CI-SET-01: 同一lex対象を持つ2問目をV-SET-01で検出する。"""

    with output_set("20990101-040401-st01") as set_dir:
        install_attempt(set_dir, FIXTURES / "candidates" / "replay_q01_conflict.json", requested_count=2)
        assert run_incremental(set_dir, "q01", "gen1")["verdict"] == "pass"
        install_attempt(set_dir, FIXTURES / "candidates" / "set_duplicate_q02.json", requested_count=2)
        second = run_incremental(set_dir, "q02", "gen1")
        assert second["verdict"] == "fail"
        assert "V-SET-01" in violation_codes(second)


def test_ci_set_02_reused_sentence() -> None:
    """CI-SET-02: 同一例文を持つ異なる2対象をV-SET-02で検出する。"""

    with output_set("20990101-040402-st02") as set_dir:
        install_attempt(set_dir, FIXTURES / "candidates" / "replay_q01_conflict.json", requested_count=2)
        assert run_incremental(set_dir, "q01", "gen1")["verdict"] == "pass"
        install_attempt(set_dir, FIXTURES / "candidates" / "replay_q02_conflict.json", requested_count=2)
        second = run_incremental(set_dir, "q02", "gen1")
        assert second["verdict"] == "fail"
        assert "V-SET-02" in violation_codes(second)


def test_ci_set_03_excessive_distractor_reuse() -> None:
    """CI-SET-03: 同一誤答由来IDの3問再利用をV-SET-03で検出する。"""

    with output_set("20990101-040403-st03") as set_dir:
        for number in (1, 2):
            qid = f"q{number:02d}"
            install_attempt(
                set_dir,
                FIXTURES / "candidates" / f"set_reuse_{qid}.json",
                requested_count=3,
            )
            assert run_incremental(set_dir, qid, "gen1")["verdict"] == "pass"
        install_attempt(
            set_dir,
            FIXTURES / "candidates" / "set_reuse_q03.json",
            requested_count=3,
        )
        third = run_incremental(set_dir, "q03", "gen1")
        assert third["verdict"] == "fail"
        assert "V-SET-03" in violation_codes(third)


def test_ci_set_04_atomic_finalize_success_and_failure() -> None:
    """CI-SET-04: 合格監査だけを原子的に確定し不合格監査ではsetを作らない。"""

    with output_set("20990101-040404-st04") as set_dir:
        _candidate, metadata = complete_one_question(set_dir)
        completed = finalize(set_dir, metadata)
        assert completed.returncode == 0, completed.stderr.decode()
        assert (set_dir / "set.json").is_file()
        validated = run_cli(
            "scripts/validate.py",
            "--schema",
            "set",
            "--file",
            str((set_dir / "set.json").relative_to(ROOT)),
        )
        assert validated.returncode == 0

    with output_set("20990101-040405-st04") as set_dir:
        source = FIXTURES / "candidates" / "replay_q01_pass.json"
        candidate = load_json(source)
        install_attempt(set_dir, source, review_fixture="fail_q01_gen1.json")
        metadata = canonical_bytes(finalize_metadata(set_dir, candidate, ["q01"], 1))
        completed = finalize(set_dir, metadata)
        assert completed.returncode == 1
        assert stderr_json(completed)["error_code"].startswith("E-CONTRACT")
        assert not (set_dir / "set.json").exists()
        assert any((set_dir / "review").iterdir())


def test_ci_set_04_parallel_finalize_and_symlink(tmp_path: Path) -> None:
    """CI-SET-04: 並行finalizeは1件だけ成功し既存一時symlinkを変更しない。"""

    with output_set("20990101-040406-st04") as set_dir:
        _candidate, metadata = complete_one_question(set_dir)
        target = tmp_path / "symlink-target"
        target.write_text("unchanged", encoding="utf-8")
        link = set_dir / ".set.json.tmp.fixed"
        link.symlink_to(target)
        command = [
            sys.executable,
            "scripts/finalize_set.py",
            "--set-dir",
            str(set_dir.relative_to(ROOT)),
        ]
        first = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        second = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        first_out, first_err = first.communicate(metadata)
        second_out, second_err = second.communicate(metadata)
        assert sorted((first.returncode, second.returncode)) == [0, 1]
        failed_stderr = first_err if first.returncode else second_err
        assert json.loads(failed_stderr)["error_code"] == "E-CONTRACT-05"
        assert (set_dir / "set.json").is_file()
        before = (set_dir / "set.json").read_bytes()
        assert target.read_text(encoding="utf-8") == "unchanged"
        assert link.is_symlink() and link.resolve() == target
        assert (set_dir / "set.json").read_bytes() == before


def test_ci_set_05_audit_names_and_references() -> None:
    """CI-SET-05: 確定セットの監査名を目録へ限定し全provenance参照を解決する。"""

    pattern = re.compile(
        r"^(?:q(?:0[1-9]|1[0-9]|20)\.gen[1-3]\.(?:candidate|machine|request|review)\.json|"
        r"set_check\.(?:q(?:0[1-9]|1[0-9]|20)\.gen[1-3]|final)\.json|"
        r"slot\.q(?:0[1-9]|1[0-9]|20)\.outcome\.json)$"
    )
    with output_set("20990101-040407-st05") as set_dir:
        _candidate, metadata = complete_one_question(set_dir)
        assert finalize(set_dir, metadata).returncode == 0
        assert all(pattern.fullmatch(path.name) for path in (set_dir / "review").iterdir())
        document = load_json(set_dir / "set.json")
        for question in document["questions"]:
            provenance = question["provenance"]
            for key in ("candidate_ref", "machine_report_ref", "review_ref"):
                assert (set_dir / provenance[key]).is_file()


def test_ci_set_06_canonical_content_blocks() -> None:
    """CI-SET-06: 正本に合格問題・昇順ID・版・設定・原本・両出典を保持する。"""

    with output_set("20990101-040408-st06") as set_dir:
        _candidate, metadata = complete_one_question(set_dir)
        assert finalize(set_dir, metadata).returncode == 0
        document = load_json(set_dir / "set.json")
        ids = [question["question_id"] for question in document["questions"]]
        assert ids == ["q01"] == sorted(set(ids))
        assert document["schema_version"] == "1.0.0"
        assert set(document["config_snapshot"]) == {"limits", "proper_nouns"}
        assert document["data_version"]
        assert len(document["source_checksums"]) == 2
        assert set(document["attribution"]) == {"wordlist", "grammar_profile"}
        assert all(question["provenance"]["generation"] == "gen1" for question in document["questions"])
