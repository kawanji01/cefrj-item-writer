from __future__ import annotations

import json
import sys

import pytest
from jsonschema import Draft202012Validator

from tests.support import (
    FIXTURES,
    ROOT,
    canonical_bytes,
    load_json,
    machine_for_path,
    run_cli,
    stderr_json,
    stdout_json,
    strip_generated_at,
)

sys.path.insert(0, str(ROOT / "scripts"))
from machine_check import POS_CANDIDATES


SET_ID = "20990101-020202-mch1"


def report(name: str, **kwargs: object) -> dict[str, object]:
    completed = machine_for_path(FIXTURES / "candidates" / name, SET_ID, **kwargs)
    assert completed.returncode == 0, completed.stderr.decode()
    return stdout_json(completed)


def codes(value: dict[str, object]) -> list[str]:
    return [violation["code"] for violation in value["violations"]]  # type: ignore[index]


def test_ci_mch_01_word_limit_violation() -> None:
    """CI-MCH-01: A1の11トークン例文をV-LEN-01で拒否する。"""

    value = report("mch_01_word_limit_11.json")
    assert value["verdict"] == "fail"
    assert "V-LEN-01" in codes(value)


def test_ci_mch_02_word_limit_boundary() -> None:
    """CI-MCH-02: A1の10トークン境界にはV-LEN-01を出さない。"""

    assert "V-LEN-01" not in codes(report("mch_02_word_limit_10.json"))


def test_ci_mch_03_unknown_word() -> None:
    """CI-MCH-03: allowlist外Helsinkiを辞書外語として検出する。"""

    value = report("mch_03_unknown_helsinki.json")
    violations = [item for item in value["violations"] if item["code"] == "V-LEX-01"]
    assert value["verdict"] == "fail"
    assert any("Helsinki" in item["location"] for item in violations)


def test_ci_mch_04_allowlisted_proper_noun() -> None:
    """CI-MCH-04: allowlist内Kyotoを辞書外違反にしない。"""

    value = report("mch_04_allowlist_kyoto.json")
    assert not [item for item in value["violations"] if item["code"] == "V-LEX-01"]


def test_ci_mch_05_mechanical_exemptions() -> None:
    """CI-MCH-05: 数字・記号・句読点・縮約を規則どおり免除・展開する。"""

    value = report("mch_05_exemptions.json")
    tokens = value["stats"]["texts"][0]["tokens"]
    assert not [item for item in value["violations"] if item["code"] in {"V-LEX-01", "V-LEX-02"}]
    assert any(token["surface"] == "2" and token["decision"] == "exempt" for token in tokens)
    assert any(token["surface"].lower() == "ca" and token["lemma"] == "can" for token in tokens)


def test_ci_mch_06_high_level_word() -> None:
    """CI-MCH-06: A1例文中のB1 abandonをレベル超過として列挙する。"""

    value = report("mch_06_high_level_abandon.json")
    matches = [item for item in value["violations"] if item["code"] == "V-LEX-02"]
    assert any(
        "abandon" in item["location"]
        and item["expected_level"] == "A1"
        and item["actual_level"] == "B1"
        for item in matches
    )


@pytest.mark.parametrize(
    ("name", "expected_verdict", "has_target_violation"),
    [
        ("mch_07_target_zero.json", "fail", True),
        ("mch_07_target_twice.json", "fail", True),
        ("mch_07_target_inflected.json", "pass", False),
    ],
)
def test_ci_mch_07_target_occurrence(
    name: str, expected_verdict: str, has_target_violation: bool
) -> None:
    """CI-MCH-07: 対象語0回・2回を拒否し活用形1回を受理する。"""

    value = report(name)
    assert value["verdict"] == expected_verdict
    assert ("V-TGT-02" in codes(value)) is has_target_violation


def test_ci_mch_08_multiword_longest_match() -> None:
    """CI-MCH-08: CD playerを最長一致し構成語単体の違反を出さない。"""

    value = report("mch_08_multiword_cd_player.json")
    assert not [item for item in value["violations"] if item["code"] in {"V-LEX-01", "V-LEX-02"}]
    tokens = value["stats"]["texts"][0]["tokens"]
    assert any(token["matched_entry_id"] == "lex:CD player:noun" for token in tokens)


def test_ci_mch_09_pos_mapping_table() -> None:
    """CI-MCH-09: spaCyタグからWordlist 15品詞への対応表全行を固定する。"""

    expected = {
        "NN": ("noun",), "NNS": ("noun",), "NNP": ("noun",), "NNPS": ("noun",),
        "JJ": ("adjective",), "JJR": ("adjective",), "JJS": ("adjective",),
        "VB": ("verb",), "VBP": ("verb",), "VBZ": ("verb",), "VBD": ("verb",),
        "VBN": ("verb",), "VBG": ("verb",), "MD": ("modal auxiliary",),
        "RB": ("adverb",), "RBR": ("adverb",), "RBS": ("adverb",), "WRB": ("adverb",),
        "PRP": ("pronoun",), "PRP$": ("pronoun",), "WP": ("pronoun",), "WP$": ("pronoun",),
        "DT": ("determiner", "pronoun"), "PDT": ("determiner", "pronoun"),
        "WDT": ("determiner", "pronoun"), "IN": ("preposition", "conjunction"),
        "CC": ("conjunction",), "CD": ("number",), "UH": ("interjection",),
        "EX": ("adverb", "pronoun"), "RP": ("adverb", "preposition"),
    }
    assert POS_CANDIDATES == expected
    assert set().union(*map(set, POS_CANDIDATES.values())) == {
        "noun", "adjective", "verb", "modal auxiliary", "adverb", "pronoun",
        "determiner", "preposition", "conjunction", "number", "interjection",
    }


def test_ci_mch_10_distractor_provenance() -> None:
    """CI-MCH-10: 誤答アンカーの正規化データ矛盾をV-DIS-01で検出する。"""

    value = report("mch_10_bad_anchor.json")
    assert value["verdict"] == "fail"
    assert "V-DIS-01" in codes(value)


@pytest.mark.parametrize(
    ("name", "has_violation"),
    [
        ("mch_11_same_pos.json", False),
        ("mch_11_relaxed_number.json", False),
        ("mch_11_missing_relax_flag.json", True),
    ],
)
def test_ci_mch_11_distractor_pool(name: str, has_violation: bool) -> None:
    """CI-MCH-11: 同品詞プール・互換品詞緩和・緩和記録を検証する。"""

    value = report(name)
    assert ("V-DIS-02" in codes(value)) is has_violation


def test_ci_mch_12_machine_report_schema() -> None:
    """CI-MCH-12: machine stdoutをjsonschema直接検証とvalidate CLIで再検証する。"""

    completed = machine_for_path(FIXTURES / "candidates" / "compat" / "grammar_cloze.json", SET_ID)
    assert completed.returncode == 0
    value = stdout_json(completed)
    Draft202012Validator(load_json(ROOT / "schemas" / "machine_report.schema.json")).validate(value)
    validated = run_cli(
        "scripts/validate.py", "--schema", "machine_report", "--file", "-", stdin=completed.stdout
    )
    assert validated.returncode == 0, validated.stderr.decode()


@pytest.mark.parametrize(
    ("name", "has_violation"),
    [
        ("mch_13_context_recorded.json", False),
        ("mch_13_context_missing_record.json", True),
    ],
)
def test_ci_mch_13_context_pair(name: str, has_violation: bool) -> None:
    """CI-MCH-13: 先行文脈と要求元記録の組を検査する。"""

    assert ("V-SENT-01" in codes(report(name))) is has_violation


def test_ci_mch_14_reorder_shuffle() -> None:
    """CI-MCH-14: 正解順と同一の整序提示順を拒否する。"""

    value = report("mch_14_reorder_same.json")
    assert value["verdict"] == "fail"
    assert "V-ORD-02" in codes(value)


def test_ci_mch_15_machine_determinism() -> None:
    """CI-MCH-15: generated_at除去後のmachine出力が2回でバイト一致する。"""

    path = FIXTURES / "candidates" / "compat" / "grammar_cloze.json"
    first = machine_for_path(path, SET_ID)
    second = machine_for_path(path, SET_ID)
    assert first.returncode == second.returncode == 0
    assert strip_generated_at(first.stdout) == strip_generated_at(second.stdout)


def test_ci_mch_16_set_conditions() -> None:
    """CI-MCH-16: format・level・試行ID上限とq20境界を検査する。"""

    base = FIXTURES / "candidates" / "mch_16_condition_match.json"
    assert "V-COND-01" not in codes(report("mch_16_condition_match.json"))
    format_bad = machine_for_path(base, SET_ID, expected_format="grammar_mcq", expected_level="A1.2")
    level_bad = machine_for_path(base, SET_ID, expected_level="A1.1")
    supplement = report("mch_16_supplement_q04.json", requested_count=3)
    over = report("mch_16_over_limit_q07.json", requested_count=3)
    q20 = report("mch_16_upper_bound_q20.json", requested_count=20)
    for completed, location in ((format_bad, "format"), (level_bad, "level")):
        value = stdout_json(completed)
        assert any(item["code"] == "V-COND-01" and item["location"] == location for item in value["violations"])
    assert "V-COND-01" not in codes(supplement)
    assert "V-COND-01" in codes(over)
    assert "V-COND-01" not in codes(q20)


@pytest.mark.parametrize(
    ("name", "expected_format", "expected_level", "expected_codes"),
    [
        ("mch_17_expected_a1_abandon.json", "vocab_flashcard_en2ja", "A1", {"V-COND-01", "V-LEN-01", "V-LEX-02", "V-TGT-03"}),
        ("mch_17_expected_a11_grammar.json", "grammar_example_selfcheck", "A1.1", {"V-COND-01", "V-TGT-01"}),
        ("mch_17_expected_a1_distractors.json", "vocab_mcq_ja2en", "A1", {"V-COND-01", "V-DIS-02"}),
    ],
)
def test_ci_mch_17_expected_level_enumeration(
    name: str, expected_format: str, expected_level: str, expected_codes: set[str]
) -> None:
    """CI-MCH-17: 候補値でなく期待レベル基準の違反を全件列挙する。"""

    value = report(name, expected_format=expected_format, expected_level=expected_level)
    assert expected_codes <= set(codes(value))


def test_ci_mch_18_integer_digit_limit() -> None:
    """CI-MCH-18: candidate整数を4,300桁まで許し超過を決定的に拒否する。"""

    def raw(digits: int, env: dict[str, str] | None = None):
        return run_cli(
            "scripts/machine_check.py",
            "--candidate",
            f"tests/fixtures/candidates/mch_18_integer_{digits}.json",
            "--set-id", SET_ID,
            "--generation", "gen1",
            "--expected-format", "grammar_cloze",
            "--expected-level", "A1.2",
            "--requested-count", "1",
            env=env,
        )

    boundary = raw(4300)
    assert boundary.returncode == 1
    assert stderr_json(boundary)["error_code"] == "E-CONTRACT-01"
    over = raw(4301)
    assert over.returncode == 1
    over_error = stderr_json(over)
    assert over_error["error_code"] == "E-INPUT-03"
    assert over_error["detail"]["digit_count"] == 4301
    first = raw(5000, {"PYTHONINTMAXSTRDIGITS": "4300"})
    second = raw(5000, {"PYTHONINTMAXSTRDIGITS": "0"})
    assert first.returncode == second.returncode == 1
    assert first.stderr == second.stderr
    error = stderr_json(first)
    assert error["detail"]["digit_limit"] == 4300
    assert error["detail"]["digit_count"] == 5000


def test_ci_lkp_01_level_lookup() -> None:
    """CI-LKP-01: abandon全品詞とA1不一致を終了コード0で返す。"""

    all_levels = run_cli("scripts/lookup.py", "lex", "--headword", "abandon")
    a1 = run_cli("scripts/lookup.py", "lex", "--headword", "abandon", "--level", "A1")
    assert all_levels.returncode == a1.returncode == 0
    assert any(item["pos"] == "verb" and item["level"] == "B1" for item in stdout_json(all_levels)["matches"])
    assert stdout_json(a1) == {"matches": [], "total": 0}


def test_ci_lkp_02_unknown_headword() -> None:
    """CI-LKP-02: TokyoをWordlist非収録として返す。"""

    completed = run_cli("scripts/lookup.py", "lex", "--headword", "Tokyo")
    assert completed.returncode == 0
    assert stdout_json(completed) == {"matches": [], "total": 0}


def test_ci_lkp_03_ambiguous_pos() -> None:
    """CI-LKP-03: watchの全品詞候補を返す。"""

    completed = run_cli("scripts/lookup.py", "lex", "--headword", "watch")
    assert completed.returncode == 0
    assert {(item["headword"], item["pos"], item["level"]) for item in stdout_json(completed)["matches"]} == {
        ("watch", "noun", "A1"), ("watch", "verb", "A1")
    }


def test_ci_lkp_04_grammar_lookup_and_inheritance() -> None:
    """CI-LKP-04: gp:13とgp:1-1の教員版情報・略記・継承を返す。"""

    direct = stdout_json(run_cli("scripts/lookup.py", "gp", "--id", "gp:13"))["matches"][0]
    branch = stdout_json(run_cli("scripts/lookup.py", "gp", "--id", "gp:1-1"))["matches"][0]
    assert direct["kyoinban"]["present"] is True
    assert direct["display_name"] and direct["item_list"]["pattern_shorthand"]
    assert branch["level"]["inherited_from"] == "gp:1"
    assert branch["level"]["min"] == "A1.1" and branch["level"]["max"] == "A1.2"
