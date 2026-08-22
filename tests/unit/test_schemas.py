from __future__ import annotations

import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tests.support import FIXTURES, GOLDEN, OFFICIAL_FORMATS, ROOT, load_json, run_cli, stderr_json


SCHEMA_NAMES = (
    "set",
    "candidate",
    "machine_report",
    "review_request",
    "review_result",
    "normalized_lexicon",
    "normalized_grammar",
    "config_limits",
    "config_proper_nouns",
)


def test_ci_sch_01_metaschema_and_ids() -> None:
    """CI-SCH-01: 9スキーマをDraft 2020-12メタスキーマと$id規則で検証する。"""

    for name in SCHEMA_NAMES:
        schema = load_json(ROOT / "schemas" / f"{name}.schema.json")
        Draft202012Validator.check_schema(schema)
        assert re.fullmatch(
            rf"https://cefr-j-agents\.local/schemas/{name}/[0-9]+\.[0-9]+\.[0-9]+",
            schema["$id"],
        )


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_ci_sch_02_valid_examples(name: str) -> None:
    """CI-SCH-02: 9スキーマの妥当例をvalidate CLIが受理する。"""

    if name == "set":
        paths = [GOLDEN / "sets" / f"{fmt}.set.json" for fmt in OFFICIAL_FORMATS]
    else:
        paths = [FIXTURES / "schemas" / "valid" / name / "valid.json"]
    assert paths
    for path in paths:
        completed = run_cli(
            "scripts/validate.py",
            "--schema",
            name,
            "--file",
            str(path.relative_to(ROOT)),
        )
        assert completed.returncode == 0, completed.stderr.decode()


@pytest.mark.parametrize(
    "case",
    [
        item
        for item in load_json(FIXTURES / "schemas" / "invalid" / "index.json")["cases"]
        if "CI-SCH-03" in item["test_ids"]
    ],
    ids=lambda item: item["file"],
)
def test_ci_sch_03_invalid_examples(case: dict[str, object]) -> None:
    """CI-SCH-03: 各スキーマの必須欠落・型不正・追加属性を違反パス付きで拒否する。"""

    schema = str(case["file"]).split("/", 1)[0]
    completed = run_cli(
        "scripts/validate.py",
        "--schema",
        schema,
        "--file",
        f"tests/fixtures/schemas/invalid/{case['file']}",
    )
    assert completed.returncode == 1
    error = stderr_json(completed)
    assert error["error_code"] == "E-CONTRACT-01"
    assert error["detail"]["errors"]
    assert all("json_pointer" in item for item in error["detail"]["errors"])


def test_ci_sch_04_format_union() -> None:
    """CI-SCH-04: candidateの9形式共用体を受理しformat/body不整合を拒否する。"""

    for fmt in OFFICIAL_FORMATS:
        path = FIXTURES / "candidates" / f"official_{fmt}.json"
        completed = run_cli(
            "scripts/validate.py",
            "--schema",
            "candidate",
            "--file",
            str(path.relative_to(ROOT)),
        )
        assert completed.returncode == 0, path.name
    invalid = run_cli(
        "scripts/validate.py",
        "--schema",
        "candidate",
        "--file",
        "tests/fixtures/candidates/sch_04_inconsistent_format.json",
    )
    assert invalid.returncode == 1
    assert stderr_json(invalid)["error_code"] == "E-CONTRACT-01"


@pytest.mark.parametrize(
    "case",
    [
        item
        for item in load_json(FIXTURES / "schemas" / "invalid" / "index.json")["cases"]
        if "CI-SCH-05" in item["test_ids"]
    ],
    ids=lambda item: item["file"],
)
def test_ci_sch_05_identifier_formats(case: dict[str, object]) -> None:
    """CI-SCH-05: set/question/generation/entry IDの不当値を拒否する。"""

    schema = str(case["file"]).split("/", 1)[0]
    completed = run_cli(
        "scripts/validate.py",
        "--schema",
        schema,
        "--file",
        f"tests/fixtures/schemas/invalid/{case['file']}",
    )
    assert completed.returncode == 1
    assert stderr_json(completed)["error_code"] == "E-CONTRACT-01"
