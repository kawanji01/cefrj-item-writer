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
            for violation in payload["violations"]
        }
    )
    assert actual_codes == expected["regeneration_payload_checks"]


def test_rpl_01_all_gen1_pass() -> None:
    """RPL-01: 3問gen1合格を実CLIで確定し完全な監査目録を残す。"""

    path, scenario = run("rpl_01_all_gen1_pass")
    with replay_scenario(path) as (result, set_dir):
        assert_expected(result, scenario)
        assert (set_dir / "set.json").is_file()


def test_rpl_02_review_regeneration_payload() -> None:
    """RPL-02: gen1レビュー指摘の全フィールドをgen2再指示へ渡す。"""

    path, scenario = run("rpl_02_regenerate_then_pass")
    with replay_scenario(path) as (result, _set_dir):
        assert_expected(result, scenario)
        violation = result.regeneration_payloads[0]["violations"][0]
        assert set(violation) == {
            "actual_level", "code", "evidence", "expected_level", "location", "suggestion"
        }


def test_rpl_03_proposal_replacement() -> None:
    """RPL-03: 提案モードで3世代fail後にq02を補充して確定する。"""

    path, scenario = run("rpl_03_proposal_replacement")
    with replay_scenario(path) as (result, _set_dir):
        assert_expected(result, scenario)
        assert result.set_questions == ["q02"]
        assert all(int(item["question_id"][1:]) <= 2 for item in result.generation_verdicts)


def test_rpl_04_explicit_teacher_consult() -> None:
    """RPL-04: 明示モードは3世代fail後に自動代替せず教師照会する。"""

    path, scenario = run("rpl_04_explicit_consult")
    with replay_scenario(path) as (result, set_dir):
        assert_expected(result, scenario)
        assert not (set_dir / "set.json").exists()
        assert len(result.regeneration_payloads) == 2
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
def test_rpl_05_review_infrastructure_failure(name: str) -> None:
    """RPL-05: レビュー受理失敗3回をinvalid監査へ残し世代failにせず中止する。"""

    path, scenario = run(name)
    with replay_scenario(path) as (result, set_dir):
        assert_expected(result, scenario)
        assert not (set_dir / "set.json").exists()
        assert result.generation_verdicts[0]["verdict"] == "aborted"
        invalids = sorted((set_dir / "review").glob("*.review.invalid*.txt"))
        assert len(invalids) == 3
        kinds = {load_json(path)["kind"] for path in invalids}
        expected_kind = "utf8_encode_failure" if name.endswith("surrogate") else "validation_failure"
        assert kinds == {expected_kind}


def test_rpl_06_candidate_retry_and_generation_consumption() -> None:
    """RPL-06: candidate同一世代再指示1回後にgen1を消費してgen2へ進む。"""

    path, scenario = run("rpl_06_candidate_invalid")
    with replay_scenario(path) as (result, set_dir):
        assert_expected(result, scenario)
        assert (set_dir / "review" / "q01.gen1.candidate.invalid1.txt").is_file()
        assert (set_dir / "review" / "q01.gen1.candidate.invalid2.txt").is_file()
        assert not (set_dir / "review" / "q01.gen1.candidate.json").exists()


def test_rpl_07_machine_failure_cannot_be_overridden() -> None:
    """RPL-07: machine failとreview passの集約結果をfailのまま保つ。"""

    path, scenario = run("rpl_07_machine_fail_review_pass")
    with replay_scenario(path) as (result, set_dir):
        assert_expected(result, scenario)
        assert result.generation_verdicts[0]["verdict"] == "fail"
        assert "V-LEX-02" in {
            item["code"] for item in result.generation_verdicts[0]["violations"]
        }
        assert not (set_dir / "set.json").exists()


def test_rpl_08_set_conflict_then_regeneration() -> None:
    """RPL-08: 例文使い回しを増分set_checkでfailしgen2で解消する。"""

    path, scenario = run("rpl_08_set_conflict")
    with replay_scenario(path) as (result, _set_dir):
        assert_expected(result, scenario)
        assert any(
            item["reason"] == "set_check"
            and "V-SET-02" in {violation["code"] for violation in item["violations"]}
            for item in result.generation_verdicts
        )


def test_rpl_09_audit_and_canonical_independence() -> None:
    """RPL-09: setの全監査参照が実在し問題内容は正本単体で完結する。"""

    path, scenario = run("rpl_09_audit_integrity")
    with replay_scenario(path) as (result, set_dir):
        assert_expected(result, scenario)
        for question in result.set_document["questions"]:
            provenance = question["provenance"]
            for key in ("candidate_ref", "machine_report_ref", "review_ref"):
                assert (set_dir / provenance[key]).is_file()
            standalone = {key: value for key, value in question.items() if key != "provenance"}
            assert standalone["body"] and standalone["target"]


def test_rpl_10_worst_case_cost_bound() -> None:
    """RPL-10: N=3でq01〜q06の18世代試行を上限として停止する。"""

    path, scenario = run("rpl_10_worst_case_bound")
    with replay_scenario(path) as (result, set_dir):
        assert_expected(result, scenario)
        assert result.attempts_total == min(2 * 3, 20) * 3
        assert {item["question_id"] for item in result.generation_verdicts} == {
            f"q{number:02d}" for number in range(1, 7)
        }
        assert not (set_dir / "set.json").exists()


def test_replay_scenario_contracts() -> None:
    """RPL-01〜10: scenario IDと全必須フィールド・candidate_retriesを固定する。"""

    for path in SCENARIOS.glob("*.json"):
        scenario = load_json(path)
        assert re.fullmatch(r"rpl_[0-9]{2}_[a-z0-9_]+", scenario["scenario_id"])
        assert set(scenario) == {"description", "expected", "request", "scenario_id", "steps"}
        assert all(
            set(step) == {"candidate", "candidate_retries", "gen", "question_id", "review", "review_retries"}
            for step in scenario["steps"]
        )
