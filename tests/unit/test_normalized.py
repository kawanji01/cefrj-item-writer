from __future__ import annotations

import collections
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import openpyxl

from tests.support import GOLDEN, ROOT, load_json, output_set, run_cli, stderr_json


def test_ci_nrm_01_build_is_deterministic() -> None:
    """CI-NRM-01: 原本からの2回の正規化出力がバイト一致する。"""

    with output_set("20990101-010101-nr01") as parent:
        first = parent / "first"
        second = parent / "second"
        for target in (first, second):
            completed = run_cli(
                "scripts/build_normalized.py",
                "--out-dir",
                str(target.relative_to(ROOT)),
            )
            assert completed.returncode == 0, completed.stderr.decode()
        for name in ("lexicon.json", "grammar.json", "meta.json"):
            assert (first / name).read_bytes() == (second / name).read_bytes()


def test_ci_nrm_02_normalized_checksums() -> None:
    """CI-NRM-02: コミット済み正規化データがチェックサムゴールデンと一致する。"""

    golden = load_json(GOLDEN / "normalized" / "checksums.json")
    meta = load_json(ROOT / "data" / "normalized" / "meta.json")
    assert golden["data_version"] == meta["data_version"]
    for name, expected in golden["files"].items():
        actual = hashlib.sha256((ROOT / "data" / "normalized" / name).read_bytes()).hexdigest()
        assert actual == expected


def test_ci_nrm_03_counts_and_relations() -> None:
    """CI-NRM-03: 語彙・文法の件数不変条件と原本行数を確認する。"""

    lexicon = load_json(ROOT / "data" / "normalized" / "lexicon.json")
    grammar = load_json(ROOT / "data" / "normalized" / "grammar.json")
    entries = lexicon["entries"]
    assert len(entries) == 7_988
    assert collections.Counter(entry["level"] for entry in entries) == {
        "A1": 1_200,
        "A2": 1_443,
        "B1": 2_486,
        "B2": 2_859,
    }
    assert len({(entry["headword"], entry["pos"]) for entry in entries}) == 7_988
    assert len(lexicon["groups"]) == 179
    assert all(len(group["member_ids"]) >= 2 for group in lexicon["groups"])

    source = next((ROOT / "data" / "source").glob("*Wordlist*.xlsx"))
    workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
    try:
        sheet = workbook["ALL"]
        assert sum(1 for row in sheet.iter_rows(min_row=2, values_only=True) if any(value is not None for value in row)) == 7_801
    finally:
        workbook.close()

    items = grammar["entries"]
    assert len(items) == 501
    assert sum(bool(item["kyoinban"]["present"]) for item in items) == 256
    ids = {item["id"] for item in items}
    assert all(item["parent_id"] is None or item["parent_id"] in ids for item in items)
    unassigned = sorted(
        int(item["item_list_id"])
        for item in items
        if "-" not in item["item_list_id"] and item["level"]["min"] is None
    )
    assert unassigned == [36, 47, 48, 52, 80, 83, 94, 96, 98, 115, 130, 191, 225, 226, 227, 238]


def test_ci_nrm_04_normalized_schemas_via_cli() -> None:
    """CI-NRM-04: 正規化2文書がvalidate CLIに合格する。"""

    for schema, name in (
        ("normalized_lexicon", "lexicon.json"),
        ("normalized_grammar", "grammar.json"),
    ):
        completed = run_cli(
            "scripts/validate.py",
            "--schema",
            schema,
            "--file",
            f"data/normalized/{name}",
        )
        assert completed.returncode == 0, completed.stderr.decode()


def test_ci_nrm_05_branch_level_inheritance() -> None:
    """CI-NRM-05: gp:1の枝番3件が親レベルを継承する。"""

    entries = {item["id"]: item for item in load_json(ROOT / "data" / "normalized" / "grammar.json")["entries"]}
    parent = entries["gp:1"]["level"]
    for child_id in ("gp:1-1", "gp:1-2", "gp:1-3"):
        child = entries[child_id]
        assert child["level"]["min"] == parent["min"]
        assert child["level"]["max"] == parent["max"]
        assert child["level"]["inherited_from"] == "gp:1"


def test_ci_nrm_06_source_checksum_mismatch(tmp_path: Path) -> None:
    """CI-NRM-06: 1バイト改変原本をbuildとdoctorがE-DATAで拒否する。"""

    clone = tmp_path / "repository"
    subprocess.run(
        ["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(clone)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    source = next((clone / "data" / "source").glob("*.xlsx"))
    source.write_bytes(source.read_bytes() + b"\x00")
    build = run_cli("scripts/build_normalized.py", cwd=clone)
    doctor = run_cli("scripts/doctor.py", cwd=clone)
    assert build.returncode == 1
    assert stderr_json(build)["error_code"] == "E-DATA-02"
    assert doctor.returncode == 1
    assert b"E-DATA-02" in doctor.stdout


def test_ci_nrm_07_teacher_level_decomposition() -> None:
    """CI-NRM-07: 教員版単一値152件・範囲値104件の分解を確認する。"""

    entries = load_json(ROOT / "data" / "normalized" / "grammar.json")["entries"]
    eligible = [item for item in entries if item["target_eligible"]]
    singles = [item for item in eligible if item["level"]["min"] == item["level"]["max"]]
    ranges = [item for item in eligible if item["level"]["min"] != item["level"]["max"]]
    assert len(singles) == 152
    assert len(ranges) == 104
    assert all(item["level"]["min"] and item["level"]["max"] for item in eligible)
