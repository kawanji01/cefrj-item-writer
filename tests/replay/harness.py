"""候補生成と独立レビューだけをfixtureへ置換する決定的リプレイ。"""

from __future__ import annotations

import base64
import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from tests.support import (
    FIXTURES,
    ROOT,
    canonical_bytes,
    finalize_metadata,
    load_json,
    machine_for_path,
    output_set,
    review_request,
    run_cli,
    stderr_json,
    stdout_json,
    write_json,
)


SET_ID = "20990101-000000-rpl1"


@dataclass
class ReplayResult:
    attempts_total: int
    audit_files: list[str]
    generation_verdicts: list[dict[str, Any]]
    outcome: str
    regeneration_payloads: list[dict[str, Any]]
    set_document: dict[str, Any] | None
    set_questions: list[str]


def validation_failure(raw: bytes, diagnostic: str) -> dict[str, Any]:
    return {
        "audit_format": "aud09-v2",
        "diagnostic": diagnostic,
        "kind": "validation_failure",
        "raw_output_base64": base64.b64encode(raw).decode("ascii"),
    }


def surrogate_failure() -> dict[str, Any]:
    return {
        "audit_format": "aud09-v2",
        "kind": "utf8_encode_failure",
        "position": "JSON string value U+D800",
        "reason": "孤立サロゲートをstrict UTF-8へ符号化できません",
    }


def validate_fixture(schema: str, path: Path):
    return run_cli(
        "scripts/validate.py",
        "--schema",
        schema,
        "--file",
        str(path.relative_to(ROOT)),
    )


def save_invalid(path: Path, source: Path, diagnostic: str) -> None:
    if source.name == "invalid_surrogate.json":
        write_json(path, surrogate_failure())
    else:
        write_json(path, validation_failure(source.read_bytes(), diagnostic))


def owner_for_question(
    qid: str,
    question_count: int,
    owner_by_question: dict[str, str],
    accepted_slots: dict[str, str],
    slot_attempts: dict[str, list[str]],
) -> str:
    if qid in owner_by_question:
        return owner_by_question[qid]
    number = int(qid[1:])
    if number <= question_count:
        owner = qid
    else:
        unresolved = [
            f"q{slot:02d}"
            for slot in range(1, question_count + 1)
            if f"q{slot:02d}" not in accepted_slots
            and len(slot_attempts[f"q{slot:02d}"]) == 1
        ]
        if not unresolved:
            unresolved = [
                f"q{slot:02d}"
                for slot in range(1, question_count + 1)
                if f"q{slot:02d}" not in accepted_slots
            ]
        owner = unresolved[0]
    owner_by_question[qid] = owner
    if qid not in slot_attempts[owner]:
        slot_attempts[owner].append(qid)
    return owner


@contextmanager
def replay_scenario(path: Path) -> Iterator[tuple[ReplayResult, Path]]:
    scenario = load_json(path)
    request = scenario["request"]
    question_count = request["question_count"]
    with output_set(SET_ID) as set_dir:
        review_dir = set_dir / "review"
        review_dir.mkdir()
        accepted_slots: dict[str, str] = {}
        slot_attempts = {f"q{number:02d}": [] for number in range(1, question_count + 1)}
        owner_by_question: dict[str, str] = {}
        regeneration_payloads: list[dict[str, Any]] = []
        generation_verdicts: list[dict[str, Any]] = []
        aborted = False
        attempts_total = 0

        for step_index, step in enumerate(scenario["steps"]):
            attempts_total += 1
            qid = step["question_id"]
            generation = step["gen"]
            owner = owner_for_question(
                qid,
                question_count,
                owner_by_question,
                accepted_slots,
                slot_attempts,
            )
            candidate_sources = [step["candidate"], *step["candidate_retries"]]
            candidate: dict[str, Any] | None = None
            candidate_path: Path | None = None
            for invalid_index, relative in enumerate(candidate_sources, start=1):
                source = FIXTURES / "candidates" / relative
                validated = validate_fixture("candidate", source)
                if validated.returncode == 0:
                    candidate = load_json(source)
                    if candidate.get("question_id") != qid:
                        raise AssertionError(f"scenarioのquestion_idとcandidateが不一致です: {path.name}")
                    candidate_path = review_dir / f"{qid}.{generation}.candidate.json"
                    candidate_path.write_bytes(source.read_bytes())
                    break
                save_invalid(
                    review_dir / f"{qid}.{generation}.candidate.invalid{invalid_index}.txt",
                    source,
                    validated.stderr.decode("utf-8"),
                )
            if candidate is None or candidate_path is None:
                generation_verdicts.append(
                    {"generation": generation, "question_id": qid, "verdict": "fail", "reason": "candidate_invalid"}
                )
                continue

            machine_completed = machine_for_path(
                candidate_path,
                SET_ID,
                generation,
                expected_format=request["format"],
                expected_level=request["level"],
                requested_count=question_count,
            )
            if machine_completed.returncode != 0:
                raise AssertionError(machine_completed.stderr.decode("utf-8"))
            machine = stdout_json(machine_completed)
            write_json(review_dir / f"{qid}.{generation}.machine.json", machine)
            envelope = review_request(candidate, machine, SET_ID, generation)
            validated_request = run_cli(
                "scripts/validate.py",
                "--schema",
                "review_request",
                "--file",
                "-",
                stdin=canonical_bytes(envelope),
            )
            if validated_request.returncode != 0:
                raise AssertionError(validated_request.stderr.decode("utf-8"))
            write_json(review_dir / f"{qid}.{generation}.request.json", envelope)

            review_sources = [step["review"], *step["review_retries"]]
            review: dict[str, Any] | None = None
            for invalid_index, relative in enumerate(review_sources, start=1):
                source = FIXTURES / "reviews" / relative
                validated = validate_fixture("review_result", source)
                if validated.returncode == 0:
                    review = load_json(source)
                    if (
                        review["set_id"] != SET_ID
                        or review["question_id"] != qid
                        or review["generation"] != generation
                    ):
                        raise AssertionError(f"scenarioのreview識別子が不一致です: {path.name}")
                    (review_dir / f"{qid}.{generation}.review.json").write_bytes(source.read_bytes())
                    break
                save_invalid(
                    review_dir / f"{qid}.{generation}.review.invalid{invalid_index}.txt",
                    source,
                    validated.stderr.decode("utf-8"),
                )
            if review is None:
                aborted = True
                generation_verdicts.append(
                    {"generation": generation, "question_id": qid, "verdict": "aborted", "reason": "review_invalid"}
                )
                break

            if machine["verdict"] == "fail" or review["verdict"] == "fail":
                combined = [*machine["violations"], *review["violations"]]
                generation_verdicts.append(
                    {"generation": generation, "question_id": qid, "verdict": "fail", "reason": "machine_or_review", "violations": combined}
                )
                if any(
                    later["question_id"] == qid
                    for later in scenario["steps"][step_index + 1 :]
                ):
                    regeneration_payloads.append(
                        {"generation": generation, "question_id": qid, "violations": combined}
                    )
                continue

            set_completed = run_cli(
                "scripts/set_check.py",
                "--set-dir",
                str(set_dir.relative_to(ROOT)),
                "--target",
                qid,
            )
            if set_completed.returncode != 0:
                raise AssertionError(set_completed.stderr.decode("utf-8"))
            set_report = stdout_json(set_completed)
            write_json(review_dir / f"set_check.{qid}.{generation}.json", set_report)
            if set_report["verdict"] == "fail":
                generation_verdicts.append(
                    {"generation": generation, "question_id": qid, "verdict": "fail", "reason": "set_check", "violations": set_report["violations"]}
                )
                if any(
                    later["question_id"] == qid
                    for later in scenario["steps"][step_index + 1 :]
                ):
                    regeneration_payloads.append(
                        {"generation": generation, "question_id": qid, "violations": set_report["violations"]}
                    )
                continue

            accepted_slots[owner] = qid
            generation_verdicts.append(
                {"generation": generation, "question_id": qid, "verdict": "pass", "reason": "accepted"}
            )
            write_json(
                review_dir / f"slot.{owner}.outcome.json",
                {
                    "accepted_question_id": qid,
                    "attempted_question_ids": slot_attempts[owner],
                    "set_id": SET_ID,
                    "slot_question_id": owner,
                    "status": "accepted",
                    "teacher_decision": None,
                },
            )

        set_document = None
        if not aborted and len(accepted_slots) == question_count:
            final = run_cli(
                "scripts/set_check.py", "--set-dir", str(set_dir.relative_to(ROOT))
            )
            if final.returncode != 0:
                raise AssertionError(final.stderr.decode("utf-8"))
            final_report = stdout_json(final)
            write_json(review_dir / "set_check.final.json", final_report)
            final_ids = sorted(accepted_slots.values(), key=lambda value: int(value[1:]))
            first_candidate = load_json(
                next(review_dir.glob(f"{final_ids[0]}.gen*.candidate.json"))
            )
            metadata = finalize_metadata(set_dir, first_candidate, final_ids, question_count)
            finalized = run_cli(
                "scripts/finalize_set.py",
                "--set-dir",
                str(set_dir.relative_to(ROOT)),
                stdin=canonical_bytes(metadata),
            )
            if finalized.returncode != 0:
                raise AssertionError(finalized.stderr.decode("utf-8"))
            validated = run_cli(
                "scripts/validate.py", "--set-dir", str(set_dir.relative_to(ROOT))
            )
            if validated.returncode != 0:
                raise AssertionError(validated.stderr.decode("utf-8"))
            set_document = load_json(set_dir / "set.json")
            outcome = "completed"
        elif aborted:
            outcome = "aborted"
        else:
            outcome = "teacher_consult"

        audit_files = sorted(path.name for path in review_dir.iterdir())
        set_questions = (
            [question["question_id"] for question in set_document["questions"]]
            if set_document is not None
            else []
        )
        result = ReplayResult(
            attempts_total=attempts_total,
            audit_files=audit_files,
            generation_verdicts=generation_verdicts,
            outcome=outcome,
            regeneration_payloads=regeneration_payloads,
            set_document=set_document,
            set_questions=set_questions,
        )
        yield result, set_dir
