from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from tests.support import FIXTURES, GOLDEN, ROOT, canonical_bytes, load_json, machine_for_path


def indexed_files(directory: Path) -> set[str]:
    return {item["file"] for item in load_json(directory / "index.json")["cases"]}


def actual_json_files(directory: Path) -> set[str]:
    return {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*.json")
        if path != directory / "index.json"
    }


def test_ci_fix_01_indexes_are_complete() -> None:
    """CI-FIX-01: 必須4 index.jsonが配下の全fixtureを過不足なく登録する。"""

    for directory in (
        FIXTURES / "candidates",
        FIXTURES / "reviews",
        FIXTURES / "machine",
        FIXTURES / "schemas" / "invalid",
    ):
        index = load_json(directory / "index.json")
        assert set(index) == {"cases"}
        assert indexed_files(directory) == actual_json_files(directory)
        for case in index["cases"]:
            assert set(case) == {"expected", "file", "purpose", "test_ids"}
            assert case["purpose"] and case["expected"] and case["test_ids"]


def test_ci_fix_01_fixture_canonical_form() -> None:
    """CI-FIX-01: JSON fixtureをUTF-8・BOMなし・LF・正準インデントで保存する。"""

    intentional_raw = {
        FIXTURES / "reviews" / "invalid_json.json",
        FIXTURES / "reviews" / "invalid_surrogate.json",
    }
    huge = set((FIXTURES / "candidates").glob("mch_18_integer_*.json"))
    for path in FIXTURES.rglob("*.json"):
        payload = path.read_bytes()
        assert not payload.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in payload
        assert payload.endswith(b"\n") and not payload.endswith(b"\n\n")
        if path in intentional_raw or path in huge:
            continue
        assert payload == canonical_bytes(json.loads(payload))
    for path in huge:
        text = path.read_text(encoding="utf-8")
        assert text.startswith("{\n") and text.endswith("\n}\n")
        assert '\n  "unexpected_m8_integer": ' in text


def test_ci_fix_01_candidate_and_review_schema_contracts() -> None:
    """CI-FIX-01: 意図した不当例以外の候補・レビューfixtureが各スキーマに合格する。"""

    candidate_validator = Draft202012Validator(load_json(ROOT / "schemas" / "candidate.schema.json"))
    review_validator = Draft202012Validator(load_json(ROOT / "schemas" / "review_result.schema.json"))
    for case in load_json(FIXTURES / "candidates" / "index.json")["cases"]:
        path = FIXTURES / "candidates" / case["file"]
        if "意図した" in case["purpose"] or path.name.startswith("mch_18_integer_"):
            continue
        candidate_validator.validate(load_json(path))
    for case in load_json(FIXTURES / "reviews" / "index.json")["cases"]:
        if "意図した" in case["purpose"]:
            continue
        review_validator.validate(load_json(FIXTURES / "reviews" / case["file"]))


def test_ci_fix_01_no_personal_fixture_data() -> None:
    """CI-FIX-01: fixtureとgolden caseに個人メールアドレスを含めない。"""

    email = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    paths = [*FIXTURES.rglob("*"), *(GOLDEN / "cases").glob("*.json")]
    assert not [path for path in paths if path.is_file() and email.search(path.read_bytes())]


def test_ci_fix_01_golden_cases_machine_pass() -> None:
    """CI-FIX-01: GLD-05の2候補がcandidateスキーマとmachine検査に合格する。"""

    validator = Draft202012Validator(load_json(ROOT / "schemas" / "candidate.schema.json"))
    for path in sorted((GOLDEN / "cases").glob("*.candidate.json")):
        validator.validate(load_json(path))
        completed = machine_for_path(path, "20990101-090909-fix1")
        assert completed.returncode == 0, completed.stderr.decode()
        assert json.loads(completed.stdout)["verdict"] == "pass"
