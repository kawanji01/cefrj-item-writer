#!/usr/bin/env python3
"""CEFR-J作問環境とデータ整合を12項目で一括診断する。"""

from __future__ import annotations

import argparse
import importlib
import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

from build_normalized import (
    MODEL_NAME,
    MODEL_VERSION,
    NORMALIZED_FILE_NAMES,
    PIPELINE_VERSION,
    REQUIRED_PACKAGES,
    SCHEMA_FILES,
    SOURCE_FILE_NAMES,
    CliFailure,
    checksum_mismatches,
    dependency_issues,
    emit_json,
    load_json_file,
    load_sources,
    load_spacy_model,
    schema_errors,
    source_checksums,
    source_data_version,
    strict_json_loads,
    validate_meta_document,
    validate_normalized_set,
)


REMEDIES = {
    "E-ENV-01": "Python 3.11以上をインストールし、python scripts/setup.py でvenvを再作成してください。",
    "E-ENV-02": "リポジトリルートで python scripts/setup.py を再実行してください。",
    "E-ENV-03": "リポジトリルートで python scripts/setup.py を再実行し、en_core_web_sm 3.8.0を取得してください。",
    "E-ENV-04": "リポジトリルートに移動してください。ファイル欠落時は git status で確認し git checkout で復元してください。",
    "E-ENV-05": "output/の権限と空き容量を確認してください。",
    "E-ENV-06": "docs/cross-agent-compatibility.mdに従い、.claude/agents/またはcodexコマンドの配線を整備してください。",
    "E-DATA-01": "原本2ファイルを固定名でdata/source/に配置し、sources.jsonに原本版・入手URL・ダウンロード日を記入してください。",
    "E-DATA-02": "意図的な原本更新はsources.jsonの対応するversion_labelも更新し、python scripts/build_normalized.py --diff で確認後、python scripts/build_normalized.py --accept-source-change を実行してください。意図しない場合は正しい原本を配置し直してください。",
    "E-DATA-03": "git checkoutで復元するか、python scripts/build_normalized.py を実行してください。",
    "E-DATA-04": "python scripts/build_normalized.py で再ビルドしてください。同じE-DATA-04で停止する場合は git checkout -- data/normalized/meta.json でコミット済みmetaを復元してから再ビルドしてください。再発時は正規化パイプラインの不具合として報告してください。",
    "E-DATA-05": "git checkoutで設定を復元し、python scripts/validate.py --schema config_limits --file data/config/limits.json で違反箇所を確認してください。generation_maxは1〜3にしてください。",
}

MAX_SCHEMA_GENERATION = 3


class DoctorArgumentParser(argparse.ArgumentParser):
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
        raise CliFailure(
            "E-INPUT-01",
            f"E-INPUT-01 doctor.pyの引数が不正です: {translated}",
            detail={"parser_message": message},
            remedy="python scripts/doctor.py --help の日本語ヘルプを参照して引数を修正してください。",
        )


def check_result(
    check_id: str,
    name: str,
    *,
    status: str,
    message: str,
    error_code: str | None = None,
    remedy: str | None = None,
) -> dict[str, Any]:
    return {
        "error_code": error_code,
        "id": check_id,
        "message": message,
        "name": name,
        "remedy": remedy,
        "status": status,
    }


def passed(check_id: str, name: str, message: str) -> dict[str, Any]:
    return check_result(check_id, name, status="pass", message=message)


def failed(check_id: str, name: str, error_code: str, message: str) -> dict[str, Any]:
    return check_result(
        check_id,
        name,
        status="fail",
        error_code=error_code,
        message=message,
        remedy=REMEDIES[error_code],
    )


def check_python() -> dict[str, Any]:
    name = "Pythonバージョン"
    detected = sys.version.split()[0]
    if sys.version_info >= (3, 11):
        return passed("D01", name, f"Python {detected}（要求3.11以上）")
    return failed(
        "D01",
        name,
        "E-ENV-01",
        f"E-ENV-01 Python版が要件未満です: 検出{detected}、要求3.11以上。",
    )


def check_dependencies() -> dict[str, Any]:
    name = "依存パッケージ"
    issues = dependency_issues()
    if not issues:
        versions = ", ".join(
            f"{distribution} {required}"
            for distribution, (_module, required) in REQUIRED_PACKAGES.items()
        )
        return passed("D02", name, f"固定版を確認しました: {versions}")
    details = "; ".join(
        f"{issue['package']} 要求{issue['required']} 検出{issue['detected'] or '欠落'}"
        for issue in issues
    )
    return failed(
        "D02",
        name,
        "E-ENV-02",
        f"E-ENV-02 依存パッケージが欠落または版不一致です: {details}",
    )


def check_model() -> dict[str, Any]:
    name = "spaCyモデル"
    try:
        _model, version = load_spacy_model()
    except CliFailure as exc:
        return failed("D03", name, "E-ENV-03", exc.message)
    return passed("D03", name, f"{MODEL_NAME} {version}をロードしました")


def check_repository(repo_root: Path) -> dict[str, Any]:
    name = "リポジトリ構成"
    problems: list[str] = []
    for relative in ("schemas", "data/config", "agent", "scripts"):
        if not (repo_root / relative).is_dir():
            problems.append(relative)
    for schema_name in SCHEMA_FILES:
        path = repo_root / "schemas" / schema_name
        if not path.is_file():
            problems.append(f"schemas/{schema_name}")
            continue
        try:
            strict_json_loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            problems.append(f"schemas/{schema_name}（破損）")
    if problems:
        return failed(
            "D04",
            name,
            "E-ENV-04",
            f"E-ENV-04 リポジトリ構成が不完全です: {', '.join(problems)}",
        )
    return passed("D04", name, "必須ディレクトリとスキーマ9ファイルを確認しました")


def check_output(repo_root: Path) -> dict[str, Any]:
    name = "output書き込み"
    output_dir = repo_root / "output"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output_dir, prefix=".doctor-", delete=True) as stream:
            stream.write(b"doctor")
            stream.flush()
    except OSError as exc:
        return failed(
            "D05",
            name,
            "E-ENV-05",
            f"E-ENV-05 output/へ書き込めません: {output_dir} ({exc})",
        )
    return passed("D05", name, f"作成・書き込み可能です: {output_dir.relative_to(repo_root)}")


def check_sources(repo_root: Path) -> dict[str, Any]:
    name = "原本入力"
    try:
        sources = load_sources(repo_root / "data/source")
    except CliFailure as exc:
        return failed("D06", name, "E-DATA-01", exc.message)
    files = ", ".join(source["file"] for source in sources)
    return passed("D06", name, f"原本2件とsources.jsonを確認しました: {files}")


def check_source_checksums(repo_root: Path) -> dict[str, Any]:
    name = "原本チェックサム"
    source_dir = repo_root / "data/source"
    meta_path = repo_root / "data/normalized/meta.json"
    try:
        actual = source_checksums(source_dir)
    except CliFailure as exc:
        return failed("D07", name, exc.error_code, exc.message)
    if not meta_path.is_file():
        return failed(
            "D07",
            name,
            "E-DATA-03",
            f"E-DATA-03 正規化データが欠落しています: {meta_path.relative_to(repo_root)}",
        )
    try:
        meta = load_json_file(meta_path, "E-DATA-04")
        meta_problems = validate_meta_document(meta)
        if meta_problems:
            raise ValueError("; ".join(meta_problems))
        expected = {source["file"]: source["sha256"] for source in meta["sources"]}
    except CliFailure as exc:
        return failed("D07", name, exc.error_code, exc.message)
    except (KeyError, TypeError, ValueError) as exc:
        return failed(
            "D07",
            name,
            "E-DATA-04",
            f"E-DATA-04 meta.jsonから期待チェックサムを取得できません: {exc}",
        )
    mismatches = checksum_mismatches(expected, actual)
    if mismatches:
        details = "; ".join(
            f"{item['file']} 期待{item['expected']} 実測{item['actual']}" for item in mismatches
        )
        return failed(
            "D07",
            name,
            "E-DATA-02",
            f"E-DATA-02 原本チェックサムが一致しません: {details}",
        )
    return passed("D07", name, "原本2ファイルのSHA-256がmeta.jsonと一致しました")


def check_normalized_presence(repo_root: Path) -> dict[str, Any]:
    name = "正規化データ存在"
    normalized_dir = repo_root / "data/normalized"
    missing = [file_name for file_name in NORMALIZED_FILE_NAMES if not (normalized_dir / file_name).is_file()]
    if missing:
        return failed(
            "D08",
            name,
            "E-DATA-03",
            f"E-DATA-03 正規化データが欠落しています: {', '.join(missing)}",
        )
    return passed("D08", name, "lexicon.json・grammar.json・meta.jsonを確認しました")


def check_normalized_integrity(repo_root: Path) -> dict[str, Any]:
    name = "正規化データ整合"
    try:
        sources = load_sources(repo_root / "data/source")
        expected_source_versions = {
            source["role"]: source["version_label"] for source in sources
        }
        lexicon, grammar, meta = validate_normalized_set(
            repo_root,
            repo_root / "data/normalized",
            expected_data_version=source_data_version(sources),
            expected_pipeline_version=PIPELINE_VERSION,
            expected_source_versions=expected_source_versions,
        )
    except CliFailure as exc:
        return failed("D09", name, exc.error_code, exc.message)
    return passed(
        "D09",
        name,
        "スキーマ・現在の入力版・パイプライン版・data_version・件数を確認しました: "
        f"lexicon={len(lexicon['entries'])}, grammar={len(grammar['entries'])}, version={meta['data_version']}",
    )


def check_configs(repo_root: Path) -> dict[str, Any]:
    name = "設定ファイル"
    targets = (
        ("limits.json", "config_limits.schema.json"),
        ("proper_nouns.json", "config_proper_nouns.schema.json"),
    )
    problems: list[str] = []
    for file_name, schema_name in targets:
        path = repo_root / "data/config" / file_name
        if not path.is_file():
            problems.append(f"{file_name}: 欠落")
            continue
        try:
            value = load_json_file(path, "E-DATA-05")
            errors = schema_errors(value, repo_root / "schemas" / schema_name)
        except Exception as exc:
            problems.append(f"{file_name}: {exc}")
            continue
        if errors:
            rendered = ", ".join(
                f"{error['json_pointer'] or '/'} {error['message']}" for error in errors[:50]
            )
            problems.append(f"{file_name}: {rendered}")
        elif file_name == "limits.json" and value["generation_max"] > MAX_SCHEMA_GENERATION:
            problems.append(
                "limits.json: /generation_max "
                f"受取{value['generation_max']}、現行スキーマの運用許容範囲1..{MAX_SCHEMA_GENERATION}"
            )
    if problems:
        return failed(
            "D10",
            name,
            "E-DATA-05",
            f"E-DATA-05 設定ファイルが欠落・スキーマ不通過・運用上限不適合です: {'; '.join(problems)}",
        )
    return passed(
        "D10",
        name,
        "limits.jsonとproper_nouns.jsonが各スキーマおよび世代上限1..3に適合しました",
    )


def check_schemas(repo_root: Path) -> dict[str, Any]:
    name = "JSON Schema自己妥当性"
    problems: list[str] = []
    try:
        jsonschema = importlib.import_module("jsonschema")
        schema_error = importlib.import_module("jsonschema.exceptions").SchemaError
    except ImportError as exc:
        return failed(
            "D11",
            name,
            "E-ENV-04",
            f"E-ENV-04 JSON Schema検証器を読み込めません: {exc}",
        )
    for schema_name in SCHEMA_FILES:
        path = repo_root / "schemas" / schema_name
        try:
            schema = strict_json_loads(path.read_text(encoding="utf-8"))
            if not isinstance(schema, dict):
                raise ValueError("トップレベルがobjectではありません")
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                raise ValueError("$schemaがdraft 2020-12ではありません")
            jsonschema.Draft202012Validator.check_schema(schema)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            ValueError,
            TypeError,
            AttributeError,
            schema_error,
        ) as exc:
            problems.append(f"{schema_name}: {exc}")
    if problems:
        return failed(
            "D11",
            name,
            "E-ENV-04",
            f"E-ENV-04 スキーマが欠落・破損・自己不当です: {'; '.join(problems)}",
        )
    return passed("D11", name, "9スキーマがJSON Schema draft 2020-12として自己妥当です")


def check_reviewer_wiring(repo_root: Path) -> dict[str, Any]:
    name = "レビュアー配線"
    reviewer_definition = repo_root / ".claude/agents/cefrj-reviewer.md"
    codex_path = shutil.which("codex")
    if reviewer_definition.is_file() or codex_path:
        detected = (
            str(reviewer_definition.relative_to(repo_root))
            if reviewer_definition.is_file()
            else codex_path
        )
        return passed("D12", name, f"レビュアー配線を検出しました: {detected}")
    return failed(
        "D12",
        name,
        "E-ENV-06",
        "E-ENV-06 レビュアー配線を検出できません: "
        ".claude/agents/cefrj-reviewer.md、PATH上のcodex。",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = DoctorArgumentParser(description="環境・データ・配線を12項目で一括診断します。")
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    parse_args(argv)
    repo_root = Path.cwd()
    checks: list[dict[str, Any]] = []
    checks.append(check_python())
    checks.append(check_dependencies())
    checks.append(check_model())
    checks.append(check_repository(repo_root))
    checks.append(check_output(repo_root))
    checks.append(check_sources(repo_root))
    checks.append(check_source_checksums(repo_root))
    checks.append(check_normalized_presence(repo_root))
    checks.append(check_normalized_integrity(repo_root))
    checks.append(check_configs(repo_root))
    checks.append(check_schemas(repo_root))
    checks.append(check_reviewer_wiring(repo_root))
    failed_count = sum(1 for check in checks if check["status"] == "fail")
    report = {
        "checks": checks,
        "summary": {"fail": failed_count, "pass": len(checks) - failed_count},
    }
    emit_json(report)
    return 1 if failed_count else 0


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
