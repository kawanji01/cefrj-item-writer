#!/usr/bin/env python3
"""CEFR-J原本xlsxから正規化JSONを決定的に生成する。"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import re
import sys
import tempfile
import traceback
import unicodedata
import warnings
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


WORDLIST_FILE = "CEFR-J Wordlist Ver1.6.xlsx"
GRAMMAR_FILE = "CEFR-J Grammar Profile full 20200220.xlsx"
SOURCE_FILE_NAMES = (WORDLIST_FILE, GRAMMAR_FILE)
NORMALIZED_FILE_NAMES = ("lexicon.json", "grammar.json", "meta.json")
DATA_VERSION = "wl1.6+gp20200220+norm1.0.0"
PIPELINE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"
MODEL_NAME = "en_core_web_sm"
MODEL_VERSION = "3.8.0"

REQUIRED_PACKAGES = {
    "spacy": ("spacy", "3.8.15"),
    "openpyxl": ("openpyxl", "3.1.5"),
    "jsonschema": ("jsonschema", "4.26.0"),
    "Jinja2": ("jinja2", "3.1.6"),
}

SCHEMA_FILES = (
    "candidate.schema.json",
    "config_limits.schema.json",
    "config_proper_nouns.schema.json",
    "machine_report.schema.json",
    "normalized_grammar.schema.json",
    "normalized_lexicon.schema.json",
    "review_request.schema.json",
    "review_result.schema.json",
    "set.schema.json",
)

POS_VALUES = {
    "noun",
    "adjective",
    "verb",
    "adverb",
    "pronoun",
    "preposition",
    "determiner",
    "conjunction",
    "number",
    "modal auxiliary",
    "be-verb",
    "do-verb",
    "have-verb",
    "interjection",
    "infinitive-to",
}
CEFR_VALUES = {"A1", "A2", "B1", "B2"}
CEFRJ_RANK = {
    "A1.1": 1,
    "A1.2": 2,
    "A1.3": 3,
    "A2.1": 4,
    "A2.2": 5,
    "B1.1": 6,
    "B1.2": 7,
    "B2.1": 8,
    "B2.2": 9,
}
LEVEL_PATTERN = re.compile(
    r"^(A1\.[123]|A2\.[12]|B1\.[12]|B2\.[12])"
    r"(?:-(A1\.[123]|A2\.[12]|B1\.[12]|B2\.[12]))?$"
)
ID_PATTERN = re.compile(r"^[0-9]+(?:-[0-9]+)?$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

UNASSIGNED_PARENT_IDS = {
    "36",
    "47",
    "48",
    "52",
    "80",
    "83",
    "94",
    "96",
    "98",
    "115",
    "130",
    "191",
    "225",
    "226",
    "227",
    "238",
}

WORDLIST_HEADERS = (
    "headword",
    "pos",
    "CEFR",
    "CoreInventory 1",
    "CoreInventory 2",
    "Threshold",
)
ITEM_HEADERS_EXACT = {
    "ID",
    "文法項目",
    "文タイプ(不問のものは空欄)",
    "Shorthand Code",
    "Grammatical Item",
    "備考",
    "パターン略記",
}
TEACHER_HEADERS = (
    "ID",
    "文法項目",
    "文法項目 (平易版)",
    "Grammatical item (English)",
    "CEFR-J level",
    "A1.1",
    "A1.2",
    "A1.3",
    "A2.1",
    "A2.2",
    "B1.1",
    "B1.2",
    "B2.1",
    "B2.2",
)

REMEDIES = {
    "E-ENV-01": "Python 3.11以上をインストールし、python scripts/setup.py でvenvを再作成してください。",
    "E-ENV-02": "リポジトリルートで python scripts/setup.py を再実行してください。",
    "E-ENV-03": "リポジトリルートで python scripts/setup.py を再実行し、en_core_web_sm 3.8.0を取得してください。",
    "E-ENV-04": "リポジトリルートに移動してください。ファイル欠落時は git status で確認し git checkout で復元してください。",
    "E-DATA-01": "原本2ファイルを固定名でdata/source/に配置し、sources.jsonに入手URLとダウンロード日を記入してください。",
    "E-DATA-02": "意図的な原本更新は python scripts/build_normalized.py --diff で確認後、python scripts/build_normalized.py --accept-source-change を実行してください。意図しない場合は正しい原本を配置し直してください。",
    "E-DATA-03": "git checkoutで復元するか、python scripts/build_normalized.py を実行してください。",
    "E-DATA-04": "python scripts/build_normalized.py で再ビルドしてください。再発時は正規化パイプラインの不具合として報告してください。",
    "E-DATA-05": "git checkoutで設定を復元し、M3以降は python scripts/validate.py --schema config_limits --file data/config/limits.json で違反箇所を確認してください。",
    "E-DATA-06": "原本の版がWordlist Ver1.6とGrammar Profile full 20200220に一致するか確認してください。新版へ移行する場合はdocs/architecture.md OPS-01に従ってください。",
    "E-INPUT-01": "python scripts/build_normalized.py --help の日本語ヘルプを参照して引数を修正してください。",
    "E-INPUT-02": "指定パスの綴り・存在・読み取り権限を確認してください。",
}


class CliFailure(Exception):
    """定義済みCLIエラー。"""

    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        detail: Any = None,
        remedy: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.detail = detail
        self.remedy = remedy or REMEDIES[error_code]

    def as_dict(self) -> dict[str, Any]:
        return {
            "detail": self.detail,
            "error_code": self.error_code,
            "message": self.message,
            "remedy": self.remedy,
        }


class JapaneseArgumentParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        return (
            super()
            .format_help()
            .replace("usage:", "使用法:", 1)
            .replace("options:", "オプション:", 1)
            .replace("show this help message and exit", "このヘルプを表示して終了します", 1)
        )

    def error(self, message: str) -> None:
        translated = message
        if message.startswith("unrecognized arguments:"):
            translated = f"未知の引数です:{message.removeprefix('unrecognized arguments:')}"
        else:
            missing_value = re.fullmatch(r"argument (.+): expected one argument", message)
            if missing_value:
                translated = f"引数 {missing_value.group(1)} に値が必要です"
        raise CliFailure(
            "E-INPUT-01",
            f"E-INPUT-01 build_normalized.pyの引数が不正です: {translated}",
            detail={"parser_message": message},
        )


def canonical_json_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ) + "\n"


def emit_json(value: Any, stream: Any = sys.stdout) -> None:
    stream.write(canonical_json_text(value))


def load_json_file(path: Path, error_code: str = "E-DATA-04") -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CliFailure(
            error_code,
            f"{error_code} JSONを読み取れません: {path}",
            detail={"error": str(exc), "path": str(path)},
        ) from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CliFailure(
            "E-DATA-01",
            f"E-DATA-01 原本を読み取れません: {path.name}",
            detail={"error": str(exc), "path": str(path)},
        ) from exc
    return digest.hexdigest()


def json_pointer(path: Iterable[Any]) -> str:
    parts = []
    for part in path:
        parts.append(str(part).replace("~", "~0").replace("/", "~1"))
    return "/" + "/".join(parts) if parts else ""


def schema_errors(instance: Any, schema_path: Path) -> list[dict[str, str]]:
    try:
        jsonschema = importlib.import_module("jsonschema")
        schema = load_json_file(schema_path, "E-ENV-04")
        validator = jsonschema.Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.absolute_path))
    except CliFailure:
        raise
    except Exception as exc:
        raise CliFailure(
            "E-ENV-04",
            f"E-ENV-04 スキーマを検証器へ読み込めません: {schema_path}",
            detail={"error": str(exc), "path": str(schema_path)},
        ) from exc
    return [
        {"json_pointer": json_pointer(error.absolute_path), "message": error.message}
        for error in errors
    ]


def validate_against_schema(instance: Any, schema_path: Path, target: str) -> None:
    errors = schema_errors(instance, schema_path)
    if errors:
        raise CliFailure(
            "E-DATA-06",
            f"E-DATA-06 正規化結果が{target}スキーマに適合しません。",
            detail={"errors": errors[:50], "total_errors": len(errors)},
        )


def dependency_issues() -> list[dict[str, str | None]]:
    issues: list[dict[str, str | None]] = []
    for distribution, (module_name, required_version) in REQUIRED_PACKAGES.items():
        detected: str | None = None
        try:
            detected = importlib.metadata.version(distribution)
            importlib.import_module(module_name)
        except Exception as exc:
            issues.append(
                {
                    "detected": detected,
                    "error": str(exc),
                    "package": distribution,
                    "required": required_version,
                }
            )
            continue
        if detected != required_version:
            issues.append(
                {
                    "detected": detected,
                    "error": "version_mismatch",
                    "package": distribution,
                    "required": required_version,
                }
            )
    return issues


def require_basic_environment(repo_root: Path) -> None:
    if sys.version_info < (3, 11):
        raise CliFailure(
            "E-ENV-01",
            f"E-ENV-01 Python版が要件未満です: 検出{sys.version.split()[0]}、要求3.11以上。",
            detail={"detected": sys.version.split()[0], "required": ">=3.11"},
        )

    issues = dependency_issues()
    if issues:
        details = "; ".join(
            f"{issue['package']} 要求{issue['required']} 検出{issue['detected'] or '欠落'}"
            for issue in issues
        )
        raise CliFailure(
            "E-ENV-02",
            f"E-ENV-02 依存パッケージが欠落または版不一致です: {details}",
            detail={"packages": issues},
        )

    missing: list[str] = []
    for relative in ("schemas", "data/config", "agent", "scripts"):
        if not (repo_root / relative).is_dir():
            missing.append(relative)
    for schema_name in SCHEMA_FILES:
        schema_path = repo_root / "schemas" / schema_name
        if not schema_path.is_file():
            missing.append(f"schemas/{schema_name}")
            continue
        try:
            json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            missing.append(f"schemas/{schema_name}（破損）")
    if missing:
        raise CliFailure(
            "E-ENV-04",
            f"E-ENV-04 リポジトリ構成が不完全です: {', '.join(missing)}",
            detail={"paths": missing},
        )


def load_spacy_model() -> tuple[Any, str]:
    detected: str | None = None
    try:
        detected = importlib.metadata.version(MODEL_NAME)
        spacy = importlib.import_module("spacy")
        model = spacy.load(MODEL_NAME)
    except Exception as exc:
        raise CliFailure(
            "E-ENV-03",
            f"E-ENV-03 spaCyモデル{MODEL_NAME}をロードできません: "
            f"要求{MODEL_VERSION}、検出{detected or '欠落'}。",
            detail={
                "detected": detected,
                "error": str(exc),
                "model": MODEL_NAME,
                "required": MODEL_VERSION,
            },
        ) from exc
    if detected != MODEL_VERSION:
        raise CliFailure(
            "E-ENV-03",
            f"E-ENV-03 spaCyモデル{MODEL_NAME}の版が不一致です: 検出{detected}、要求{MODEL_VERSION}。",
            detail={"detected": detected, "model": MODEL_NAME, "required": MODEL_VERSION},
        )
    return model, detected


def validate_sources_document(document: Any, path: Path) -> list[dict[str, str]]:
    expected = (
        ("wordlist", WORDLIST_FILE),
        ("grammar_profile", GRAMMAR_FILE),
    )
    problems: list[str] = []
    if not isinstance(document, dict) or set(document) != {"sources"}:
        problems.append("トップレベルはsourcesキー1個でなければなりません")
        sources: Any = []
    else:
        sources = document["sources"]
    if not isinstance(sources, list) or len(sources) != 2:
        problems.append("sourcesは2要素の配列でなければなりません")
        sources = []

    validated: list[dict[str, str]] = []
    for index, (role, file_name) in enumerate(expected):
        if index >= len(sources) or not isinstance(sources[index], dict):
            problems.append(f"sources[{index}]がオブジェクトではありません")
            continue
        source = sources[index]
        if set(source) != {"role", "file", "url", "download_date"}:
            problems.append(f"sources[{index}]のキーが不正です")
            continue
        if source.get("role") != role:
            problems.append(f"sources[{index}].roleは{role}でなければなりません")
        if source.get("file") != file_name:
            problems.append(f"sources[{index}].fileは{file_name}でなければなりません")
        url = source.get("url")
        if not isinstance(url, str) or not re.match(r"^https?://", url):
            problems.append(f"sources[{index}].urlはhttp://またはhttps://で始まる文字列でなければなりません")
        download_date = source.get("download_date")
        if not isinstance(download_date, str) or not DATE_PATTERN.fullmatch(download_date):
            problems.append(f"sources[{index}].download_dateはYYYY-MM-DDでなければなりません")
        if not problems or all(not problem.startswith(f"sources[{index}]") for problem in problems):
            validated.append(
                {
                    "download_date": download_date,
                    "file": file_name,
                    "role": role,
                    "url": url,
                }
            )

    if problems:
        raise CliFailure(
            "E-DATA-01",
            f"E-DATA-01 sources.jsonの構造が不正です: {path}",
            detail={"problems": problems},
        )
    return validated


def load_sources(source_dir: Path) -> list[dict[str, str]]:
    missing = [name for name in SOURCE_FILE_NAMES if not (source_dir / name).is_file()]
    sources_path = source_dir / "sources.json"
    if not sources_path.is_file():
        missing.append("sources.json")
    if missing:
        raise CliFailure(
            "E-DATA-01",
            f"E-DATA-01 原本入力が欠落しています: {', '.join(missing)}",
            detail={"missing": missing, "source_dir": str(source_dir)},
        )
    document = load_json_file(sources_path, "E-DATA-01")
    return validate_sources_document(document, sources_path)


def source_checksums(source_dir: Path) -> dict[str, str]:
    return {name: sha256_file(source_dir / name) for name in SOURCE_FILE_NAMES}


def existing_meta_checksums(meta_path: Path) -> dict[str, str] | None:
    if not meta_path.exists():
        return None
    meta = load_json_file(meta_path, "E-DATA-04")
    try:
        return {source["file"]: source["sha256"] for source in meta["sources"]}
    except (KeyError, TypeError) as exc:
        raise CliFailure(
            "E-DATA-04",
            f"E-DATA-04 既存meta.jsonのsourcesが不正です: {meta_path}",
            detail={"error": str(exc), "path": str(meta_path)},
        ) from exc


def checksum_mismatches(
    expected: dict[str, str], actual: dict[str, str]
) -> list[dict[str, str | None]]:
    return [
        {
            "actual": actual.get(file_name),
            "expected": expected.get(file_name),
            "file": file_name,
        }
        for file_name in SOURCE_FILE_NAMES
        if expected.get(file_name) != actual.get(file_name)
    ]


def normalized_text(value: Any, *, field: str, required: bool, trim: bool = True) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field}が空です")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field}が文字列ではありません: {value!r}")
    text = unicodedata.normalize("NFC", value)
    if trim:
        text = text.strip()
    if text == "":
        if required:
            raise ValueError(f"{field}が空です")
        return None
    return text


def normalized_id(value: Any, *, field: str) -> str:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field}がIDではありません: {value!r}")
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float) and value.is_integer():
        text = str(int(value))
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise ValueError(f"{field}がIDではありません: {value!r}")
    if not ID_PATTERN.fullmatch(text):
        raise ValueError(f"{field}の書式が不正です: {text!r}")
    return text


def data_rows(worksheet: Any, start_row: int) -> list[tuple[Any, ...]]:
    rows = []
    for row in worksheet.iter_rows(min_row=start_row, values_only=True):
        if any(value is not None for value in row):
            rows.append(tuple(row))
    return rows


def fixed_data_rows(
    worksheet: Any,
    start_row: int,
    end_row: int,
    *,
    sheet_name: str,
) -> list[tuple[Any, ...]]:
    rows = [
        tuple(row)
        for row in worksheet.iter_rows(
            min_row=start_row,
            max_row=end_row,
            values_only=True,
        )
    ]
    blank_rows = [
        start_row + index
        for index, row in enumerate(rows)
        if not any(value is not None for value in row)
    ]
    trailing_rows = [
        row_number
        for row_number, row in enumerate(
            worksheet.iter_rows(min_row=end_row + 1, values_only=True),
            start=end_row + 1,
        )
        if any(value is not None for value in row)
    ]
    if blank_rows or trailing_rows:
        raise ValueError(
            f"{sheet_name}のデータ行位置が不正です: "
            f"空行={blank_rows}、範囲後の非空行={trailing_rows}"
        )
    return rows


def require_nonempty_row(worksheet: Any, row_number: int, *, sheet_name: str) -> None:
    if not any(cell.value is not None for cell in worksheet[row_number]):
        raise ValueError(f"{sheet_name}の{row_number}行目が空です")


def ensure_sheets(workbook: Any, required: Iterable[str], workbook_name: str) -> None:
    missing = [name for name in required if name not in workbook.sheetnames]
    if missing:
        raise CliFailure(
            "E-DATA-06",
            f"E-DATA-06 {workbook_name}に必須シートがありません: {', '.join(missing)}",
            detail={"missing_sheets": missing, "workbook": workbook_name},
        )


def ensure_exact_headers(
    worksheet: Any,
    row_number: int,
    expected: Iterable[str],
    *,
    sheet_name: str,
) -> dict[str, int]:
    values = [cell.value for cell in worksheet[row_number]]
    found: dict[str, int] = {}
    for header in expected:
        positions = [index for index, value in enumerate(values) if value == header]
        if len(positions) != 1:
            raise CliFailure(
                "E-DATA-06",
                f"E-DATA-06 {sheet_name}で列名を一意に検出できません: {header}",
                detail={"header": header, "positions": positions, "sheet": sheet_name},
            )
        found[header] = positions[0]
    return found


def load_workbook(path: Path) -> Any:
    try:
        openpyxl = importlib.import_module("openpyxl")
        # read_onlyでは実データ反復時に発火するため、処理全体へ狭いmodule条件で適用する。
        # 原本の非データ拡張（条件付き書式・sparkline等）は正規化対象ではない。
        warnings.filterwarnings(
            "ignore",
            category=UserWarning,
            module=r"openpyxl\.worksheet\._reader",
        )
        return openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        raise CliFailure(
            "E-DATA-06",
            f"E-DATA-06 原本xlsxを開けません: {path.name}",
            detail={"error": str(exc), "file": path.name},
        ) from exc


def lex_id(headword: str, pos: str) -> str:
    return f"lex:{headword}:{pos.replace(' ', '-')}"


def build_lexicon(source_path: Path) -> tuple[dict[str, Any], dict[str, int]]:
    workbook = load_workbook(source_path)
    try:
        required_sheets = (
            "ALL",
            "A1",
            "A2",
            "B1",
            "B2",
            "ALL_sep",
            "A1_sep",
            "A2_sep",
            "B1_sep",
            "B2_sep",
        )
        ensure_sheets(workbook, required_sheets, WORDLIST_FILE)
        for sheet_name in required_sheets:
            ensure_exact_headers(
                workbook[sheet_name],
                1,
                WORDLIST_HEADERS,
                sheet_name=sheet_name,
            )

        all_sep_rows = data_rows(workbook["ALL_sep"], 2)
        all_rows = data_rows(workbook["ALL"], 2)
        if len(all_sep_rows) != 7_988 or len(all_rows) != 7_801:
            raise ValueError(
                f"行数不一致: ALL_sep={len(all_sep_rows)}、ALL={len(all_rows)}"
            )

        entries_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for row_number, row in enumerate(all_sep_rows, start=2):
            headword = normalized_text(row[0], field="headword", required=True)
            pos = normalized_text(row[1], field="pos", required=True)
            level = normalized_text(row[2], field="CEFR", required=True)
            if ":" in headword:
                raise ValueError(f"ALL_sep!A{row_number} headwordにコロンがあります: {headword}")
            if pos not in POS_VALUES:
                raise ValueError(f"ALL_sep!B{row_number} posが値域外です: {pos}")
            if level not in CEFR_VALUES:
                raise ValueError(f"ALL_sep!C{row_number} CEFRが値域外です: {level}")
            entry = {
                "core_inventory_1": normalized_text(
                    row[3], field="CoreInventory 1", required=False
                ),
                "core_inventory_2": normalized_text(
                    row[4], field="CoreInventory 2", required=False
                ),
                "group_ids": [],
                "headword": headword,
                "id": lex_id(headword, pos),
                "is_multiword": " " in headword or "-" in headword,
                "level": level,
                "pos": pos,
                "threshold": normalized_text(row[5], field="Threshold", required=False),
            }
            key = (headword, pos)
            existing = entries_by_key.get(key)
            if existing is None:
                entries_by_key[key] = entry
            else:
                comparable = {k: v for k, v in entry.items() if k != "group_ids"}
                existing_comparable = {k: v for k, v in existing.items() if k != "group_ids"}
                if comparable != existing_comparable:
                    raise ValueError(f"ALL_sepに不一致重複があります: {headword}/{pos}")

        groups: list[dict[str, Any]] = []
        seen_group_ids: set[str] = set()
        for row_number, row in enumerate(all_rows, start=2):
            joined = normalized_text(row[0], field="ALL headword", required=True)
            pos = normalized_text(row[1], field="ALL pos", required=True)
            level = normalized_text(row[2], field="ALL CEFR", required=True)
            if pos not in POS_VALUES or level not in CEFR_VALUES:
                raise ValueError(f"ALL!{row_number} のposまたはCEFRが値域外です")
            if "/" not in joined:
                continue
            variants = [unicodedata.normalize("NFC", part.strip()) for part in joined.split("/")]
            if len(variants) < 2 or any(not variant for variant in variants):
                raise ValueError(f"ALL!A{row_number} のvariantが不正です: {joined}")
            group_id = f"grp:{variants[0]}:{pos.replace(' ', '-')}"
            if ":" in variants[0] or group_id in seen_group_ids:
                raise ValueError(f"ALL!A{row_number} のgroup_idが不正または重複です: {group_id}")
            member_ids: list[str] = []
            member_levels: set[str] = set()
            for variant in variants:
                entry = entries_by_key.get((variant, pos))
                if entry is None:
                    raise ValueError(
                        f"ALL!A{row_number} variantに対応するALL_sep行がありません: {variant}/{pos}"
                    )
                member_ids.append(entry["id"])
                member_levels.add(entry["level"])
                entry["group_ids"].append(group_id)
            if len(set(member_ids)) != len(member_ids):
                raise ValueError(f"ALL!A{row_number} に重複variantがあります: {joined}")
            if member_levels != {level}:
                raise ValueError(f"ALL!A{row_number} のグループ内レベルが一致しません: {joined}")
            groups.append(
                {
                    "group_id": group_id,
                    "headword_joined": joined,
                    "level": level,
                    "member_ids": member_ids,
                    "pos": pos,
                }
            )
            seen_group_ids.add(group_id)

        entries = list(entries_by_key.values())
        for entry in entries:
            entry["group_ids"].sort()
        entries.sort(key=lambda entry: (entry["headword"].casefold(), entry["headword"], entry["pos"]))
        groups.sort(key=lambda group: group["group_id"])

        expected_levels = {"A1": 1_200, "A2": 1_443, "B1": 2_486, "B2": 2_859}
        actual_levels = Counter(entry["level"] for entry in entries)
        sep_counts = {
            level: len(data_rows(workbook[f"{level}_sep"], 2))
            for level in ("A1", "A2", "B1", "B2")
        }
        if len(entries) != 7_988:
            raise ValueError(f"entries件数が7,988ではありません: {len(entries)}")
        if dict(actual_levels) != expected_levels:
            raise ValueError(f"レベル別件数が不一致です: {dict(actual_levels)}")
        if sep_counts != expected_levels:
            raise ValueError(f"レベル別sepシート件数が不一致です: {sep_counts}")
        if len({(entry["headword"], entry["pos"]) for entry in entries}) != 7_988:
            raise ValueError("(headword, pos)ユニーク数が7,988ではありません")
        if any(len(group["member_ids"]) < 2 for group in groups):
            raise ValueError("member_idsが2件未満のグループがあります")

        lexicon = {
            "data_version": DATA_VERSION,
            "entries": entries,
            "groups": groups,
            "schema_version": SCHEMA_VERSION,
        }
        stats = {
            "all_rows": len(all_rows),
            "entries": len(entries),
            "groups": len(groups),
            "unique_headword_pos": len(entries),
        }
        return lexicon, stats
    except CliFailure:
        raise
    except (IndexError, TypeError, ValueError) as exc:
        raise CliFailure(
            "E-DATA-06",
            f"E-DATA-06 Wordlist原本の構造または内容が不正です: {exc}",
            detail={"error": str(exc), "file": WORDLIST_FILE},
        ) from exc
    finally:
        workbook.close()


def item_header_map(worksheet: Any) -> dict[str, int]:
    values = [cell.value for cell in worksheet[2]]
    found = ensure_exact_headers(
        worksheet,
        2,
        ITEM_HEADERS_EXACT,
        sheet_name="ITEM LIST",
    )
    prefix_targets = {
        "sentence_type_en": "Sentence Type (",
        "regex_treetagger": "正規表現(TreeTaggerベース",
    }
    for key, prefix in prefix_targets.items():
        positions = [
            index
            for index, value in enumerate(values)
            if isinstance(value, str) and value.startswith(prefix)
        ]
        if len(positions) != 1:
            raise CliFailure(
                "E-DATA-06",
                f"E-DATA-06 ITEM LISTで接頭辞列を一意に検出できません: {prefix}",
                detail={"positions": positions, "prefix": prefix, "sheet": "ITEM LIST"},
            )
        found[key] = positions[0]
    return found


def numeric_value(value: Any, *, field: str, integer: bool) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field}が数値ではありません: {value!r}")
    if integer:
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"{field}が整数ではありません: {value!r}")
        return int(value)
    return value


def parse_level(raw_value: Any, *, field: str) -> tuple[str, str, str]:
    raw = normalized_text(raw_value, field=field, required=True)
    match = LEVEL_PATTERN.fullmatch(raw)
    if not match:
        raise ValueError(f"{field}のCEFR-J level書式が不正です: {raw}")
    minimum = match.group(1)
    maximum = match.group(2) or minimum
    if minimum != maximum and CEFRJ_RANK[minimum] >= CEFRJ_RANK[maximum]:
        raise ValueError(f"{field}のレベル範囲が昇順ではありません: {raw}")
    return raw, minimum, maximum


def grammar_sort_key(entry: dict[str, Any]) -> tuple[int, int, int]:
    parts = entry["item_list_id"].split("-")
    parent = int(parts[0])
    if len(parts) == 1:
        return parent, 0, 0
    return parent, 1, int(parts[1])


def build_grammar(source_path: Path) -> tuple[dict[str, Any], dict[str, int]]:
    workbook = load_workbook(source_path)
    try:
        ensure_sheets(
            workbook,
            ("ITEM LIST", "教員版", "EFL SUMMARY (FULL)"),
            GRAMMAR_FILE,
        )
        item_sheet = workbook["ITEM LIST"]
        teacher_sheet = workbook["教員版"]
        efl_sheet = workbook["EFL SUMMARY (FULL)"]
        require_nonempty_row(item_sheet, 1, sheet_name="ITEM LISTタイトル")
        require_nonempty_row(teacher_sheet, 1, sheet_name="教員版タイトル")
        require_nonempty_row(efl_sheet, 2, sheet_name="EFL SUMMARY (FULL)タイトル")
        item_headers = item_header_map(item_sheet)
        teacher_headers = ensure_exact_headers(
            teacher_sheet,
            2,
            TEACHER_HEADERS,
            sheet_name="教員版",
        )

        efl_header_values = [cell.value for cell in efl_sheet[3]]
        required_efl_positions = {
            0: "ID",
            1: "文法項目",
            2: "文タイプ(不問のものは空欄)",
            3: "Shorthand Code",
            6: "A1",
            7: "A2",
            8: "B1",
            9: "B2",
            10: "C1",
            12: "A1",
            13: "A2",
            14: "B1",
            15: "B2",
            16: "C1",
        }
        wrong_efl = {
            index: (expected, efl_header_values[index] if index < len(efl_header_values) else None)
            for index, expected in required_efl_positions.items()
            if index >= len(efl_header_values) or efl_header_values[index] != expected
        }
        if wrong_efl:
            raise ValueError(f"EFL SUMMARY (FULL)の列位置が不正です: {wrong_efl}")

        item_rows = fixed_data_rows(item_sheet, 3, 503, sheet_name="ITEM LIST")
        teacher_rows = fixed_data_rows(teacher_sheet, 3, 258, sheet_name="教員版")
        efl_rows = fixed_data_rows(efl_sheet, 4, 504, sheet_name="EFL SUMMARY (FULL)")
        if len(item_rows) != 501 or len(teacher_rows) != 256 or len(efl_rows) != 501:
            raise ValueError(
                f"データ行数不一致: ITEM LIST={len(item_rows)}、教員版={len(teacher_rows)}、EFL={len(efl_rows)}"
            )

        item_by_id: dict[str, dict[str, Any]] = {}
        for row_number, row in enumerate(item_rows, start=3):
            item_id = normalized_id(row[item_headers["ID"]], field=f"ITEM LIST!A{row_number}")
            if item_id in item_by_id:
                raise ValueError(f"ITEM LIST IDが重複しています: {item_id}")
            item_by_id[item_id] = {
                "grammatical_item_en": normalized_text(
                    row[item_headers["Grammatical Item"]],
                    field="Grammatical Item",
                    required=False,
                ),
                "name_ja": normalized_text(
                    row[item_headers["文法項目"]], field="文法項目", required=True
                ),
                "note": normalized_text(
                    row[item_headers["備考"]], field="備考", required=False, trim=False
                ),
                "pattern_shorthand": normalized_text(
                    row[item_headers["パターン略記"]], field="パターン略記", required=False
                ),
                "regex_treetagger": normalized_text(
                    row[item_headers["regex_treetagger"]],
                    field="正規表現(TreeTaggerベース...)",
                    required=False,
                ),
                "sentence_type_en": normalized_text(
                    row[item_headers["sentence_type_en"]],
                    field="Sentence Type (...)",
                    required=False,
                    trim=False,
                ),
                "sentence_type_ja": normalized_text(
                    row[item_headers["文タイプ(不問のものは空欄)"]],
                    field="文タイプ",
                    required=False,
                    trim=False,
                ),
                "shorthand_code": normalized_text(
                    row[item_headers["Shorthand Code"]],
                    field="Shorthand Code",
                    required=False,
                ),
            }

        teacher_by_id: dict[str, dict[str, Any]] = {}
        single_levels = 0
        range_levels = 0
        for row_number, row in enumerate(teacher_rows, start=3):
            item_id = normalized_id(row[teacher_headers["ID"]], field=f"教員版!A{row_number}")
            if item_id not in item_by_id:
                raise ValueError(f"教員版IDがITEM LISTにありません: {item_id}")
            if item_id in teacher_by_id:
                raise ValueError(f"教員版IDが重複しています: {item_id}")
            raw, minimum, maximum = parse_level(
                row[teacher_headers["CEFR-J level"]], field=f"教員版!E{row_number}"
            )
            if minimum == maximum:
                single_levels += 1
            else:
                range_levels += 1
            teacher_by_id[item_id] = {
                "level": {"max": maximum, "min": minimum},
                "kyoinban": {
                    "level_raw": raw,
                    "name_en": normalized_text(
                        row[teacher_headers["Grammatical item (English)"]],
                        field="Grammatical item (English)",
                        required=False,
                    ),
                    "name_ja": normalized_text(
                        row[teacher_headers["文法項目"]],
                        field="教員版 文法項目",
                        required=True,
                    ),
                    "name_simple_ja": normalized_text(
                        row[teacher_headers["文法項目 (平易版)"]],
                        field="文法項目 (平易版)",
                        required=True,
                    ),
                    "present": True,
                },
            }

        efl_by_id: dict[str, dict[str, Any]] = {}
        levels = ("A1", "A2", "B1", "B2", "C1")
        for row_number, row in enumerate(efl_rows, start=4):
            item_id = normalized_id(row[0], field=f"EFL SUMMARY (FULL)!A{row_number}")
            if item_id not in item_by_id:
                raise ValueError(f"EFL IDがITEM LISTにありません: {item_id}")
            if item_id in efl_by_id:
                raise ValueError(f"EFL IDが重複しています: {item_id}")
            rel_freq = {
                level: numeric_value(row[6 + index], field=f"EFL rel_freq {item_id}/{level}", integer=False)
                for index, level in enumerate(levels)
            }
            ranges = {
                level: numeric_value(row[12 + index], field=f"EFL range {item_id}/{level}", integer=True)
                for index, level in enumerate(levels)
            }
            efl_by_id[item_id] = {"range": ranges, "rel_freq": rel_freq}

        corpus_row = [cell.value for cell in efl_sheet[1]]
        words = {
            level: numeric_value(corpus_row[6 + index], field=f"EFL corpus words/{level}", integer=True)
            for index, level in enumerate(levels)
        }
        books = {
            level: numeric_value(corpus_row[12 + index], field=f"EFL corpus books/{level}", integer=True)
            for index, level in enumerate(levels)
        }
        if books != {"A1": 17, "A2": 21, "B1": 26, "B2": 23, "C1": 8}:
            raise ValueError(f"EFL教科書数が不一致です: {books}")
        if any(value is None for value in words.values()):
            raise ValueError(f"EFL総語数に空値があります: {words}")

        parent_ids = {item_id for item_id in item_by_id if "-" not in item_id}
        child_ids = {item_id for item_id in item_by_id if "-" in item_id}
        if len(parent_ids) != 263 or len(child_ids) != 238:
            raise ValueError(f"親子件数が不一致です: 親{len(parent_ids)}、枝番{len(child_ids)}")
        for child_id in child_ids:
            parent_id = child_id.split("-", 1)[0]
            if parent_id not in parent_ids:
                raise ValueError(f"枝番の親IDがありません: {child_id} -> {parent_id}")

        missing_direct_parents = parent_ids - set(teacher_by_id)
        if missing_direct_parents != UNASSIGNED_PARENT_IDS:
            raise ValueError(
                f"教員版レベル未付与親IDが不一致です: {sorted(missing_direct_parents, key=int)}"
            )

        entries: list[dict[str, Any]] = []
        null_level_ids: set[str] = set()
        for item_id, item_list in item_by_id.items():
            parent_id_value = item_id.split("-", 1)[0] if "-" in item_id else None
            teacher = teacher_by_id.get(item_id)
            if teacher is not None:
                kyoinban = teacher["kyoinban"]
                level = {
                    "inherited_from": None,
                    "max": teacher["level"]["max"],
                    "min": teacher["level"]["min"],
                    "source": "kyoinban_direct",
                }
                display_name = kyoinban["name_simple_ja"]
                target_eligible = True
            else:
                kyoinban = {
                    "level_raw": None,
                    "name_en": None,
                    "name_ja": None,
                    "name_simple_ja": None,
                    "present": False,
                }
                parent_teacher = teacher_by_id.get(parent_id_value) if parent_id_value else None
                if parent_teacher is not None:
                    level = {
                        "inherited_from": f"gp:{parent_id_value}",
                        "max": parent_teacher["level"]["max"],
                        "min": parent_teacher["level"]["min"],
                        "source": "kyoinban_inherited",
                    }
                else:
                    level = {
                        "inherited_from": None,
                        "max": None,
                        "min": None,
                        "source": None,
                    }
                    null_level_ids.add(item_id)
                display_name = item_list["name_ja"]
                target_eligible = False

            entries.append(
                {
                    "display_name": display_name,
                    "efl": efl_by_id.get(item_id),
                    "id": f"gp:{item_id}",
                    "item_list": item_list,
                    "item_list_id": item_id,
                    "kyoinban": kyoinban,
                    "level": level,
                    "parent_id": f"gp:{parent_id_value}" if parent_id_value else None,
                    "target_eligible": target_eligible,
                }
            )

        expected_null = {
            item_id
            for item_id in item_by_id
            if item_id not in teacher_by_id and item_id.split("-", 1)[0] in UNASSIGNED_PARENT_IDS
        }
        if null_level_ids != expected_null:
            raise ValueError(f"level.source=nullのID集合が不一致です: {sorted(null_level_ids)}")
        if len(teacher_by_id) != 256 or single_levels != 152 or range_levels != 104:
            raise ValueError(
                f"教員版レベル件数が不一致です: total={len(teacher_by_id)}、single={single_levels}、range={range_levels}"
            )

        entries.sort(key=grammar_sort_key)
        grammar = {
            "data_version": DATA_VERSION,
            "efl_corpus": {"books": books, "words": words},
            "entries": entries,
            "schema_version": SCHEMA_VERSION,
        }
        stats = {
            "children": len(child_ids),
            "entries": len(entries),
            "null_levels": len(null_level_ids),
            "parents": len(parent_ids),
            "range_levels": range_levels,
            "single_levels": single_levels,
            "target_eligible": len(teacher_by_id),
        }
        return grammar, stats
    except CliFailure:
        raise
    except (IndexError, TypeError, ValueError) as exc:
        raise CliFailure(
            "E-DATA-06",
            f"E-DATA-06 Grammar Profile原本の構造または内容が不正です: {exc}",
            detail={"error": str(exc), "file": GRAMMAR_FILE},
        ) from exc
    finally:
        workbook.close()


def build_meta(
    sources: list[dict[str, str]],
    checksums: dict[str, str],
    *,
    model_version: str,
    lexicon_count: int,
    group_count: int,
    grammar_count: int,
    target_count: int,
) -> dict[str, Any]:
    source_versions = {
        "wordlist": "1.6",
        "grammar_profile": "20200220",
    }
    return {
        "counts": {
            "grammar_items": grammar_count,
            "lexicon_entries": lexicon_count,
            "lexicon_groups": group_count,
            "target_eligible": target_count,
        },
        "data_version": DATA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "sources": [
            {
                "file": source["file"],
                "retrieved_date": source["download_date"],
                "role": source["role"],
                "sha256": checksums[source["file"]],
                "url": source["url"],
                "version_label": source_versions[source["role"]],
            }
            for source in sources
        ],
        "spacy_model": {"name": MODEL_NAME, "version": model_version},
    }


def validate_meta_document(meta: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(meta, dict) or set(meta) != {
        "counts",
        "data_version",
        "pipeline_version",
        "sources",
        "spacy_model",
    }:
        return ["トップレベルキーがNRM-29と一致しません"]
    if meta.get("data_version") != DATA_VERSION:
        problems.append("data_versionが不一致です")
    if meta.get("pipeline_version") != PIPELINE_VERSION:
        problems.append("pipeline_versionが不一致です")
    model = meta.get("spacy_model")
    if not isinstance(model, dict) or set(model) != {"name", "version"}:
        problems.append("spacy_modelの構造が不正です")
    elif model.get("name") != MODEL_NAME or not isinstance(model.get("version"), str):
        problems.append("spacy_modelの値が不正です")
    counts = meta.get("counts")
    count_keys = {"lexicon_entries", "lexicon_groups", "grammar_items", "target_eligible"}
    if not isinstance(counts, dict) or set(counts) != count_keys:
        problems.append("countsの構造が不正です")
    elif any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts.values()):
        problems.append("countsに0以上の整数でない値があります")
    sources = meta.get("sources")
    expected = (("wordlist", WORDLIST_FILE, "1.6"), ("grammar_profile", GRAMMAR_FILE, "20200220"))
    if not isinstance(sources, list) or len(sources) != 2:
        problems.append("sourcesは2要素でなければなりません")
    else:
        for index, (role, file_name, version_label) in enumerate(expected):
            source = sources[index]
            required_keys = {"role", "file", "sha256", "version_label", "url", "retrieved_date"}
            if not isinstance(source, dict) or set(source) != required_keys:
                problems.append(f"sources[{index}]の構造が不正です")
                continue
            if source["role"] != role or source["file"] != file_name or source["version_label"] != version_label:
                problems.append(f"sources[{index}]の固定値が不正です")
            if not isinstance(source["sha256"], str) or not SHA256_PATTERN.fullmatch(source["sha256"]):
                problems.append(f"sources[{index}].sha256が不正です")
            if not isinstance(source["url"], str) or not re.match(r"^https?://", source["url"]):
                problems.append(f"sources[{index}].urlが不正です")
            if not isinstance(source["retrieved_date"], str) or not DATE_PATTERN.fullmatch(source["retrieved_date"]):
                problems.append(f"sources[{index}].retrieved_dateが不正です")
    return problems


def validate_normalized_set(repo_root: Path, normalized_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    missing = [name for name in NORMALIZED_FILE_NAMES if not (normalized_dir / name).is_file()]
    if missing:
        raise CliFailure(
            "E-DATA-03",
            f"E-DATA-03 正規化データが欠落しています: {', '.join(missing)}",
            detail={"missing": missing},
            remedy="git checkoutで復元するか、python scripts/build_normalized.py を実行してください。",
        )
    lexicon = load_json_file(normalized_dir / "lexicon.json", "E-DATA-04")
    grammar = load_json_file(normalized_dir / "grammar.json", "E-DATA-04")
    meta = load_json_file(normalized_dir / "meta.json", "E-DATA-04")
    lex_errors = schema_errors(lexicon, repo_root / "schemas/normalized_lexicon.schema.json")
    grammar_errors = schema_errors(grammar, repo_root / "schemas/normalized_grammar.schema.json")
    meta_errors = validate_meta_document(meta)
    problems: list[Any] = []
    if lex_errors:
        problems.append({"lexicon": lex_errors[:50], "total": len(lex_errors)})
    if grammar_errors:
        problems.append({"grammar": grammar_errors[:50], "total": len(grammar_errors)})
    if meta_errors:
        problems.append({"meta": meta_errors})
    versions = {lexicon.get("data_version"), grammar.get("data_version"), meta.get("data_version")}
    if versions != {DATA_VERSION}:
        problems.append({"data_versions": sorted(str(value) for value in versions)})
    try:
        expected_counts = {
            "grammar_items": len(grammar["entries"]),
            "lexicon_entries": len(lexicon["entries"]),
            "lexicon_groups": len(lexicon["groups"]),
            "target_eligible": sum(1 for entry in grammar["entries"] if entry["target_eligible"]),
        }
        if meta.get("counts") != expected_counts:
            problems.append({"actual_counts": expected_counts, "meta_counts": meta.get("counts")})
    except (KeyError, TypeError) as exc:
        problems.append({"count_error": str(exc)})
    if problems:
        raise CliFailure(
            "E-DATA-04",
            f"E-DATA-04 正規化データのスキーマまたは内部整合が不正です: {normalized_dir}",
            detail={"problems": problems},
        )
    return lexicon, grammar, meta


def diff_bucket(ids: Iterable[str]) -> dict[str, Any]:
    sorted_ids = sorted(ids)
    return {"count": len(sorted_ids), "ids": sorted_ids}


def entry_diff(
    old_document: dict[str, Any],
    new_document: dict[str, Any],
) -> dict[str, Any]:
    old_by_id = {entry["id"]: entry for entry in old_document["entries"]}
    new_by_id = {entry["id"]: entry for entry in new_document["entries"]}
    shared = set(old_by_id) & set(new_by_id)
    changed = {
        entry_id
        for entry_id in shared
        if old_by_id[entry_id]["level"] != new_by_id[entry_id]["level"]
    }
    return {
        "added": diff_bucket(set(new_by_id) - set(old_by_id)),
        "level_changed": diff_bucket(changed),
        "removed": diff_bucket(set(old_by_id) - set(new_by_id)),
    }


def build_diff(
    old_lexicon: dict[str, Any],
    old_grammar: dict[str, Any],
    new_lexicon: dict[str, Any],
    new_grammar: dict[str, Any],
) -> dict[str, Any]:
    return {
        "grammar": entry_diff(old_grammar, new_grammar),
        "lexicon": entry_diff(old_lexicon, new_lexicon),
    }


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = canonical_json_text(value)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def relative_path(path: Path, repo_root: Path) -> str:
    return Path(os.path.relpath(path, repo_root)).as_posix()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = JapaneseArgumentParser(
        description="CEFR-J原本xlsxから正規化JSONを決定的に生成します。",
    )
    parser.add_argument(
        "--source-dir",
        default="data/source",
        help="原本ディレクトリ（既定: data/source）",
    )
    parser.add_argument(
        "--out-dir",
        default="data/normalized",
        help="出力ディレクトリ（既定: data/normalized）",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="既存正規化データとの差分を表示し、書き込みません",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="検証と生成を行いますが、ファイルを書き込みません",
    )
    parser.add_argument(
        "--accept-source-change",
        action="store_true",
        help="承認済みの原本チェックサム変更を受け入れて本ビルドします",
    )
    args = parser.parse_args(argv)
    if args.diff and args.accept_source_change:
        raise CliFailure(
            "E-INPUT-01",
            "E-INPUT-01 --diffと--accept-source-changeは併用できません。",
            detail={"arguments": ["--diff", "--accept-source-change"]},
        )
    return args


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path.cwd()
    require_basic_environment(repo_root)
    _model, model_version = load_spacy_model()

    source_dir = Path(args.source_dir)
    out_dir = Path(args.out_dir)
    if not source_dir.is_absolute():
        source_dir = repo_root / source_dir
    if not out_dir.is_absolute():
        out_dir = repo_root / out_dir

    sources = load_sources(source_dir)
    checksums = source_checksums(source_dir)
    if args.diff:
        missing = [name for name in NORMALIZED_FILE_NAMES if not (out_dir / name).is_file()]
        if missing:
            raise CliFailure(
                "E-INPUT-02",
                f"E-INPUT-02 --diffに必要な既存正規化データがありません: {', '.join(missing)}",
                detail={"missing": missing, "out_dir": str(out_dir)},
            )
    existing_checksums = existing_meta_checksums(out_dir / "meta.json")
    if existing_checksums is not None:
        mismatches = checksum_mismatches(existing_checksums, checksums)
        if mismatches and not args.diff and not args.accept_source_change:
            details = "; ".join(
                f"{item['file']} 期待{item['expected']} 実測{item['actual']}"
                for item in mismatches
            )
            raise CliFailure(
                "E-DATA-02",
                f"E-DATA-02 原本チェックサムがmeta.jsonと一致しません: {details}",
                detail={"mismatches": mismatches},
            )

    lexicon, lexicon_stats = build_lexicon(source_dir / WORDLIST_FILE)
    grammar, grammar_stats = build_grammar(source_dir / GRAMMAR_FILE)
    meta = build_meta(
        sources,
        checksums,
        model_version=model_version,
        lexicon_count=lexicon_stats["entries"],
        group_count=lexicon_stats["groups"],
        grammar_count=grammar_stats["entries"],
        target_count=grammar_stats["target_eligible"],
    )
    validate_against_schema(
        lexicon,
        repo_root / "schemas/normalized_lexicon.schema.json",
        "normalized_lexicon",
    )
    validate_against_schema(
        grammar,
        repo_root / "schemas/normalized_grammar.schema.json",
        "normalized_grammar",
    )
    meta_problems = validate_meta_document(meta)
    if meta_problems:
        raise CliFailure(
            "E-DATA-06",
            "E-DATA-06 生成したmeta.jsonがNRM-29に適合しません。",
            detail={"problems": meta_problems},
        )

    diff: dict[str, Any] | None = None
    if args.diff:
        old_lexicon, old_grammar, _old_meta = validate_normalized_set(repo_root, out_dir)
        diff = build_diff(old_lexicon, old_grammar, lexicon, grammar)

    written: list[str] = []
    if not args.dry_run and not args.diff:
        output_values = {
            "lexicon.json": lexicon,
            "grammar.json": grammar,
            "meta.json": meta,
        }
        for file_name in NORMALIZED_FILE_NAMES:
            path = out_dir / file_name
            atomic_write_json(path, output_values[file_name])
            written.append(relative_path(path, repo_root))

    summary = {
        "counts": {
            "grammar_items": grammar_stats["entries"],
            "lexicon_entries": lexicon_stats["entries"],
        },
        "data_version": DATA_VERSION,
        "diff": diff,
        "source_checksums": checksums,
        "written": written,
    }
    emit_json(summary)
    return 0


def main() -> int:
    try:
        return run()
    except CliFailure as exc:
        emit_json(exc.as_dict(), sys.stderr)
        return 1
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
