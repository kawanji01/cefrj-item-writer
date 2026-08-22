from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.replay.harness import replay_scenario
from tests.support import FIXTURES, ROOT, load_json, machine_for_path, stdout_json


SCENARIOS = FIXTURES / "scenarios"


def run(name: str):
    path = SCENARIOS / f"{name}.json"
    return path, load_json(path)


def assert_expected(result, scenario: dict[str, object]) -> None:
    expected = scenario["expected"]
    assert result.outcome == expected["outcome"]
    assert result.set_questions == expected["set_questions"]
    assert result.audit_files == expected["audit_files"]
    assert result.attempts_total == expected["attempts_total"]
    actual_codes = sorted(
        {
            violation["code"]
            for payload in result.regeneration_payloads
            for key in (
                "machine_violations",
                "review_violations",
                "set_check_violations",
            )
            for violation in payload.get(key, [])
        }
    )
    assert actual_codes == expected["regeneration_payload_checks"]


def test_rpl_01_all_gen1_pass(tmp_path: Path) -> None:
    """RPL-01: 3問gen1合格を実CLIで確定し完全な監査目録を残す。"""

    path, scenario = run("rpl_01_all_gen1_pass")
    with replay_scenario(path, tmp_path) as (result, set_dir):
        assert_expected(result, scenario)
        assert (set_dir / "set.json").is_file()
        assert set_dir.parent != ROOT / "output"
        assert not (ROOT / "output" / "20990101-000000-rpl1").exists()


def test_rpl_02_review_regeneration_payload(tmp_path: Path) -> None:
    """RPL-02: gen1レビュー指摘の全フィールドをgen2再指示へ渡す。"""

    path, scenario = run("rpl_02_regenerate_then_pass")
    with replay_scenario(path, tmp_path) as (result, set_dir):
        assert_expected(result, scenario)
        payload = result.regeneration_payloads[0]
        violation = payload["review_violations"][0]
        assert set(violation) == {
            "actual_level", "code", "evidence", "expected_level", "location", "suggestion"
        }
        assert payload["previous_candidate"]["question_id"] == "q01"
        assert payload["machine_violations"] == []
        assert payload["set_check_violations"] == []


def test_rpl_03_proposal_replacement(tmp_path: Path) -> None:
    """RPL-03: N=3のq01失敗時に補充q04を未処理q02より先に処理する。"""

    path, scenario = run("rpl_03_proposal_replacement")
    with replay_scenario(path, tmp_path) as (result, set_dir):
        assert_expected(result, scenario)
        assert result.set_questions == ["q02", "q03", "q04"]
        assert result.provider_requests[6:8] == [
            ("candidate", "q04", "gen1"),
            ("review", "q04", "gen1"),
        ]
        assert result.provider_requests[8:10] == [
            ("candidate", "q02", "gen1"),
            ("review", "q02", "gen1"),
        ]
        slot = load_json(set_dir / "review" / "slot.q01.outcome.json")
        assert slot["attempted_question_ids"] == ["q01", "q04"]
        assert slot["accepted_question_id"] == "q04"


def test_rpl_04_explicit_teacher_consult(tmp_path: Path) -> None:
    """RPL-04: 明示モードは3世代fail後に自動代替せず教師照会する。"""

    path, scenario = run("rpl_04_explicit_consult")
    with replay_scenario(path, tmp_path) as (result, set_dir):
        assert_expected(result, scenario)
        assert not (set_dir / "set.json").exists()
        assert len(result.regeneration_payloads) == 2
        assert result.consultation is not None
        assert len(result.consultation["generations"]) == 3
        assert len(result.consultation["failed_targets"]) == 1
        assert result.consultation["choices"] == ["alternative", "abort"]
        assert all(item["audit_files"] for item in result.consultation["generations"])
        assert result.consultation["accepted_count"] == 0
        assert result.consultation["target_attempts_total"] == 1
        assert not [request for request in result.provider_requests if request[1] == "q02"]
    alternative = machine_for_path(
        FIXTURES / "candidates" / "replay_q02_pass.json",
        "20990101-000000-rpl1",
        requested_count=1,
    )
    assert alternative.returncode == 0
    assert not [item for item in stdout_json(alternative)["violations"] if item["code"] == "V-COND-01"]


@pytest.mark.parametrize(
    "name",
    ("rpl_05_review_invalid_json", "rpl_05_review_invalid_schema", "rpl_05_review_invalid_surrogate"),
)
def test_rpl_05_review_infrastructure_failure(name: str, tmp_path: Path) -> None:
    """RPL-05: レビュー受理失敗3回をinvalid監査へ残し世代failにせず中止する。"""

    path, scenario = run(name)
    with replay_scenario(path, tmp_path) as (result, set_dir):
        assert_expected(result, scenario)
        assert not (set_dir / "set.json").exists()
        assert result.generation_verdicts[0]["verdict"] == "aborted"
        invalids = sorted((set_dir / "review").glob("*.review.invalid*.txt"))
        assert len(invalids) == 3
        kinds = {load_json(path)["kind"] for path in invalids}
        expected_kind = "utf8_encode_failure" if name.endswith("surrogate") else "validation_failure"
        assert kinds == {expected_kind}
        assert set_dir.parent != ROOT / "output"
        assert not (ROOT / "output" / "20990101-000000-rpl1").exists()


def test_rpl_06_candidate_retry_and_generation_consumption(tmp_path: Path) -> None:
    """RPL-06: candidate同一世代再指示1回後にgen1を消費してgen2へ進む。"""

    path, scenario = run("rpl_06_candidate_invalid")
    with replay_scenario(path, tmp_path) as (result, set_dir):
        assert_expected(result, scenario)
        assert (set_dir / "review" / "q01.gen1.candidate.invalid1.txt").is_file()
        assert (set_dir / "review" / "q01.gen1.candidate.invalid2.txt").is_file()
        assert not (set_dir / "review" / "q01.gen1.candidate.json").exists()
        assert set(result.regeneration_payloads[0]) == {
            "candidate_validation_diagnostic", "generation", "question_id"
        }


def test_rpl_07_machine_failure_cannot_be_overridden(tmp_path: Path) -> None:
    """RPL-07: machine failとreview passの集約結果をfailのまま保つ。"""

    path, scenario = run("rpl_07_machine_fail_review_pass")
    with replay_scenario(path, tmp_path) as (result, set_dir):
        assert_expected(result, scenario)
        assert result.generation_verdicts[0]["verdict"] == "fail"
        assert "V-LEX-02" in {
            item["code"] for item in result.generation_verdicts[0]["violations"]
        }
        assert not (set_dir / "set.json").exists()


def test_rpl_08_set_conflict_then_regeneration(tmp_path: Path) -> None:
    """RPL-08: 例文使い回しを増分set_checkでfailしgen2で解消する。"""

    path, scenario = run("rpl_08_set_conflict")
    with replay_scenario(path, tmp_path) as (result, _set_dir):
        assert_expected(result, scenario)
        assert any(
            item["reason"] == "set_check"
            and "V-SET-02" in {violation["code"] for violation in item["violations"]}
            for item in result.generation_verdicts
        )


def test_rpl_09_audit_and_canonical_independence(tmp_path: Path) -> None:
    """RPL-09: setの全監査参照が実在し問題内容は正本単体で完結する。"""

    path, scenario = run("rpl_09_audit_integrity")
    with replay_scenario(path, tmp_path) as (result, set_dir):
        assert_expected(result, scenario)
        for question in result.set_document["questions"]:
            provenance = question["provenance"]
            for key in ("candidate_ref", "machine_report_ref", "review_ref"):
                assert (set_dir / provenance[key]).is_file()
            standalone = {key: value for key, value in question.items() if key != "provenance"}
            assert standalone["body"] and standalone["target"]


def test_rpl_10_worst_case_cost_bound(tmp_path: Path) -> None:
    """RPL-10: N=3で減数判断後も続行し6対象×3世代で停止する。"""

    path, scenario = run("rpl_10_worst_case_bound")
    with replay_scenario(path, tmp_path) as (result, set_dir):
        assert_expected(result, scenario)
        assert result.attempts_total == 6 * 3
        assert {item["question_id"] for item in result.generation_verdicts} == {
            "q01", "q02", "q03", "q04", "q05", "q06"
        }
        assert [
            question_id
            for boundary, question_id, _generation in result.provider_requests
            if boundary == "candidate"
        ] == [
            "q01", "q01", "q01",
            "q04", "q04", "q04",
            "q05", "q05", "q05",
            "q06", "q06", "q06",
            "q02", "q02", "q02",
            "q03", "q03", "q03",
        ]
        assert not [request for request in result.provider_requests if request[1] == "q07"]
        assert result.teacher_decisions == scenario["teacher_decisions"]
        assert result.consultation is not None
        assert len(result.consultation["generations"]) == 3
        assert len(result.consultation["failed_targets"]) == 1
        assert result.consultation["slot_question_id"] == "q03"
        assert result.consultation["target_attempts_total"] == 6
        assert result.consultation["target_attempt_limit"] == 6
        assert result.consultation["choices"] == ["abort"]
        for slot_id in ("q01", "q02"):
            outcome = load_json(set_dir / "review" / f"slot.{slot_id}.outcome.json")
            assert outcome["status"] == "reduced"
            assert outcome["teacher_decision"] == "reduce"
        assert not list((set_dir / "review").glob("q07.*"))
        assert not (set_dir / "set.json").exists()


def test_replay_scenario_contracts() -> None:
    """RPL-01〜10: scenario IDと全必須フィールド・candidate_retriesを固定する。"""

    for path in SCENARIOS.glob("*.json"):
        scenario = load_json(path)
        assert re.fullmatch(r"rpl_[0-9]{2}_[a-z0-9_]+", scenario["scenario_id"])
        assert set(scenario) == {
            "description",
            "expected",
            "request",
            "scenario_id",
            "steps",
            "teacher_decisions",
        }
        assert all(
            set(step) == {"candidate", "candidate_retries", "gen", "question_id", "review", "review_retries"}
            for step in scenario["steps"]
        )
        for event in scenario["teacher_decisions"]:
            assert set(event) == {"decision", "slot_question_id", "target_ref"}
            assert event["decision"] in {"alternative", "reduce", "abort"}
            assert re.fullmatch(r"q(?:0[1-9]|1[0-9]|20)", event["slot_question_id"])
            if event["decision"] == "alternative":
                assert isinstance(event["target_ref"], str) and event["target_ref"]
            else:
                assert event["target_ref"] is None
