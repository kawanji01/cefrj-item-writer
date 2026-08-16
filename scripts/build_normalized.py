#!/usr/bin/env python3
"""CEFR-J原本xlsxから正規化JSONを決定的に生成する。"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import re
import subprocess
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
PIPELINE_VERSION = "1.0.2"
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
VERSION_LABEL_PATTERN = re.compile(r"^[0-9A-Za-z.\-]+$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
DATA_VERSION_PATTERN = re.compile(
    r"^wl[0-9A-Za-z.\-]+\+gp[0-9A-Za-z.\-]+\+norm\d+\.\d+\.\d+$"
)

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
ITEM_HEADERS_EXACT = (
    "ID",
    "文法項目",
    "文タイプ(不問のものは空欄)",
    "Shorthand Code",
    "Grammatical Item",
    "備考",
    "パターン略記",
)
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
    "E-ENV-05": "出力ディレクトリの権限と空き容量を確認してください。",
    "E-DATA-01": "原本2ファイルを固定名でdata/source/に配置し、sources.jsonに原本版・入手URL・ダウンロード日を記入してください。",
    "E-DATA-02": "意図的な原本更新はsources.jsonの対応するversion_labelも更新し、python scripts/build_normalized.py --diff で確認後、python scripts/build_normalized.py --accept-source-change を実行してください。意図しない場合は正しい原本を配置し直してください。",
    "E-DATA-03": "git checkoutで復元するか、python scripts/build_normalized.py を実行してください。",
    "E-DATA-04": "python scripts/build_normalized.py で再ビルドしてください。同じE-DATA-04で停止する場合は git checkout -- data/normalized/meta.json でコミット済みmetaを復元してから再ビルドしてください。再発時は正規化パイプラインの不具合として報告してください。",
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
        prefix = "unrecognized arguments:"
        if message.startswith(prefix):
            translated = f"未知の引数です:{message[len(prefix):]}"
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


def emit_json(value: Any, stream: Any = None) -> None:
    if stream is None:
        stream = sys.stdout
    payload = canonical_json_text(value).encode("utf-8")
    binary_stream = getattr(stream, "buffer", None)
    if binary_stream is not None:
        binary_stream.write(payload)
        return
    try:
        stream.write(payload)
    except TypeError:
        stream.write(payload.decode("utf-8"))


def reject_nonstandard_json_constant(token: str) -> None:
    raise ValueError(f"標準JSONではない数値定数です: {token}")


def parse_finite_json_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"有限値として表現できないJSON数値です: {token}")
    return value


def strict_json_loads(text: str) -> Any:
    return json.loads(
        text,
        parse_constant=reject_nonstandard_json_constant,
        parse_float=parse_finite_json_float,
    )


def load_json_file(path: Path, error_code: str = "E-DATA-04") -> Any:
    try:
        return strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
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


def selected_schema_branch(instance: Any, schema: dict[str, Any]) -> dict[str, Any]:
    """Discriminatorが有効な場合はoneOfの対応分岐を直接検証する。"""

    if not isinstance(instance, dict):
        return schema
    definition_name: str | None = None
    if schema.get("title") == "candidate":
        format_value = instance.get("format")
        if isinstance(format_value, str) and f"q_{format_value}" in schema.get("$defs", {}):
            definition_name = f"q_{format_value}"
    elif schema.get("title") == "machine_report":
        scope = instance.get("scope")
        if scope in {"question", "set"}:
            definition_name = f"{scope}_report"
    if definition_name is None:
        return schema
    return {
        "$schema": schema.get("$schema", "https://json-schema.org/draft/2020-12/schema"),
        "$defs": schema["$defs"],
        "$ref": f"#/$defs/{definition_name}",
    }


def leaf_schema_errors(error: Any) -> list[Any]:
    if not error.context:
        return [error]
    leaves: list[Any] = []
    for child in error.context:
        leaves.extend(leaf_schema_errors(child))
    return leaves


def json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__


def japanese_schema_message(error: Any) -> str:
    validator = error.validator
    constraint = error.validator_value
    if validator == "required" and isinstance(error.instance, dict):
        missing = sorted(set(constraint) - set(error.instance))
        return f"必須プロパティがありません: {', '.join(missing)}"
    if validator == "type":
        expected = constraint if isinstance(constraint, str) else "|".join(constraint)
        return f"型が不正です: 期待{expected}、実際{json_type_name(error.instance)}"
    if validator == "additionalProperties" and isinstance(error.instance, dict):
        allowed = set(error.schema.get("properties", {}))
        unexpected = sorted(set(error.instance) - allowed)
        return f"未定義のプロパティです: {', '.join(unexpected)}"
    if validator == "pattern":
        return f"文字列がパターン{constraint}に一致しません"
    if validator == "enum":
        return f"値{error.instance!r}が許容値{constraint!r}に含まれません"
    if validator == "const":
        return f"値{error.instance!r}が固定値{constraint!r}と一致しません"
    if validator == "minLength":
        return f"文字列は{constraint}文字以上必要です"
    if validator == "maxLength":
        return f"文字列は{constraint}文字以下である必要があります"
    if validator == "minItems":
        return f"配列は{constraint}件以上必要です"
    if validator == "maxItems":
        return f"配列は{constraint}件以下である必要があります"
    if validator == "uniqueItems":
        return "配列の要素が重複しています"
    if validator == "minimum":
        return f"値は{constraint}以上である必要があります"
    if validator == "maximum":
        return f"値は{constraint}以下である必要があります"
    return f"スキーマ制約{validator}に適合しません"


def schema_errors(instance: Any, schema_path: Path) -> list[dict[str, str]]:
    try:
        jsonschema = importlib.import_module("jsonschema")
        schema = load_json_file(schema_path, "E-ENV-04")
        validator = jsonschema.Draft202012Validator(selected_schema_branch(instance, schema))
        root_errors = validator.iter_errors(instance)
        errors = [leaf for error in root_errors for leaf in leaf_schema_errors(error)]
    except CliFailure:
        raise
    except Exception as exc:
        raise CliFailure(
            "E-ENV-04",
            f"E-ENV-04 スキーマを検証器へ読み込めません: {schema_path}",
            detail={"error": str(exc), "path": str(schema_path)},
        ) from exc
    rendered = {
        (json_pointer(error.absolute_path), japanese_schema_message(error)) for error in errors
    }
    return [
        {"json_pointer": pointer, "message": message}
        for pointer, message in sorted(rendered)
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
    try:
        metadata = importlib.import_module("importlib.metadata")
    except Exception as exc:
        return [
            {
                "detected": None,
                "error": str(exc),
                "package": distribution,
                "required": required_version,
            }
            for distribution, (_module_name, required_version) in REQUIRED_PACKAGES.items()
        ]
    for distribution, (module_name, required_version) in REQUIRED_PACKAGES.items():
        detected: str | None = None
        try:
            detected = metadata.version(distribution)
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
            strict_json_loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
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
        metadata = importlib.import_module("importlib.metadata")
        detected = metadata.version(MODEL_NAME)
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
        if set(source) != {"role", "file", "version_label", "url", "download_date"}:
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
        version_label = source.get("version_label")
        if not isinstance(version_label, str) or not VERSION_LABEL_PATTERN.fullmatch(version_label):
            problems.append(
                f"sources[{index}].version_labelは英数字・ピリオド・ハイフンでなければなりません"
            )
        if not problems or all(not problem.startswith(f"sources[{index}]") for problem in problems):
            validated.append(
                {
                    "download_date": download_date,
                    "file": file_name,
                    "role": role,
                    "url": url,
                    "version_label": version_label,
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


def compose_data_version(
    wordlist_version: str,
    grammar_version: str,
    pipeline_version: str,
) -> str:
    return f"wl{wordlist_version}+gp{grammar_version}+norm{pipeline_version}"


def source_data_version(sources: list[dict[str, str]]) -> str:
    versions = {source["role"]: source["version_label"] for source in sources}
    return compose_data_version(
        versions["wordlist"],
        versions["grammar_profile"],
        PIPELINE_VERSION,
    )


def existing_meta_restore_remedy(meta_path: Path) -> str:
    try:
        display_path = meta_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        display_path = str(meta_path)
    return (
        f"git checkout -- {display_path} でコミット済みmetaを復元してから、"
        "python scripts/build_normalized.py を再実行してください。"
    )


def existing_meta_safety_sources(meta: Any) -> list[dict[str, str | None]] | None:
    if not isinstance(meta, dict):
        return None
    sources = meta.get("sources")
    expected = (("wordlist", WORDLIST_FILE), ("grammar_profile", GRAMMAR_FILE))
    if not isinstance(sources, list) or len(sources) != len(expected):
        return None
    safe_sources: list[dict[str, str | None]] = []
    for index, (role, file_name) in enumerate(expected):
        source = sources[index]
        if not isinstance(source, dict):
            return None
        if source.get("role") != role or source.get("file") != file_name:
            return None
        sha256 = source.get("sha256")
        if not isinstance(sha256, str) or not SHA256_PATTERN.fullmatch(sha256):
            return None
        version_label = source.get("version_label")
        safe_sources.append(
            {
                "file": file_name,
                "role": role,
                "sha256": sha256,
                "version_label": (
                    version_label
                    if isinstance(version_label, str)
                    and VERSION_LABEL_PATTERN.fullmatch(version_label)
                    else None
                ),
            }
        )
    return safe_sources


def git_head_query_failure(
    path: Path,
    command: list[str],
    *,
    error: str,
    returncode: int | None,
) -> CliFailure:
    rendered_command = json.dumps(command, ensure_ascii=False)
    rendered_error = error.replace("\r", " ").replace("\n", "; ")
    if returncode is None:
        failure_description = (
            f"コマンド={rendered_command}、OSエラー={rendered_error}"
        )
    else:
        failure_description = (
            f"コマンド={rendered_command}、終了コード={returncode}、"
            f"stderr={rendered_error}"
        )
    return CliFailure(
        "E-ENV-04",
        "E-ENV-04 Git HEADを照会できないため初回ビルド判定を安全に"
        f"行えません: {path} ({failure_description})",
        detail={
            "command": command,
            "error": error,
            "path": str(path),
            "returncode": returncode,
        },
        remedy=(
            "git --version と git rev-parse --verify HEAD を確認し、Gitまたは"
            "リポジトリを復旧してから再実行してください。"
        ),
    )


def git_query_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_GRAFT_FILE",
        "GIT_INDEX_FILE",
        "GIT_INTERNAL_SUPER_PREFIX",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_REPLACE_REF_BASE",
        "GIT_SHALLOW_FILE",
        "GIT_WORK_TREE",
    ):
        environment.pop(name, None)
    environment["LC_ALL"] = "C"
    environment["LANG"] = "C"
    return environment


def run_git_head_query(
    path: Path,
    command: list[str],
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=git_query_environment(),
        )
    except OSError as exc:
        raise git_head_query_failure(
            path,
            command,
            error=str(exc),
            returncode=None,
        ) from exc
    if result.returncode != 0:
        error = result.stderr.strip().replace("\r", " ").replace("\n", "; ")
        raise git_head_query_failure(
            path,
            command,
            error=error or "Gitコマンドが非0終了しました",
            returncode=result.returncode,
        )
    return result


def run_git_repository_query(path: Path, directory: Path) -> str | None:
    command = [
        "git",
        "-C",
        str(directory),
        "rev-parse",
        "--show-toplevel",
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=git_query_environment(),
        )
    except OSError as exc:
        raise git_head_query_failure(
            path,
            command,
            error=str(exc),
            returncode=None,
        ) from exc
    if result.returncode != 0:
        error = result.stderr.strip().replace("\r", " ").replace("\n", "; ")
        if "not a git repository" in error:
            return None
        raise git_head_query_failure(
            path,
            command,
            error=error or "Gitコマンドが非0終了しました",
            returncode=result.returncode,
        )
    root_text = result.stdout.rstrip("\r\n")
    if not root_text:
        raise git_head_query_failure(
            path,
            command,
            error="Gitリポジトリルートが空です",
            returncode=0,
        )
    return root_text


def alternate_ascii_case(name: str) -> str | None:
    for index, character in enumerate(name):
        if "a" <= character <= "z":
            return name[:index] + character.upper() + name[index + 1 :]
        if "A" <= character <= "Z":
            return name[:index] + character.lower() + name[index + 1 :]
    return None


def filesystem_is_case_insensitive(git_root: Path, *, target_path: Path) -> bool:
    try:
        candidates = [git_root, *sorted(git_root.iterdir(), key=lambda path: path.name)]
        for candidate in candidates:
            alternate_name = alternate_ascii_case(candidate.name)
            if alternate_name is None:
                continue
            alternate_path = candidate.with_name(alternate_name)
            try:
                return candidate.samefile(alternate_path)
            except FileNotFoundError:
                return False
    except OSError as exc:
        raise CliFailure(
            "E-ENV-04",
            "E-ENV-04 Git追跡パスとの大小文字同一性をファイルシステム上で"
            f"確認できません: {target_path} (OSエラー={exc})",
            detail={"error": str(exc), "path": str(target_path)},
            remedy=(
                "リポジトリと親ディレクトリの読み取り権限を確認し、"
                "Gitまたはリポジトリを復旧してから再実行してください。"
            ),
        ) from exc
    raise CliFailure(
        "E-ENV-04",
        "E-ENV-04 Git追跡パスとの大小文字同一性を判定できる既存パスが"
        f"ありません: {target_path}",
        detail={"path": str(target_path)},
        remedy="Gitリポジトリの作業ツリーを復旧してから再実行してください。",
    )


def git_relative_path(
    candidate_path: Path,
    git_root: Path,
    *,
    case_insensitive: bool,
) -> str | None:
    try:
        return candidate_path.relative_to(git_root).as_posix()
    except ValueError:
        if not case_insensitive:
            return None
    root_parts = git_root.parts
    target_parts = candidate_path.parts
    if len(target_parts) < len(root_parts):
        return None
    if any(
        target_part.casefold() != root_part.casefold()
        for target_part, root_part in zip(target_parts, root_parts)
    ):
        return None
    return Path(*target_parts[len(root_parts) :]).as_posix()


def nearest_git_repository(
    path: Path,
    candidate_path: Path,
) -> tuple[Path, str, bool] | None:
    directory = candidate_path.parent
    while True:
        try:
            is_directory = directory.is_dir()
        except OSError as exc:
            raise CliFailure(
                "E-ENV-04",
                "E-ENV-04 Gitリポジトリ探索用のディレクトリを確認できません: "
                f"{directory} ({exc})",
                detail={"error": str(exc), "path": str(directory)},
                remedy=(
                    "出力先と親ディレクトリの読み取り権限を確認し、Gitまたは"
                    "リポジトリを復旧してから再実行してください。"
                ),
            ) from exc
        if is_directory:
            root_text = run_git_repository_query(path, directory)
            if root_text is not None:
                try:
                    git_root = Path(root_text).resolve()
                except (OSError, RuntimeError) as exc:
                    raise CliFailure(
                        "E-ENV-04",
                        "E-ENV-04 Gitリポジトリルートを安全に解決できません: "
                        f"{root_text} ({exc})",
                        detail={"error": str(exc), "path": root_text},
                        remedy=(
                            "Gitリポジトリの作業ツリーを復旧してから"
                            "再実行してください。"
                        ),
                    ) from exc
                case_insensitive = filesystem_is_case_insensitive(
                    git_root,
                    target_path=path,
                )
                relative_path = git_relative_path(
                    candidate_path,
                    git_root,
                    case_insensitive=case_insensitive,
                )
                if relative_path is None:
                    try:
                        resolved_directory = directory.resolve()
                        directory_suffix = resolved_directory.relative_to(git_root)
                    except (OSError, RuntimeError, ValueError):
                        directory_suffix = None
                    if directory_suffix is not None:
                        lexical_root = directory
                        if directory_suffix != Path("."):
                            for _part in directory_suffix.parts:
                                lexical_root = lexical_root.parent
                        try:
                            same_root = lexical_root.samefile(git_root)
                        except OSError:
                            same_root = False
                        if same_root:
                            relative_path = git_relative_path(
                                candidate_path,
                                lexical_root,
                                case_insensitive=case_insensitive,
                            )
                if relative_path is not None:
                    return git_root, relative_path, case_insensitive
        parent = directory.parent
        if parent == directory:
            return None
        directory = parent


def path_exists_in_git_head(path: Path) -> bool:
    lexical_path = Path(os.path.abspath(path))
    try:
        resolved_path = path.resolve()
    except (OSError, RuntimeError) as exc:
        raise CliFailure(
            "E-DATA-04",
            "E-DATA-04 正規化metaパスのsymlinkを安全に解決できません: "
            f"{path} ({exc})",
            detail={"error": str(exc), "path": str(path)},
            remedy=existing_meta_restore_remedy(path),
        ) from exc
    candidate_paths = [lexical_path]
    if resolved_path != lexical_path:
        candidate_paths.append(resolved_path)
    repositories: list[tuple[Path, str, bool]] = []
    for candidate_path in candidate_paths:
        repository = nearest_git_repository(path, candidate_path)
        if repository is None:
            repository_query = [
                "git",
                "-C",
                str(candidate_path.parent),
                "rev-parse",
                "--show-toplevel",
            ]
            run_git_head_query(path, repository_query, cwd=Path.cwd())
            raise CliFailure(
                "E-ENV-04",
                "E-ENV-04 正規化metaパスを包含するGitリポジトリを"
                f"特定できません: {candidate_path}",
                detail={"command": repository_query, "path": str(candidate_path)},
                remedy=(
                    "出力先を有効なHEADを持つGitリポジトリ内へ配置するか、"
                    "Gitリポジトリを復旧してから再実行してください。"
                ),
            )
        repositories.append(repository)
    repositories = list(dict.fromkeys(repositories))
    verified_roots: set[Path] = set()
    for git_root, _relative_path, _case_insensitive in repositories:
        if git_root not in verified_roots:
            head_query = ["git", "rev-parse", "--verify", "HEAD^{commit}"]
            run_git_head_query(path, head_query, cwd=git_root)
            verified_roots.add(git_root)
    for git_root, relative_path, case_insensitive in repositories:
        tree_query = [
            "git",
            "ls-tree",
            "--name-only",
            "-z",
            "HEAD",
            "--",
            relative_path,
        ]
        tree_result = run_git_head_query(path, tree_query, cwd=git_root)
        if tree_result.stdout.rstrip("\0"):
            return True
        if case_insensitive:
            all_paths_query = ["git", "ls-tree", "-r", "--name-only", "-z", "HEAD"]
            all_paths_result = run_git_head_query(
                path,
                all_paths_query,
                cwd=git_root,
            )
            tracked_paths = [
                tracked_path
                for tracked_path in all_paths_result.stdout.split("\0")
                if tracked_path
            ]
            if any(
                tracked_path.casefold() == relative_path.casefold()
                for tracked_path in tracked_paths
            ):
                return True
    return False


def existing_meta_document(meta_path: Path) -> dict[str, Any] | None:
    if meta_path.is_symlink() or (meta_path.exists() and not meta_path.is_file()):
        entry_type = "symlink" if meta_path.is_symlink() else "通常ファイル以外"
        raise CliFailure(
            "E-DATA-04",
            "E-DATA-04 既存meta.jsonのパスが通常ファイルではありません: "
            f"{meta_path} ({entry_type})",
            detail={"entry_type": entry_type, "path": str(meta_path)},
            remedy=existing_meta_restore_remedy(meta_path),
        )
    if not meta_path.exists():
        remaining_normalized = [
            name
            for name in NORMALIZED_FILE_NAMES
            if name != "meta.json" and (meta_path.parent / name).is_file()
        ]
        if remaining_normalized:
            raise CliFailure(
                "E-DATA-04",
                "E-DATA-04 既存正規化セットでmeta.jsonが欠落し、原本変更防止用の"
                f"安全根拠を取得できません: 残存{', '.join(remaining_normalized)}",
                detail={
                    "existing": remaining_normalized,
                    "missing": ["meta.json"],
                    "path": str(meta_path),
                },
                remedy=existing_meta_restore_remedy(meta_path),
            )
        if path_exists_in_git_head(meta_path):
            raise CliFailure(
                "E-DATA-04",
                "E-DATA-04 Git HEADに存在する正規化セットの3ファイルが全て欠落し、"
                f"原本変更防止用の安全根拠を取得できません: {meta_path.parent}",
                detail={
                    "head_path": str(meta_path),
                    "missing": list(NORMALIZED_FILE_NAMES),
                },
                remedy=existing_meta_restore_remedy(meta_path),
            )
        return None
    try:
        meta = load_json_file(meta_path, "E-DATA-04")
    except CliFailure as exc:
        raise CliFailure(
            "E-DATA-04",
            f"E-DATA-04 既存meta.jsonから原本変更防止用チェックサムを取得できません: {meta_path}",
            detail={"cause": exc.detail, "path": str(meta_path)},
            remedy=existing_meta_restore_remedy(meta_path),
        ) from exc
    problems = validate_meta_document(meta)
    safe_sources = existing_meta_safety_sources(meta)
    if safe_sources is None:
        raise CliFailure(
            "E-DATA-04",
            f"E-DATA-04 既存meta.jsonから原本変更防止用チェックサムを取得できません: {meta_path}",
            detail={"path": str(meta_path), "problems": problems},
            remedy=existing_meta_restore_remedy(meta_path),
        )
    return {"document": meta, "problems": problems, "sources": safe_sources}


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


def original_and_normalized_text(value: Any, *, field: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise ValueError(f"{field}が文字列ではありません: {value!r}")
    normalized = normalized_text(value, field=field, required=True)
    return value, normalized


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
    found, problems = collect_exact_headers(values, expected)
    raise_header_problems(problems, sheet_name=sheet_name)
    return found


def collect_exact_headers(
    values: list[Any],
    expected: Iterable[str],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    found: dict[str, int] = {}
    problems: list[dict[str, Any]] = []
    for header in expected:
        positions = [index for index, value in enumerate(values) if value == header]
        if len(positions) != 1:
            problems.append({"header": header, "positions": positions})
        else:
            found[header] = positions[0]
    return found, problems


def raise_header_problems(
    problems: list[dict[str, Any]],
    *,
    sheet_name: str,
) -> None:
    if problems:
        rendered = "; ".join(
            f"{problem['header']}="
            f"{problem['positions'] if problem['positions'] else '欠落'}"
            for problem in problems
        )
        raise CliFailure(
            "E-DATA-06",
            f"E-DATA-06 {sheet_name}で列名を一意に検出できません: {rendered}",
            detail={"headers": problems, "sheet": sheet_name},
        )


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


def excel_column_name(zero_based_index: int) -> str:
    value = zero_based_index + 1
    letters = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def collect_wordlist_value_problems(
    rows: list[tuple[Any, ...]],
    headers: dict[str, int],
    *,
    sheet_name: str,
    include_categories: bool,
) -> list[dict[str, Any]]:
    fields = list(WORDLIST_HEADERS if include_categories else WORDLIST_HEADERS[:3])
    problems: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=2):
        for field_name in fields:
            column_index = headers[field_name]
            value = row[column_index] if column_index < len(row) else None
            required = field_name in {"headword", "pos", "CEFR"}
            try:
                text = normalized_text(value, field=field_name, required=required)
            except ValueError as exc:
                reason = str(exc)
            else:
                reason = ""
                if sheet_name == "ALL_sep" and field_name == "headword" and ":" in text:
                    reason = f"headwordにコロンがあります: {text}"
                elif field_name == "pos" and text not in POS_VALUES:
                    reason = f"posが値域外です: {text}"
                elif field_name == "CEFR" and text not in CEFR_VALUES:
                    reason = f"CEFRが値域外です: {text}"
            if reason:
                problems.append(
                    {
                        "cell": (
                            f"{sheet_name}!{excel_column_name(column_index)}{row_number}"
                        ),
                        "column": column_index,
                        "field": field_name,
                        "reason": reason,
                        "row": row_number,
                    }
                )
    problems.sort(key=lambda problem: (problem["row"], problem["column"]))
    return [
        {key: value for key, value in problem.items() if key not in {"column", "row"}}
        for problem in problems
    ]


def raise_wordlist_value_problems(problems: list[dict[str, Any]]) -> None:
    if not problems:
        return
    rendered = "; ".join(
        f"{problem['cell']} {problem['reason']}" for problem in problems
    )
    raise CliFailure(
        "E-DATA-06",
        f"E-DATA-06 Wordlist原本の値が不正です: {rendered}",
        detail={"file": WORDLIST_FILE, "problems": problems},
    )


def collect_wordlist_group_problems(
    all_rows: list[tuple[Any, ...]],
    all_headers: dict[str, int],
    entries_by_key: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    headword_column = all_headers["headword"]
    seen_group_rows: dict[str, int] = {}
    problems: list[dict[str, Any]] = []
    kind_order = {
        "invalid_group_id": 0,
        "duplicate_group_id": 1,
        "empty_variant": 2,
        "missing_variant": 3,
        "duplicate_variant": 4,
        "level_mismatch": 5,
    }
    for row_number, row in enumerate(all_rows, start=2):
        _joined_original, joined = original_and_normalized_text(
            row[headword_column],
            field="ALL headword",
        )
        if "/" not in joined:
            continue
        pos = normalized_text(row[all_headers["pos"]], field="ALL pos", required=True)
        level = normalized_text(
            row[all_headers["CEFR"]],
            field="ALL CEFR",
            required=True,
        )
        variants = [
            unicodedata.normalize("NFC", part.strip()) for part in joined.split("/")
        ]
        cell = f"ALL!{excel_column_name(headword_column)}{row_number}"
        group_id = (
            f"grp:{variants[0]}:{pos.replace(' ', '-')}" if variants[0] else None
        )
        if variants[0] and ":" in variants[0]:
            problems.append(
                {
                    "cell": cell,
                    "kind": "invalid_group_id",
                    "reason": f"group_idの先頭variantにコロンがあります: {variants[0]}",
                    "row": row_number,
                    "variant": variants[0],
                    "variant_index": 0,
                }
            )
        if group_id is not None:
            first_row = seen_group_rows.get(group_id)
            if first_row is not None:
                problems.append(
                    {
                        "cell": cell,
                        "kind": "duplicate_group_id",
                        "reason": (
                            f"group_idが重複しています: {group_id} "
                            f"(初出ALL行{first_row})"
                        ),
                        "row": row_number,
                        "variant": variants[0],
                        "variant_index": 0,
                    }
                )
            else:
                seen_group_rows[group_id] = row_number

        seen_variants: set[str] = set()
        member_levels: set[str] = set()
        for variant_index, variant in enumerate(variants):
            if not variant:
                problems.append(
                    {
                        "cell": cell,
                        "kind": "empty_variant",
                        "reason": f"variant {variant_index + 1}が空です",
                        "row": row_number,
                        "variant": variant,
                        "variant_index": variant_index,
                    }
                )
                continue
            entry = entries_by_key.get((variant, pos))
            if entry is None:
                problems.append(
                    {
                        "cell": cell,
                        "kind": "missing_variant",
                        "reason": (
                            "variantに対応するALL_sep行がありません: "
                            f"{variant}/{pos}"
                        ),
                        "row": row_number,
                        "variant": variant,
                        "variant_index": variant_index,
                    }
                )
            else:
                member_levels.add(entry["level"])
            if variant in seen_variants:
                problems.append(
                    {
                        "cell": cell,
                        "kind": "duplicate_variant",
                        "reason": f"variantが重複しています: {variant}",
                        "row": row_number,
                        "variant": variant,
                        "variant_index": variant_index,
                    }
                )
            else:
                seen_variants.add(variant)
        if member_levels and member_levels != {level}:
            problems.append(
                {
                    "cell": cell,
                    "kind": "level_mismatch",
                    "reason": (
                        f"グループ内レベルが一致しません: 期待{level} "
                        f"実測{sorted(member_levels)}"
                    ),
                    "row": row_number,
                    "variant": None,
                    "variant_index": len(variants),
                }
            )
    problems.sort(
        key=lambda problem: (
            problem["row"],
            problem["variant_index"],
            kind_order[problem["kind"]],
        )
    )
    return [
        {
            key: value
            for key, value in problem.items()
            if key not in {"row", "variant_index"}
        }
        for problem in problems
    ]


def raise_wordlist_group_problems(problems: list[dict[str, Any]]) -> None:
    if not problems:
        return
    rendered = "; ".join(
        f"{problem['cell']} {problem['reason']}" for problem in problems
    )
    raise CliFailure(
        "E-DATA-06",
        f"E-DATA-06 Wordlist原本のALL併記グループが不正です: {rendered}",
        detail={"file": WORDLIST_FILE, "problems": problems},
    )


def build_lexicon(
    source_path: Path,
    *,
    data_version: str,
) -> tuple[dict[str, Any], dict[str, int]]:
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
        wordlist_headers: dict[str, dict[str, int]] = {}
        for sheet_name in required_sheets:
            wordlist_headers[sheet_name] = ensure_exact_headers(
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

        all_sep_headers = wordlist_headers["ALL_sep"]
        all_headers = wordlist_headers["ALL"]
        wordlist_value_problems = collect_wordlist_value_problems(
            all_sep_rows,
            all_sep_headers,
            sheet_name="ALL_sep",
            include_categories=True,
        )
        wordlist_value_problems.extend(
            collect_wordlist_value_problems(
                all_rows,
                all_headers,
                sheet_name="ALL",
                include_categories=False,
            )
        )
        raise_wordlist_value_problems(wordlist_value_problems)

        entries_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for row_number, row in enumerate(all_sep_rows, start=2):
            headword = normalized_text(
                row[all_sep_headers["headword"]],
                field="headword",
                required=True,
            )
            pos = normalized_text(
                row[all_sep_headers["pos"]],
                field="pos",
                required=True,
            )
            level = normalized_text(
                row[all_sep_headers["CEFR"]],
                field="CEFR",
                required=True,
            )
            if ":" in headword:
                raise ValueError(f"ALL_sep!A{row_number} headwordにコロンがあります: {headword}")
            if pos not in POS_VALUES:
                raise ValueError(f"ALL_sep!B{row_number} posが値域外です: {pos}")
            if level not in CEFR_VALUES:
                raise ValueError(f"ALL_sep!C{row_number} CEFRが値域外です: {level}")
            entry = {
                "core_inventory_1": normalized_text(
                    row[all_sep_headers["CoreInventory 1"]],
                    field="CoreInventory 1",
                    required=False,
                ),
                "core_inventory_2": normalized_text(
                    row[all_sep_headers["CoreInventory 2"]],
                    field="CoreInventory 2",
                    required=False,
                ),
                "group_ids": [],
                "headword": headword,
                "id": lex_id(headword, pos),
                "is_multiword": " " in headword or "-" in headword,
                "level": level,
                "pos": pos,
                "threshold": normalized_text(
                    row[all_sep_headers["Threshold"]],
                    field="Threshold",
                    required=False,
                ),
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

        group_problems = collect_wordlist_group_problems(
            all_rows,
            all_headers,
            entries_by_key,
        )
        raise_wordlist_group_problems(group_problems)

        groups: list[dict[str, Any]] = []
        seen_group_ids: set[str] = set()
        for row_number, row in enumerate(all_rows, start=2):
            joined_original, joined = original_and_normalized_text(
                row[all_headers["headword"]],
                field="ALL headword",
            )
            pos = normalized_text(
                row[all_headers["pos"]],
                field="ALL pos",
                required=True,
            )
            level = normalized_text(
                row[all_headers["CEFR"]],
                field="ALL CEFR",
                required=True,
            )
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
                    "headword_joined": joined_original,
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
            "data_version": data_version,
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
    found, problems = collect_exact_headers(values, ITEM_HEADERS_EXACT)
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
            problems.append({"header": f"{prefix}*", "positions": positions})
        else:
            found[key] = positions[0]
    raise_header_problems(problems, sheet_name="ITEM LIST")
    return found


def numeric_value(value: Any, *, field: str, integer: bool) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field}が数値ではありません: {value!r}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{field}が有限数ではありません: {value!r}")
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
    if match.group(2) is not None and CEFRJ_RANK[minimum] >= CEFRJ_RANK[maximum]:
        raise ValueError(f"{field}のレベル範囲が昇順ではありません: {raw}")
    return raw, minimum, maximum


def grammar_sort_key(entry: dict[str, Any]) -> tuple[int, int, int]:
    parts = entry["item_list_id"].split("-")
    parent = int(parts[0])
    if len(parts) == 1:
        return parent, 0, 0
    return parent, 1, int(parts[1])


def grammar_value_reason(value: Any, specification: dict[str, Any]) -> str | None:
    field = specification["field"]
    kind = specification["kind"]
    try:
        if kind == "id":
            normalized_id(value, field=field)
            parsed = None
        elif kind == "level":
            parse_level(value, field=field)
            parsed = None
        elif kind == "text":
            normalized_text(
                value,
                field=field,
                required=specification.get("required", False),
                trim=specification.get("trim", True),
            )
            parsed = None
        elif kind == "number":
            parsed = numeric_value(
                value,
                field=field,
                integer=specification.get("integer", False),
            )
            if specification.get("required", False) and parsed is None:
                raise ValueError(f"{field}が空です")
        else:
            raise AssertionError(f"未知のGrammar値検査種別です: {kind}")
    except ValueError as exc:
        return str(exc)
    minimum = specification.get("minimum")
    if "minimum" in specification and parsed is not None and parsed < minimum:
        return f"{field}が最小値未満です: 最小{minimum!r} 実測{parsed!r}"
    expected = specification.get("expected")
    if "expected" in specification and parsed != expected:
        return f"{field}が期待値と不一致です: 期待{expected!r} 実測{parsed!r}"
    return None


def collect_grammar_value_problems(
    item_rows: list[tuple[Any, ...]],
    teacher_rows: list[tuple[Any, ...]],
    efl_rows: list[tuple[Any, ...]],
    corpus_row: list[Any],
    item_headers: dict[str, int],
    teacher_headers: dict[str, int],
) -> list[dict[str, Any]]:
    item_fields = {
        "ID": {"field": "ID", "kind": "id"},
        "文法項目": {"field": "文法項目", "kind": "text", "required": True},
        "文タイプ(不問のものは空欄)": {
            "field": "文タイプ",
            "kind": "text",
            "trim": False,
        },
        "Shorthand Code": {"field": "Shorthand Code", "kind": "text"},
        "Grammatical Item": {"field": "Grammatical Item", "kind": "text"},
        "備考": {"field": "備考", "kind": "text", "trim": False},
        "パターン略記": {"field": "パターン略記", "kind": "text"},
        "sentence_type_en": {
            "field": "Sentence Type (...)",
            "kind": "text",
            "trim": False,
        },
        "regex_treetagger": {
            "field": "正規表現(TreeTaggerベース...)",
            "kind": "text",
        },
    }
    teacher_fields = {
        "ID": {"field": "ID", "kind": "id"},
        "文法項目": {
            "field": "教員版 文法項目",
            "kind": "text",
            "required": True,
        },
        "文法項目 (平易版)": {
            "field": "文法項目 (平易版)",
            "kind": "text",
            "required": True,
        },
        "Grammatical item (English)": {
            "field": "Grammatical item (English)",
            "kind": "text",
        },
        "CEFR-J level": {"field": "CEFR-J level", "kind": "level"},
    }
    levels = ("A1", "A2", "B1", "B2", "C1")
    efl_fields = [{"column": 0, "field": "ID", "kind": "id"}]
    efl_fields.extend(
        {
            "column": 6 + index,
            "field": f"rel_freq {level}",
            "kind": "number",
        }
        for index, level in enumerate(levels)
    )
    efl_fields.extend(
        {
            "column": 12 + index,
            "field": f"range {level}",
            "integer": True,
            "kind": "number",
        }
        for index, level in enumerate(levels)
    )
    corpus_fields = [
        {
            "column": 6 + index,
            "field": f"corpus words {level}",
            "integer": True,
            "kind": "number",
            "minimum": 0,
            "required": True,
        }
        for index, level in enumerate(levels)
    ]
    expected_books = (17, 21, 26, 23, 8)
    corpus_fields.extend(
        {
            "column": 12 + index,
            "expected": expected_books[index],
            "field": f"corpus books {level}",
            "integer": True,
            "kind": "number",
            "required": True,
        }
        for index, level in enumerate(levels)
    )

    sources: list[tuple[int, str, int, list[Any], list[dict[str, Any]]]] = []
    item_specifications = [
        {"column": item_headers[key], **specification}
        for key, specification in item_fields.items()
    ]
    teacher_specifications = [
        {"column": teacher_headers[key], **specification}
        for key, specification in teacher_fields.items()
    ]
    for row_number, row in enumerate(item_rows, start=3):
        sources.append((0, "ITEM LIST", row_number, list(row), item_specifications))
    for row_number, row in enumerate(teacher_rows, start=3):
        sources.append((1, "教員版", row_number, list(row), teacher_specifications))
    sources.append((2, "EFL SUMMARY (FULL)", 1, corpus_row, corpus_fields))
    for row_number, row in enumerate(efl_rows, start=4):
        sources.append((2, "EFL SUMMARY (FULL)", row_number, list(row), efl_fields))

    problems: list[dict[str, Any]] = []
    for sheet_order, sheet_name, row_number, row, specifications in sources:
        for specification in specifications:
            column_index = specification["column"]
            value = row[column_index] if column_index < len(row) else None
            reason = grammar_value_reason(value, specification)
            if reason is not None:
                problems.append(
                    {
                        "cell": (
                            f"{sheet_name}!{excel_column_name(column_index)}{row_number}"
                        ),
                        "column": column_index,
                        "field": specification["field"],
                        "reason": reason,
                        "row": row_number,
                        "sheet_order": sheet_order,
                    }
                )
    problems.sort(
        key=lambda problem: (
            problem["sheet_order"],
            problem["row"],
            problem["column"],
        )
    )
    return [
        {
            key: value
            for key, value in problem.items()
            if key not in {"column", "row", "sheet_order"}
        }
        for problem in problems
    ]


def raise_grammar_value_problems(problems: list[dict[str, Any]]) -> None:
    if not problems:
        return
    rendered = "; ".join(
        f"{problem['cell']} {problem['reason']}" for problem in problems
    )
    raise CliFailure(
        "E-DATA-06",
        f"E-DATA-06 Grammar Profile原本の値が不正です: {rendered}",
        detail={"file": GRAMMAR_FILE, "problems": problems},
    )


def collect_grammar_id_problems(
    item_rows: list[tuple[Any, ...]],
    teacher_rows: list[tuple[Any, ...]],
    efl_rows: list[tuple[Any, ...]],
    item_headers: dict[str, int],
    teacher_headers: dict[str, int],
) -> list[dict[str, Any]]:
    sheet_inputs = (
        (0, "ITEM LIST", item_rows, 3, item_headers["ID"]),
        (1, "教員版", teacher_rows, 3, teacher_headers["ID"]),
        (2, "EFL SUMMARY (FULL)", efl_rows, 4, 0),
    )
    occurrences_by_sheet: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for _sheet_order, sheet_name, rows, start_row, column_index in sheet_inputs:
        occurrences: dict[str, list[dict[str, Any]]] = {}
        for row_number, row in enumerate(rows, start=start_row):
            item_id = normalized_id(row[column_index], field=f"{sheet_name} ID")
            occurrences.setdefault(item_id, []).append(
                {
                    "cell": (
                        f"{sheet_name}!{excel_column_name(column_index)}{row_number}"
                    ),
                    "row": row_number,
                }
            )
        occurrences_by_sheet[sheet_name] = occurrences

    item_ids = set(occurrences_by_sheet["ITEM LIST"])
    problems: list[dict[str, Any]] = []
    for sheet_order, sheet_name, _rows, _start_row, _column_index in sheet_inputs:
        occurrences = occurrences_by_sheet[sheet_name]
        for item_id, locations in occurrences.items():
            if len(locations) > 1:
                problems.append(
                    {
                        "cells": [location["cell"] for location in locations],
                        "id": item_id,
                        "kind": "duplicate_id",
                        "row": locations[0]["row"],
                        "sheet": sheet_name,
                        "sheet_order": sheet_order,
                    }
                )
            if sheet_name == "ITEM LIST" or item_id in item_ids:
                continue
            for location in locations:
                problems.append(
                    {
                        "cell": location["cell"],
                        "id": item_id,
                        "kind": "missing_item_list_id",
                        "row": location["row"],
                        "sheet": sheet_name,
                        "sheet_order": sheet_order,
                    }
                )
    problems.sort(
        key=lambda problem: (
            problem["sheet_order"],
            problem["row"],
            problem["id"],
            problem["kind"],
        )
    )
    return [
        {
            key: value
            for key, value in problem.items()
            if key not in {"row", "sheet_order"}
        }
        for problem in problems
    ]


def raise_grammar_id_problems(problems: list[dict[str, Any]]) -> None:
    if not problems:
        return
    rendered: list[str] = []
    for problem in problems:
        if problem["kind"] == "duplicate_id":
            rendered.append(
                f"{problem['sheet']} ID重複 {problem['id']}: "
                f"{', '.join(problem['cells'])}"
            )
        else:
            rendered.append(
                f"{problem['cell']} IDがITEM LISTにありません: {problem['id']}"
            )
    raise CliFailure(
        "E-DATA-06",
        "E-DATA-06 Grammar Profile原本のID結合が不正です: "
        + "; ".join(rendered),
        detail={"file": GRAMMAR_FILE, "problems": problems},
    )


def build_grammar(
    source_path: Path,
    *,
    data_version: str,
) -> tuple[dict[str, Any], dict[str, int]]:
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

        corpus_row = [cell.value for cell in efl_sheet[1]]
        grammar_value_problems = collect_grammar_value_problems(
            item_rows,
            teacher_rows,
            efl_rows,
            corpus_row,
            item_headers,
            teacher_headers,
        )
        raise_grammar_value_problems(grammar_value_problems)
        grammar_id_problems = collect_grammar_id_problems(
            item_rows,
            teacher_rows,
            efl_rows,
            item_headers,
            teacher_headers,
        )
        raise_grammar_id_problems(grammar_id_problems)

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
        missing_parents = sorted(
            [
                {
                    "child_id": child_id,
                    "parent_id": child_id.split("-", 1)[0],
                }
                for child_id in child_ids
                if child_id.split("-", 1)[0] not in parent_ids
            ],
            key=lambda item: tuple(int(part) for part in item["child_id"].split("-")),
        )
        if missing_parents:
            rendered = "; ".join(
                f"{item['child_id']} -> {item['parent_id']}"
                for item in missing_parents
            )
            raise CliFailure(
                "E-DATA-06",
                f"E-DATA-06 枝番の親IDがありません: {rendered}",
                detail={"missing_parents": missing_parents},
            )

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
            "data_version": data_version,
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
    data_version: str,
    model_version: str,
    lexicon_count: int,
    group_count: int,
    grammar_count: int,
    target_count: int,
) -> dict[str, Any]:
    return {
        "counts": {
            "grammar_items": grammar_count,
            "lexicon_entries": lexicon_count,
            "lexicon_groups": group_count,
            "target_eligible": target_count,
        },
        "data_version": data_version,
        "pipeline_version": PIPELINE_VERSION,
        "sources": [
            {
                "file": source["file"],
                "retrieved_date": source["download_date"],
                "role": source["role"],
                "sha256": checksums[source["file"]],
                "url": source["url"],
                "version_label": source["version_label"],
            }
            for source in sources
        ],
        "spacy_model": {"name": MODEL_NAME, "version": model_version},
    }


def validate_meta_document(
    meta: Any,
    *,
    expected_data_version: str | None = None,
) -> list[str]:
    problems: list[str] = []
    if not isinstance(meta, dict) or set(meta) != {
        "counts",
        "data_version",
        "pipeline_version",
        "sources",
        "spacy_model",
    }:
        return ["トップレベルキーがNRM-29と一致しません"]
    data_version = meta.get("data_version")
    if not isinstance(data_version, str) or not DATA_VERSION_PATTERN.fullmatch(data_version):
        problems.append("data_versionの書式が不正です")
    elif expected_data_version is not None and data_version != expected_data_version:
        problems.append(f"data_versionが期待値と不一致です: {data_version} != {expected_data_version}")
    pipeline_version = meta.get("pipeline_version")
    if not isinstance(pipeline_version, str) or not SEMVER_PATTERN.fullmatch(pipeline_version):
        problems.append("pipeline_versionの書式が不正です")
    model = meta.get("spacy_model")
    if not isinstance(model, dict) or set(model) != {"name", "version"}:
        problems.append("spacy_modelの構造が不正です")
    else:
        if model.get("name") != MODEL_NAME:
            problems.append(
                f"spacy_model.nameが期待値と不一致です: "
                f"期待{MODEL_NAME} 実測{model.get('name')}"
            )
        if model.get("version") != MODEL_VERSION:
            problems.append(
                f"spacy_model.versionが期待値と不一致です: "
                f"期待{MODEL_VERSION} 実測{model.get('version')}"
            )
    counts = meta.get("counts")
    count_keys = {"lexicon_entries", "lexicon_groups", "grammar_items", "target_eligible"}
    if not isinstance(counts, dict) or set(counts) != count_keys:
        problems.append("countsの構造が不正です")
    elif any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts.values()):
        problems.append("countsに0以上の整数でない値があります")
    sources = meta.get("sources")
    expected = (("wordlist", WORDLIST_FILE), ("grammar_profile", GRAMMAR_FILE))
    source_versions: dict[str, str] = {}
    if not isinstance(sources, list) or len(sources) != 2:
        problems.append("sourcesは2要素でなければなりません")
    else:
        for index, (role, file_name) in enumerate(expected):
            source = sources[index]
            required_keys = {"role", "file", "sha256", "version_label", "url", "retrieved_date"}
            if not isinstance(source, dict) or set(source) != required_keys:
                problems.append(f"sources[{index}]の構造が不正です")
                continue
            if source["role"] != role or source["file"] != file_name:
                problems.append(f"sources[{index}]の固定値が不正です")
            version_label = source.get("version_label")
            if not isinstance(version_label, str) or not VERSION_LABEL_PATTERN.fullmatch(version_label):
                problems.append(f"sources[{index}].version_labelが不正です")
            else:
                source_versions[role] = version_label
            if not isinstance(source["sha256"], str) or not SHA256_PATTERN.fullmatch(source["sha256"]):
                problems.append(f"sources[{index}].sha256が不正です")
            if not isinstance(source["url"], str) or not re.match(r"^https?://", source["url"]):
                problems.append(f"sources[{index}].urlが不正です")
            if not isinstance(source["retrieved_date"], str) or not DATE_PATTERN.fullmatch(source["retrieved_date"]):
                problems.append(f"sources[{index}].retrieved_dateが不正です")
    if (
        isinstance(pipeline_version, str)
        and SEMVER_PATTERN.fullmatch(pipeline_version)
        and set(source_versions) == {"wordlist", "grammar_profile"}
    ):
        derived_data_version = compose_data_version(
            source_versions["wordlist"],
            source_versions["grammar_profile"],
            pipeline_version,
        )
        if data_version != derived_data_version:
            problems.append(
                f"data_versionがsourcesとpipeline_versionからの導出値に不一致です: "
                f"{data_version} != {derived_data_version}"
            )
    return problems


def one_line_text(value: Any) -> str:
    return " ".join(str(value).splitlines())


def render_normalized_problems(
    problems: list[Any],
    current_mismatches: list[dict[str, str]],
) -> str:
    rendered: list[str] = []
    for problem in problems:
        if "lexicon" in problem or "grammar" in problem:
            target = "lexicon" if "lexicon" in problem else "grammar"
            errors = problem[target]
            total = problem["total"]
            error_text = ", ".join(
                f"{error['json_pointer'] or '/'} {one_line_text(error['message'])}"
                for error in errors
            )
            qualifier = f"先頭{len(errors)}件: " if total > len(errors) else ""
            rendered.append(
                f"{target}スキーマ違反（総数{total}件）: {qualifier}{error_text}"
            )
        elif "meta" in problem:
            rendered.extend(
                f"meta不整合: {one_line_text(message)}"
                for message in problem["meta"]
            )
        elif "data_versions" in problem:
            values = json.dumps(
                problem["data_versions"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            rendered.append(f"3ファイルのdata_versionが不一致です: {values}")
        elif "actual_counts" in problem:
            expected = json.dumps(
                problem["actual_counts"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            actual = json.dumps(
                problem["meta_counts"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            rendered.append(f"meta.counts不一致: 期待{expected} 実測{actual}")
        elif "count_error" in problem:
            rendered.append(f"件数検査不能: {one_line_text(problem['count_error'])}")
        else:
            rendered.append(
                json.dumps(
                    problem,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
    rendered.extend(
        f"{item['field']} 期待{item['expected']} 実測{item['actual']}"
        for item in current_mismatches
    )
    return "; ".join(rendered)


def raise_normalized_data_failure(
    normalized_dir: Path,
    problems: list[Any],
    current_mismatches: list[dict[str, str]],
) -> None:
    detail: dict[str, Any] = {"problems": problems}
    if current_mismatches:
        detail["mismatches"] = current_mismatches
    raise CliFailure(
        "E-DATA-04",
        "E-DATA-04 正規化データのスキーマ・内部整合・現在値との整合が不正です: "
        f"{normalized_dir}: {render_normalized_problems(problems, current_mismatches)}",
        detail=detail,
    )


def validate_normalized_set(
    repo_root: Path,
    normalized_dir: Path,
    *,
    expected_data_version: str | None = None,
    expected_pipeline_version: str | None = None,
    expected_source_versions: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
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
    current_mismatches: list[dict[str, str]] = []

    def compare_current(field: str, expected: str, actual: str) -> None:
        if actual != expected:
            current_mismatches.append(
                {"actual": actual, "expected": expected, "field": field}
            )

    def safe_data_version(document: Any) -> str | None:
        if isinstance(document, dict) and isinstance(document.get("data_version"), str):
            return document["data_version"]
        return None

    lexicon_data_version = safe_data_version(lexicon)
    grammar_data_version = safe_data_version(grammar)
    meta_data_version = safe_data_version(meta)
    if expected_data_version is not None and lexicon_data_version is not None:
        compare_current("lexicon.data_version", expected_data_version, lexicon_data_version)
    if expected_data_version is not None and grammar_data_version is not None:
        compare_current("grammar.data_version", expected_data_version, grammar_data_version)
    if expected_data_version is not None and meta_data_version is not None:
        compare_current("meta.data_version", expected_data_version, meta_data_version)
    if (
        expected_pipeline_version is not None
        and isinstance(meta, dict)
        and isinstance(meta.get("pipeline_version"), str)
    ):
        compare_current(
            "meta.pipeline_version",
            expected_pipeline_version,
            meta["pipeline_version"],
        )
    if expected_source_versions is not None and isinstance(meta, dict):
        sources = meta.get("sources")
        meta_sources: dict[str, Any] = {}
        if isinstance(sources, list):
            meta_sources = {
                source.get("role"): source
                for source in sources
                if isinstance(source, dict) and isinstance(source.get("role"), str)
            }
        for role in ("wordlist", "grammar_profile"):
            source = meta_sources.get(role)
            if isinstance(source, dict) and isinstance(source.get("version_label"), str):
                compare_current(
                    f"meta.sources[{role}].version_label",
                    expected_source_versions[role],
                    source["version_label"],
                )
    if all(
        value is not None
        for value in (lexicon_data_version, grammar_data_version, meta_data_version)
    ):
        versions = {
            lexicon_data_version,
            grammar_data_version,
            meta_data_version,
        }
        if len(versions) != 1:
            problems.append({"data_versions": sorted(versions)})
    if problems or current_mismatches:
        raise_normalized_data_failure(normalized_dir, problems, current_mismatches)
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
        raise_normalized_data_failure(normalized_dir, problems, [])
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


def stage_json_text(path: Path, text: str) -> Path:
    descriptor: int | None = None
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            descriptor = None
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        return temporary
    except OSError as exc:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def backup_regular_file(path: Path) -> Path:
    descriptor: int | None = None
    backup: Path | None = None
    try:
        descriptor, backup_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".backup", dir=path.parent
        )
        backup = Path(backup_name)
        os.close(descriptor)
        descriptor = None
        backup.unlink()
        os.link(path, backup)
        return backup
    except OSError:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if backup is not None:
            try:
                backup.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def cleanup_temporary_paths(paths: Iterable[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def validate_output_targets(out_dir: Path) -> None:
    invalid: list[dict[str, str]] = []
    for file_name in NORMALIZED_FILE_NAMES:
        path = out_dir / file_name
        if path.is_symlink():
            invalid.append({"entry_type": "symlink", "path": str(path)})
        elif path.exists() and not path.is_file():
            invalid.append({"entry_type": "通常ファイル以外", "path": str(path)})
    if invalid:
        details = "; ".join(
            f"{item['path']} ({item['entry_type']})" for item in invalid
        )
        raise CliFailure(
            "E-ENV-05",
            f"E-ENV-05 正規化JSONの最終パスを置換できません: {details}",
            detail={"invalid_targets": invalid},
        )


def write_normalized_set(out_dir: Path, output_texts: dict[str, str]) -> None:
    staged: dict[str, Path] = {}
    backups: dict[str, Path] = {}
    committed: list[str] = []
    active_path = out_dir
    phase = "一時ファイル準備"
    try:
        for file_name in NORMALIZED_FILE_NAMES:
            active_path = out_dir / file_name
            staged[file_name] = stage_json_text(active_path, output_texts[file_name])

        validate_output_targets(out_dir)
        phase = "既存ファイル退避"
        for file_name in NORMALIZED_FILE_NAMES:
            active_path = out_dir / file_name
            if active_path.exists():
                backups[file_name] = backup_regular_file(active_path)

        phase = "確定"
        for file_name in NORMALIZED_FILE_NAMES:
            active_path = out_dir / file_name
            os.replace(staged[file_name], active_path)
            del staged[file_name]
            committed.append(file_name)
    except CliFailure:
        cleanup_temporary_paths(staged.values())
        cleanup_temporary_paths(backups.values())
        raise
    except OSError as exc:
        rollback_errors: list[dict[str, str]] = []
        preserved_backups: set[Path] = set()
        for file_name in reversed(committed):
            path = out_dir / file_name
            try:
                if file_name in backups:
                    os.replace(backups[file_name], path)
                    del backups[file_name]
                else:
                    path.unlink(missing_ok=True)
            except OSError as rollback_exc:
                problem = {"error": str(rollback_exc), "path": str(path)}
                if file_name in backups:
                    backup = backups[file_name]
                    preserved_backups.add(backup)
                    problem["backup_path"] = str(backup)
                rollback_errors.append(problem)
        cleanup_temporary_paths(staged.values())
        cleanup_temporary_paths(
            backup for backup in backups.values() if backup not in preserved_backups
        )
        restoration = (
            "復元にも失敗しました"
            if rollback_errors
            else "更新前の正規化セットへ復元しました"
        )
        detail: dict[str, Any] = {
            "error": str(exc),
            "path": str(active_path),
            "phase": phase,
        }
        if rollback_errors:
            detail["rollback_errors"] = rollback_errors
        raise CliFailure(
            "E-ENV-05",
            f"E-ENV-05 正規化JSONの{phase}に失敗し、{restoration}: "
            f"{active_path} ({exc})",
            detail=detail,
        ) from exc
    cleanup_temporary_paths(backups.values())


def ensure_output_writable(out_dir: Path) -> None:
    descriptor: int | None = None
    probe: Path | None = None
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        if not out_dir.is_dir():
            raise NotADirectoryError(f"ディレクトリではありません: {out_dir}")
        validate_output_targets(out_dir)
        descriptor, probe_name = tempfile.mkstemp(prefix=".write-check.", dir=out_dir)
        probe = Path(probe_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(b"doctor")
            stream.flush()
            os.fsync(stream.fileno())
        probe.unlink()
    except OSError as exc:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if probe is not None:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass
        raise CliFailure(
            "E-ENV-05",
            f"E-ENV-05 出力ディレクトリを作成または書き込みできません: {out_dir} ({exc})",
            detail={"error": str(exc), "path": str(out_dir)},
        ) from exc


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

    if not args.dry_run and not args.diff:
        ensure_output_writable(out_dir)

    sources = load_sources(source_dir)
    data_version = source_data_version(sources)
    checksums = source_checksums(source_dir)
    if args.diff:
        missing = [name for name in NORMALIZED_FILE_NAMES if not (out_dir / name).is_file()]
        if missing:
            raise CliFailure(
                "E-INPUT-02",
                f"E-INPUT-02 --diffに必要な既存正規化データがありません: {', '.join(missing)}",
                detail={"missing": missing, "out_dir": str(out_dir)},
            )
    existing_meta = existing_meta_document(out_dir / "meta.json")
    if existing_meta is not None:
        if args.diff and existing_meta["problems"]:
            raise CliFailure(
                "E-DATA-04",
                f"E-DATA-04 --diffに必要な既存meta.jsonがNRM-29に適合しません: {out_dir / 'meta.json'}",
                detail={
                    "path": str(out_dir / "meta.json"),
                    "problems": existing_meta["problems"],
                },
                remedy=existing_meta_restore_remedy(out_dir / "meta.json"),
            )
        existing_checksums = {
            source["file"]: source["sha256"] for source in existing_meta["sources"]
        }
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
        if mismatches and args.accept_source_change:
            old_versions = {
                source["file"]: source["version_label"] for source in existing_meta["sources"]
            }
            new_versions = {source["file"]: source["version_label"] for source in sources}
            missing_old_versions = [
                item["file"]
                for item in mismatches
                if old_versions[item["file"]] is None
            ]
            if missing_old_versions:
                raise CliFailure(
                    "E-DATA-04",
                    "E-DATA-04 --accept-source-changeの安全確認に必要な既存版を"
                    f"meta.jsonから取得できません: {', '.join(missing_old_versions)}",
                    detail={
                        "files": missing_old_versions,
                        "path": str(out_dir / "meta.json"),
                    },
                    remedy=existing_meta_restore_remedy(out_dir / "meta.json"),
                )
            unchanged_versions = [
                {
                    "actual": item["actual"],
                    "expected": item["expected"],
                    "file": item["file"],
                    "new_version": new_versions[item["file"]],
                    "old_version": old_versions[item["file"]],
                }
                for item in mismatches
                if new_versions[item["file"]] == old_versions[item["file"]]
            ]
            if unchanged_versions:
                details = "; ".join(
                    f"{item['file']} 期待SHA-256 {item['expected']} 実測SHA-256 {item['actual']} "
                    f"旧版{item['old_version']} 新版{item['new_version']}"
                    for item in unchanged_versions
                )
                raise CliFailure(
                    "E-DATA-02",
                    f"E-DATA-02 原本チェックサム変更に対してversion_labelが未更新です: {details}",
                    detail={
                        "mismatches": mismatches,
                        "unchanged_versions": unchanged_versions,
                    },
                )

    lexicon, lexicon_stats = build_lexicon(
        source_dir / WORDLIST_FILE,
        data_version=data_version,
    )
    grammar, grammar_stats = build_grammar(
        source_dir / GRAMMAR_FILE,
        data_version=data_version,
    )
    meta = build_meta(
        sources,
        checksums,
        data_version=data_version,
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
    meta_problems = validate_meta_document(meta, expected_data_version=data_version)
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
        output_texts = {
            file_name: canonical_json_text(output_values[file_name])
            for file_name in NORMALIZED_FILE_NAMES
        }
        write_normalized_set(out_dir, output_texts)
        written.extend(
            relative_path(out_dir / file_name, repo_root)
            for file_name in NORMALIZED_FILE_NAMES
        )

    summary = {
        "counts": {
            "grammar_items": grammar_stats["entries"],
            "lexicon_entries": lexicon_stats["entries"],
        },
        "data_version": data_version,
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
