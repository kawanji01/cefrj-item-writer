"""第1層・第2層テストで共有する実CLI駆動ヘルパー。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parent.parent
PYTHON = Path(sys.executable)
FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN = ROOT / "tests" / "golden"
OFFICIAL_FORMATS = (
    "vocab_mcq_en2ja",
    "vocab_mcq_ja2en",
    "vocab_flashcard_en2ja",
    "vocab_flashcard_ja2en",
    "grammar_mcq",
    "grammar_cloze",
    "grammar_reorder",
    "grammar_rewrite",
    "grammar_example_selfcheck",
)
GOLDEN_CASE_FILES = (
    "these_relative_clause.candidate.json",
    "estimate_label.candidate.json",
)
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from flow_control import (  # noqa: E402
    build_config_snapshot,
    build_finalize_metadata,
    build_review_request,
    build_session_from_candidate,
    build_slot_outcome,
)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def run_cli(
    *arguments: str,
    stdin: bytes | None = None,
    env: dict[str, str] | None = None,
    cwd: Path = ROOT,
) -> subprocess.CompletedProcess[bytes]:
    child_env = os.environ.copy()
    if env is not None:
        child_env.update(env)
    return subprocess.run(
        [str(PYTHON), *arguments],
        cwd=cwd,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=child_env,
        check=False,
    )


def stdout_json(completed: subprocess.CompletedProcess[bytes]) -> Any:
    return json.loads(completed.stdout.decode("utf-8"))


def stderr_json(completed: subprocess.CompletedProcess[bytes]) -> Any:
    return json.loads(completed.stderr.decode("utf-8"))


def strip_generated_at(payload: bytes) -> bytes:
    value = json.loads(payload)
    value.pop("generated_at", None)
    return canonical_bytes(value)


@contextmanager
def output_set(set_id: str) -> Iterator[Path]:
    set_dir = ROOT / "output" / set_id
    if set_dir.exists() or set_dir.is_symlink():
        raise RuntimeError(f"テスト予約set_idが既に存在します: {set_dir}")
    set_dir.mkdir()
    try:
        yield set_dir
    finally:
        shutil.rmtree(set_dir)


def machine_for_path(
    candidate_path: Path,
    set_id: str,
    generation: str = "gen1",
    *,
    expected_format: str | None = None,
    expected_level: str | None = None,
    requested_count: int = 1,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    candidate = load_json(candidate_path)
    return run_cli(
        "scripts/machine_check.py",
        "--candidate",
        str(candidate_path.relative_to(ROOT)),
        "--set-id",
        set_id,
        "--generation",
        generation,
        "--expected-format",
        expected_format or candidate["format"],
        "--expected-level",
        expected_level or candidate["level"]["value"],
        "--requested-count",
        str(requested_count),
        env=env,
    )


def review_request(
    candidate: dict[str, Any],
    machine: dict[str, Any],
    set_id: str,
    generation: str,
) -> dict[str, Any]:
    limits = load_json(ROOT / "data" / "config" / "limits.json")
    proper = load_json(ROOT / "data" / "config" / "proper_nouns.json")["words"]
    return build_review_request(
        candidate,
        machine,
        set_id,
        generation,
        limits=limits,
        proper_nouns=proper,
        topic=None,
    )


def review_result(
    fixture_name: str,
    set_id: str,
    question_id: str,
    generation: str,
) -> dict[str, Any]:
    value = load_json(FIXTURES / "reviews" / fixture_name)
    value["set_id"] = set_id
    value["question_id"] = question_id
    value["generation"] = generation
    return value


def install_attempt(
    set_dir: Path,
    candidate_source: Path,
    generation: str = "gen1",
    *,
    review_fixture: str = "pass_q01_gen1.json",
    requested_count: int = 1,
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = load_json(candidate_source)
    qid = candidate["question_id"]
    review_dir = set_dir / "review"
    review_dir.mkdir(exist_ok=True)
    candidate_path = review_dir / f"{qid}.{generation}.candidate.json"
    write_json(candidate_path, candidate)
    completed = machine_for_path(
        candidate_path,
        set_dir.name,
        generation,
        requested_count=requested_count,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8"))
    machine = stdout_json(completed)
    write_json(review_dir / f"{qid}.{generation}.machine.json", machine)
    write_json(
        review_dir / f"{qid}.{generation}.request.json",
        review_request(candidate, machine, set_dir.name, generation),
    )
    review = review_result(review_fixture, set_dir.name, qid, generation)
    write_json(review_dir / f"{qid}.{generation}.review.json", review)
    return machine, review


def run_incremental(set_dir: Path, qid: str, generation: str) -> dict[str, Any]:
    completed = run_cli(
        "scripts/set_check.py",
        "--set-dir",
        str(set_dir.relative_to(ROOT)),
        "--target",
        qid,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8"))
    report = stdout_json(completed)
    write_json(set_dir / "review" / f"set_check.{qid}.{generation}.json", report)
    return report


def write_slot_outcome(
    set_dir: Path,
    slot_id: str,
    attempted_ids: list[str],
    accepted_id: str,
) -> None:
    write_json(
        set_dir / "review" / f"slot.{slot_id}.outcome.json",
        build_slot_outcome(set_dir.name, slot_id, attempted_ids, accepted_id),
    )


def run_final_check(set_dir: Path) -> dict[str, Any]:
    completed = run_cli(
        "scripts/set_check.py", "--set-dir", str(set_dir.relative_to(ROOT))
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8"))
    report = stdout_json(completed)
    write_json(set_dir / "review" / "set_check.final.json", report)
    return report


def finalize_metadata(
    set_dir: Path,
    candidate: dict[str, Any],
    final_ids: list[str],
    requested_count: int,
) -> dict[str, Any]:
    created_at = (
        f"{set_dir.name[0:4]}-{set_dir.name[4:6]}-{set_dir.name[6:8]}T"
        f"{set_dir.name[9:11]}:{set_dir.name[11:13]}:{set_dir.name[13:15]}+09:00"
    )
    session = build_session_from_candidate(
        candidate,
        set_dir.name,
        requested_count,
        created_at=created_at,
        mode="proposal",
        model="m8-test",
        tool="codex",
    )
    snapshot = build_config_snapshot(
        load_json(ROOT / "data" / "config" / "limits.json"),
        load_json(ROOT / "data" / "config" / "proper_nouns.json")["words"],
    )
    return build_finalize_metadata(session, snapshot, final_ids)
