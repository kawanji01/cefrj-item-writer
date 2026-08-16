#!/usr/bin/env python3
"""9種類のJSON文書を統一契約で検証し、セット状態を識別する。"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Any

from build_normalized import (
    CliFailure,
    emit_json,
    require_basic_environment,
    schema_errors,
    strict_json_loads,
)


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
SET_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[a-z0-9]{4}$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
JSON_NUMBER_PATTERN = re.compile(
    r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
)
NONSTANDARD_JSON_CONSTANTS = ("-Infinity", "Infinity", "NaN")

REMEDIES = {
    "E-ENV-04": (
        "リポジトリルートに移動して再実行してください。スキーマ欠落・破損時は"
        "git statusで確認し、git checkoutで復元してください。"
    ),
    "E-INPUT-01": (
        "python scripts/validate.py --help の日本語ヘルプを参照して引数を修正してください。"
    ),
    "E-INPUT-02": "指定パスの綴り・存在・読み取り権限を確認してください。",
    "E-INPUT-03": (
        "入力をUTF-8の標準JSONに修正してください。エージェント生成入力の場合は"
        "生成をやり直してください。"
    ),
    "E-INPUT-04": (
        "docs/architecture.md CLI-26のスキーマ識別子一覧に従って値を修正してください。"
    ),
    "E-INPUT-05": (
        "set_idを書式例20260816-142530-k7x2に一致させたディレクトリを指定してください。"
    ),
}


class ValidateArgumentParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        return (
            super()
            .format_help()
            .replace("usage:", "使用法:", 1)
            .replace("options:", "オプション:", 1)
            .replace("show this help message and exit", "このヘルプを表示して終了します", 1)
        )

    def error(self, message: str) -> None:
        translated = translate_argument_error(message)
        raise CliFailure(
            "E-INPUT-01",
            f"E-INPUT-01 validate.pyの引数が不正です: {translated}",
            detail={"parser_message": message},
            remedy=REMEDIES["E-INPUT-01"],
        )


def translate_argument_error(message: str) -> str:
    unknown_prefix = "unrecognized arguments:"
    if message.startswith(unknown_prefix):
        return f"未知の引数です:{message[len(unknown_prefix):]}"
    missing_value = re.fullmatch(r"argument (.+): expected one argument", message)
    if missing_value:
        return f"引数 {missing_value.group(1)} に値が必要です"
    return f"引数の書式が不正です: {message}"


def make_parser() -> ValidateArgumentParser:
    parser = ValidateArgumentParser(
        description="9種類のJSON文書を検証し、セットの完成・未完成状態を識別します。"
    )
    parser.add_argument("--schema", help="スキーマ識別子。--fileと組で指定します。")
    parser.add_argument("--file", help="検証対象JSONのパス。-はstdin。")
    parser.add_argument(
        "--set-dir",
        help="セット状態を確認するディレクトリ。--schema/--fileとは排他的です。",
    )
    return parser


def validate_mode_arguments(args: argparse.Namespace) -> None:
    normal_values = (args.schema, args.file)
    if args.set_dir is not None:
        if any(value is not None for value in normal_values):
            raise CliFailure(
                "E-INPUT-01",
                "E-INPUT-01 --set-dirは--schema・--fileと併用できません。"
                "正しい書式はpython scripts/validate.py --set-dir <path>です。",
                detail={
                    "conflicting_options": [
                        option
                        for option, value in (
                            ("--schema", args.schema),
                            ("--file", args.file),
                        )
                        if value is not None
                    ]
                    + ["--set-dir"]
                },
                remedy=REMEDIES["E-INPUT-01"],
            )
        return
    if args.schema is None or args.file is None:
        missing = [
            option
            for option, value in (("--schema", args.schema), ("--file", args.file))
            if value is None
        ]
        raise CliFailure(
            "E-INPUT-01",
            "E-INPUT-01 validate.pyの必須引数が欠落しています: "
            f"{', '.join(missing)}。正しい書式はpython scripts/validate.py "
            "--schema <識別子> --file <path|->です。",
            detail={"missing_options": missing},
            remedy=REMEDIES["E-INPUT-01"],
        )


def unknown_schema_failure(received: str) -> CliFailure:
    return CliFailure(
        "E-INPUT-04",
        f"E-INPUT-04 schemaが値域外です: 受取{received!r}、許容{'|'.join(SCHEMA_NAMES)}。",
        detail={"allowed": list(SCHEMA_NAMES), "field": "schema", "received": received},
        remedy=REMEDIES["E-INPUT-04"],
    )


def decode_utf8(payload: bytes, source_name: str) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        prefix = payload[: exc.start]
        line = prefix.count(b"\n") + 1
        line_start = prefix.rfind(b"\n") + 1
        column = exc.start - line_start + 1
        raise CliFailure(
            "E-INPUT-03",
            f"E-INPUT-03 入力JSONがUTF-8ではありません: "
            f"{source_name}（{line}行{column}列）。",
            detail={
                "column": column,
                "encoding": "utf-8",
                "error": str(exc),
                "line": line,
                "source": source_name,
            },
            remedy=REMEDIES["E-INPUT-03"],
        ) from exc


def validate_json_number_tokens(text: str) -> None:
    """標準外定数と有限floatに変換できない数値を位置付きで拒否する。"""

    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        character = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            index += 1
            continue

        constant = next(
            (value for value in NONSTANDARD_JSON_CONSTANTS if text.startswith(value, index)),
            None,
        )
        if constant is not None:
            raise json.JSONDecodeError(
                f"標準JSONではない数値定数です: {constant}", text, index
            )

        if character == "-" or character.isdigit():
            match = JSON_NUMBER_PATTERN.match(text, index)
            if match is not None:
                token = match.group(0)
                if "." in token or "e" in token.lower():
                    value = float(token)
                    if not math.isfinite(value):
                        raise json.JSONDecodeError(
                            "有限値として表現できないJSON数値です", text, index
                        )
                index = match.end()
                continue
        index += 1


def parse_json_text(text: str) -> Any:
    json.loads(
        text,
        parse_constant=lambda token: token,
        parse_float=lambda token: token,
        parse_int=lambda token: token,
    )
    validate_json_number_tokens(text)
    if hasattr(sys, "set_int_max_str_digits"):
        sys.set_int_max_str_digits(0)
    try:
        return strict_json_loads(text)
    except json.JSONDecodeError:
        raise
    except ValueError as exc:
        raise json.JSONDecodeError(str(exc), text, 0) from exc


def read_json_document(path_text: str) -> Any:
    source_name = "stdin" if path_text == "-" else path_text
    if path_text == "-":
        try:
            input_stream = getattr(sys.stdin, "buffer", sys.stdin)
            payload = input_stream.read()
        except OSError as exc:
            raise CliFailure(
                "E-INPUT-02",
                f"E-INPUT-02 stdinを読み取れません: {exc}",
                detail={"error": str(exc), "path": "stdin"},
                remedy=REMEDIES["E-INPUT-02"],
            ) from exc
        text = payload if isinstance(payload, str) else decode_utf8(payload, source_name)
    else:
        path = Path(path_text)
        if not path.is_file():
            raise CliFailure(
                "E-INPUT-02",
                f"E-INPUT-02 検証対象ファイルが存在しないか読み取れません: {path}",
                detail={"path": str(path)},
                remedy=REMEDIES["E-INPUT-02"],
            )
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise CliFailure(
                "E-INPUT-02",
                f"E-INPUT-02 検証対象ファイルを読み取れません: {path}: {exc}",
                detail={"error": str(exc), "path": str(path)},
                remedy=REMEDIES["E-INPUT-02"],
            ) from exc
        text = decode_utf8(payload, source_name)
    try:
        return parse_json_text(text)
    except json.JSONDecodeError as exc:
        raise CliFailure(
            "E-INPUT-03",
            f"E-INPUT-03 入力JSONをパースできません: "
            f"{source_name}（{exc.lineno}行{exc.colno}列）。",
            detail={
                "column": exc.colno,
                "error": str(exc),
                "line": exc.lineno,
                "source": source_name,
            },
            remedy=REMEDIES["E-INPUT-03"],
        ) from exc


def load_schema(repo_root: Path, schema_name: str) -> tuple[Path, str]:
    schema_path = repo_root / "schemas" / f"{schema_name}.schema.json"
    try:
        schema = parse_json_text(decode_utf8(schema_path.read_bytes(), str(schema_path)))
        jsonschema = importlib.import_module("jsonschema")
        jsonschema.Draft202012Validator.check_schema(schema)
    except CliFailure:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise CliFailure(
            "E-ENV-04",
            f"E-ENV-04 スキーマファイルが欠落または破損しています: {schema_path}",
            detail={"error": str(exc), "path": str(schema_path)},
            remedy=REMEDIES["E-ENV-04"],
        ) from exc
    except Exception as exc:
        raise CliFailure(
            "E-ENV-04",
            f"E-ENV-04 スキーマを検証器へ読み込めません: {schema_path}",
            detail={"error": str(exc), "path": str(schema_path)},
            remedy=REMEDIES["E-ENV-04"],
        ) from exc

    expected_prefix = f"https://cefr-j-agents.local/schemas/{schema_name}/"
    schema_id = schema.get("$id") if isinstance(schema, dict) else None
    version = (
        schema_id.removeprefix(expected_prefix)
        if isinstance(schema_id, str) and schema_id.startswith(expected_prefix)
        else ""
    )
    if not SEMVER_PATTERN.fullmatch(version):
        raise CliFailure(
            "E-ENV-04",
            f"E-ENV-04 スキーマ$idが規定書式ではありません: {schema_path}: {schema_id!r}",
            detail={"id": schema_id, "path": str(schema_path)},
            remedy=REMEDIES["E-ENV-04"],
        )
    return schema_path, version


def validation_result(
    document: Any,
    schema_name: str,
    schema_path: Path,
    schema_version: str,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    all_errors = schema_errors(document, schema_path)
    result = {
        "errors": all_errors[:50],
        "schema": schema_name,
        "schema_version": schema_version,
        "valid": not all_errors,
    }
    return result, all_errors


def contract_remedy(schema_name: str) -> str:
    if schema_name == "candidate":
        return "candidateを同一世代内で1回再生成し、再度スキーマ検証してください。"
    if schema_name == "review_result":
        return (
            "レビュー結果をインフラ障害として再実行してください。2回再実行しても"
            "不通過の場合はセットを中止してください。"
        )
    if schema_name == "review_request":
        return (
            "セットを中止し、オーケストレータのreview_request組み立て不具合として"
            "報告してください。"
        )
    if schema_name in {"set", "machine_report"}:
        return f"{schema_name}を生成した実装の内部バグとして報告してください。"
    if schema_name.startswith("config_"):
        return (
            "git checkoutで設定ファイルを復元し、同じvalidate.pyコマンドで再検証してください。"
        )
    return (
        "python scripts/build_normalized.pyで正規化データを再ビルドしてください。"
        "同じ違反が再発する場合は正規化パイプラインの不具合として報告してください。"
    )


def contract_failure(
    schema_name: str,
    schema_version: str,
    errors: list[dict[str, str]],
) -> CliFailure:
    rendered = "; ".join(
        f"{error['json_pointer'] or '/'} {error['message']}" for error in errors[:50]
    )
    if len(errors) > 50:
        rendered = f"先頭50件: {rendered}; 総数{len(errors)}件"
    return CliFailure(
        "E-CONTRACT-01",
        f"E-CONTRACT-01 {schema_name}がスキーマ{schema_version}に適合しません: "
        f"{rendered}",
        detail={
            "errors": errors[:50],
            "schema": schema_name,
            "schema_version": schema_version,
            "total_errors": len(errors),
        },
        remedy=contract_remedy(schema_name),
    )


def validate_document(
    repo_root: Path,
    schema_name: str,
    path_text: str,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if schema_name not in SCHEMA_NAMES:
        raise unknown_schema_failure(schema_name)
    schema_path, schema_version = load_schema(repo_root, schema_name)
    document = read_json_document(path_text)
    return validation_result(document, schema_name, schema_path, schema_version)


def inspect_set_directory(
    repo_root: Path,
    set_dir_text: str,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    set_dir = Path(set_dir_text)
    set_id = set_dir.name
    if not SET_ID_PATTERN.fullmatch(set_id):
        raise CliFailure(
            "E-INPUT-05",
            f"E-INPUT-05 set_idの書式が不正です: 受取{set_id!r}、"
            "要求^\\d{8}-\\d{6}-[a-z0-9]{4}$。",
            detail={"pattern": r"^\d{8}-\d{6}-[a-z0-9]{4}$", "received": set_id},
            remedy=REMEDIES["E-INPUT-05"],
        )
    try:
        if not set_dir.is_dir():
            raise OSError("ディレクトリが存在しないか読み取れません")
        with os.scandir(set_dir):
            pass
    except OSError as exc:
        raise CliFailure(
            "E-INPUT-02",
            f"E-INPUT-02 セットディレクトリが存在しないか読み取れません: "
            f"{set_dir}: {exc}",
            detail={"error": str(exc), "path": str(set_dir)},
            remedy=REMEDIES["E-INPUT-02"],
        ) from exc

    set_json = set_dir / "set.json"
    if not set_json.exists() and not set_json.is_symlink():
        return (
            {
                "set_dir": set_dir_text,
                "set_json_path": None,
                "status": "incomplete",
                "validation": None,
            },
            [],
        )
    if set_json.is_symlink() or not set_json.is_file():
        raise CliFailure(
            "E-INPUT-02",
            f"E-INPUT-02 set.jsonが通常ファイルではないか読み取れません: {set_json}",
            detail={"path": str(set_json)},
            remedy=REMEDIES["E-INPUT-02"],
        )
    result, errors = validate_document(repo_root, "set", str(set_json))
    return (
        {
            "set_dir": set_dir_text,
            "set_json_path": str(set_json),
            "status": "complete",
            "validation": result,
        },
        errors,
    )


def run(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    validate_mode_arguments(args)
    repo_root = Path.cwd()
    require_basic_environment(repo_root)

    if args.set_dir is not None:
        output, errors = inspect_set_directory(repo_root, args.set_dir)
        emit_json(output)
        if errors:
            validation = output["validation"]
            raise contract_failure("set", validation["schema_version"], errors)
        return 0

    result, errors = validate_document(repo_root, args.schema, args.file)
    emit_json(result)
    if errors:
        raise contract_failure(args.schema, result["schema_version"], errors)
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except CliFailure as exc:
        emit_json(exc.as_dict(), sys.stderr)
        return 1
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
