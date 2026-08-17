#!/usr/bin/env python3
"""9種類のJSON文書を統一契約で検証し、セット状態を識別する。"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import stat
import sys
import traceback
from functools import total_ordering
from pathlib import Path
from typing import Any

from build_normalized import (
    CliFailure,
    emit_json as emit_canonical_json,
    japanese_schema_message,
    json_pointer,
    leaf_schema_errors,
    require_basic_environment,
    selected_schema_branch,
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
SET_ID_PATTERN = re.compile(r"^[0-9]{8}-[0-9]{6}-[a-z0-9]{4}$")
SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
JSON_NUMBER_PATTERN = re.compile(
    r"(?P<sign>-?)(?P<integer>0|[1-9][0-9]*)"
    r"(?:\.(?P<fraction>[0-9]+))?"
    r"(?:[eE](?P<exponent>[+-]?[0-9]+))?"
)
NONSTANDARD_JSON_CONSTANTS = ("-Infinity", "Infinity", "NaN")
ECMA262_WHITESPACE_CLASS = (
    r"\u0009-\u000d\u0020\u00a0\u1680\u2000-\u200a"
    r"\u2028\u2029\u202f\u205f\u3000\ufeff"
)
LINE_BREAK_ESCAPES = {
    ord("\n"): "\\n",
    ord("\r"): "\\r",
    ord("\v"): "\\v",
    ord("\f"): "\\f",
    0x001C: "\\u001c",
    0x001D: "\\u001d",
    0x001E: "\\u001e",
    0x0085: "\\u0085",
    0x2028: "\\u2028",
    0x2029: "\\u2029",
}


@total_ordering
class ExactJsonNumber:
    """係数と任意精度の10進指数でJSON実数を正確に保持する。"""

    __slots__ = ("coefficient", "exponent", "sign", "token")

    def __init__(self, token: str) -> None:
        match = JSON_NUMBER_PATTERN.fullmatch(token)
        if match is None:
            raise ValueError(f"標準JSON数値ではありません: {token}")
        integer = match.group("integer")
        fraction = match.group("fraction") or ""
        coefficient = (integer + fraction).lstrip("0")
        self.token = token
        if not coefficient:
            self.sign = 0
            self.coefficient = "0"
            self.exponent = 0
            return
        self.sign = -1 if match.group("sign") else 1
        self.exponent = int(match.group("exponent") or "0") - len(fraction)
        normalized = coefficient.rstrip("0")
        self.exponent += len(coefficient) - len(normalized)
        self.coefficient = normalized

    @classmethod
    def from_integer(cls, value: int) -> ExactJsonNumber:
        instance = cls.__new__(cls)
        instance.token = str(value)
        if value == 0:
            instance.sign = 0
            instance.coefficient = "0"
            instance.exponent = 0
            return instance
        digits = str(abs(value))
        instance.sign = -1 if value < 0 else 1
        instance.coefficient = digits.rstrip("0")
        instance.exponent = len(digits) - len(instance.coefficient)
        return instance

    @staticmethod
    def coerce(value: Any) -> ExactJsonNumber | Any:
        if isinstance(value, ExactJsonNumber):
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            return ExactJsonNumber.from_integer(value)
        return NotImplemented

    def is_integer(self) -> bool:
        return self.sign == 0 or self.exponent >= 0

    def compare_magnitude(self, other: ExactJsonNumber) -> int:
        self_digits = len(self.coefficient) + self.exponent
        other_digits = len(other.coefficient) + other.exponent
        if self_digits != other_digits:
            return -1 if self_digits < other_digits else 1
        width = max(len(self.coefficient), len(other.coefficient))
        self_coefficient = self.coefficient.ljust(width, "0")
        other_coefficient = other.coefficient.ljust(width, "0")
        if self_coefficient == other_coefficient:
            return 0
        return -1 if self_coefficient < other_coefficient else 1

    def __eq__(self, other: Any) -> bool:
        coerced = self.coerce(other)
        if coerced is NotImplemented:
            return False
        return (
            self.sign == coerced.sign
            and self.coefficient == coerced.coefficient
            and self.exponent == coerced.exponent
        )

    def __lt__(self, other: Any) -> bool:
        coerced = self.coerce(other)
        if coerced is NotImplemented:
            return NotImplemented
        if self.sign != coerced.sign:
            return self.sign < coerced.sign
        if self.sign == 0:
            return False
        magnitude = self.compare_magnitude(coerced)
        return magnitude < 0 if self.sign > 0 else magnitude > 0

    def __repr__(self) -> str:
        return self.token

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


def emit_utf8_text(value: str, stream: Any = None) -> None:
    """テキストを環境エンコーディングに依存せずUTF-8で出力する。"""

    if stream is None:
        stream = sys.stdout
    payload = value.encode("utf-8")
    binary_stream = getattr(stream, "buffer", None)
    if binary_stream is not None:
        binary_stream.write(payload)
        return
    try:
        stream.write(payload)
    except TypeError:
        stream.write(value)


class ValidateArgumentParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        return (
            super()
            .format_help()
            .replace("usage:", "使用法:", 1)
            .replace("options:", "オプション:", 1)
            .replace("show this help message and exit", "このヘルプを表示して終了します", 1)
        )

    def print_help(self, file: Any = None) -> None:
        emit_utf8_text(self.format_help(), sys.stdout if file is None else file)

    def error(self, message: str) -> None:
        translated = translate_argument_error(message)
        raise CliFailure(
            "E-INPUT-01",
            f"E-INPUT-01 validate.pyの引数が不正です: {one_line(translated)}",
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


def one_line(value: Any) -> str:
    """エラー要約へ埋め込む動的値の行区切りを可視化する。"""

    return escape_unpaired_surrogates(str(value)).translate(LINE_BREAK_ESCAPES)


def escape_unpaired_surrogates(value: str) -> str:
    """UTF-8へ符号化できない孤立サロゲートを可視な表記へ変換する。"""

    return re.sub(
        r"[\ud800-\udfff]",
        lambda match: f"\\u{ord(match.group(0)):04x}",
        value,
    )


def utf8_safe_json(value: Any) -> Any:
    """JSON出力値を再帰し、外部文字列をUTF-8直列化可能にする。"""

    if isinstance(value, str):
        return escape_unpaired_surrogates(value)
    if isinstance(value, list):
        return [utf8_safe_json(item) for item in value]
    if isinstance(value, tuple):
        return tuple(utf8_safe_json(item) for item in value)
    if isinstance(value, dict):
        return {
            utf8_safe_json(key): utf8_safe_json(item) for key, item in value.items()
        }
    return value


def emit_json(value: Any, stream: Any = None) -> None:
    emit_canonical_json(utf8_safe_json(value), stream)


def ecma262_pattern_for_python(pattern: str) -> str:
    """現行スキーマが使うECMA-262文字クラスをPythonへ移植する。"""

    rendered: list[str] = []
    index = 0
    in_character_class = False
    while index < len(pattern):
        character = pattern[index]
        if character == "\\" and index + 1 < len(pattern):
            escaped = pattern[index + 1]
            if escaped == "d":
                rendered.append("0-9" if in_character_class else "[0-9]")
            elif escaped == "D" and not in_character_class:
                rendered.append("[^0-9]")
            elif escaped == "s":
                rendered.append(
                    ECMA262_WHITESPACE_CLASS
                    if in_character_class
                    else f"[{ECMA262_WHITESPACE_CLASS}]"
                )
            elif escaped == "S" and not in_character_class:
                rendered.append(f"[^{ECMA262_WHITESPACE_CLASS}]")
            elif escaped == "w":
                rendered.append("A-Za-z0-9_" if in_character_class else "[A-Za-z0-9_]")
            elif escaped == "W" and not in_character_class:
                rendered.append("[^A-Za-z0-9_]")
            else:
                rendered.extend((character, escaped))
            index += 2
            continue
        if character == "[":
            in_character_class = True
        elif character == "]" and in_character_class:
            in_character_class = False
        elif character == "$" and not in_character_class:
            rendered.append(r"\Z")
            index += 1
            continue
        rendered.append(character)
        index += 1
    return "".join(rendered)


def make_parser() -> ValidateArgumentParser:
    parser = ValidateArgumentParser(
        description="9種類のJSON文書を検証し、セットの完成・未完成状態を識別します。",
        allow_abbrev=False,
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
        f"E-INPUT-04 schemaが値域外です: 受取{one_line(repr(received))}、"
        f"許容{'|'.join(SCHEMA_NAMES)}。",
        detail={"allowed": list(SCHEMA_NAMES), "field": "schema", "received": received},
        remedy=REMEDIES["E-INPUT-04"],
    )


def decode_utf8(payload: bytes, source_name: str) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        prefix = payload[: exc.start].decode("utf-8")
        lines = re.split(r"\r\n|\r|\n", prefix)
        line = len(lines)
        column = len(lines[-1]) + 1
        raise CliFailure(
            "E-INPUT-03",
            f"E-INPUT-03 入力JSONがUTF-8ではありません: "
            f"{one_line(source_name)}（{line}行{column}列）。",
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
    """文字列外に現れる標準外数値定数を位置付きで拒否する。"""

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
                index = match.end()
                continue
        index += 1


def parse_json_text(text: str) -> Any:
    if hasattr(sys, "set_int_max_str_digits"):
        sys.set_int_max_str_digits(0)
    json.loads(
        text,
        parse_constant=lambda token: token,
        parse_float=lambda token: token,
        parse_int=lambda token: token,
    )
    validate_json_number_tokens(text)
    try:
        return json.loads(
            text,
            parse_constant=lambda token: reject_json_constant(token),
            parse_float=ExactJsonNumber,
        )
    except json.JSONDecodeError:
        raise
    except ValueError as exc:
        raise json.JSONDecodeError(str(exc), text, 0) from exc


def reject_json_constant(token: str) -> None:
    raise ValueError(f"標準JSONではない数値定数です: {token}")


def validate_strict_utf8_strings(document: Any, source_name: str) -> None:
    """全JSON string値・object keyがstrict UTF-8へ符号化可能か検証する。"""

    stack: list[tuple[str, str, Any]] = [("value", "$", document)]
    while stack:
        value_kind, location, value = stack.pop()
        if isinstance(value, str):
            try:
                value.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                code_point = f"U+{ord(value[exc.start]):04X}"
                raise CliFailure(
                    "E-INPUT-03",
                    "E-INPUT-03 入力JSONにstrict UTF-8で表現できない文字列が"
                    f"あります: {one_line(source_name)}（{location}、{code_point}）。",
                    detail={
                        "character_offset": exc.start,
                        "code_point": code_point,
                        "error": exc.reason,
                        "json_location": location,
                        "source": source_name,
                        "value_kind": value_kind,
                    },
                    remedy=REMEDIES["E-INPUT-03"],
                ) from exc
            continue
        if isinstance(value, list):
            for index in range(len(value) - 1, -1, -1):
                stack.append(("value", f"{location}[{index}]", value[index]))
            continue
        if isinstance(value, dict):
            items = list(value.items())
            for key, child in reversed(items):
                key_label = json.dumps(key, ensure_ascii=True)
                stack.append(("value", f"{location}[{key_label}]", child))
                stack.append(("object_key", f"{location}[key={key_label}]", key))


def parse_json_payload(payload: bytes | str, source_name: str) -> Any:
    text = payload if isinstance(payload, str) else decode_utf8(payload, source_name)
    try:
        document = parse_json_text(text)
    except json.JSONDecodeError as exc:
        raise CliFailure(
            "E-INPUT-03",
            f"E-INPUT-03 入力JSONをパースできません: "
            f"{one_line(source_name)}（{exc.lineno}行{exc.colno}列）。",
            detail={
                "column": exc.colno,
                "error": str(exc),
                "line": exc.lineno,
                "source": source_name,
            },
            remedy=REMEDIES["E-INPUT-03"],
        ) from exc
    except RecursionError as exc:
        raise CliFailure(
            "E-INPUT-03",
            f"E-INPUT-03 入力JSONのネストを解析できません: "
            f"{one_line(source_name)}（1行1列）。",
            detail={
                "column": 1,
                "error": str(exc),
                "line": 1,
                "source": source_name,
            },
            remedy=REMEDIES["E-INPUT-03"],
        ) from exc
    validate_strict_utf8_strings(document, source_name)
    return document


def read_json_document(path_text: str) -> Any:
    source_name = "stdin" if path_text == "-" else path_text
    if path_text == "-":
        try:
            input_stream = getattr(sys.stdin, "buffer", sys.stdin)
            payload = input_stream.read()
        except OSError as exc:
            raise CliFailure(
                "E-INPUT-02",
                f"E-INPUT-02 stdinを読み取れません: {one_line(exc)}",
                detail={"error": str(exc), "path": "stdin"},
                remedy=REMEDIES["E-INPUT-02"],
            ) from exc
        return parse_json_payload(payload, source_name)

    path = Path(path_text)
    try:
        file_status = path.stat()
        if not stat.S_ISREG(file_status.st_mode):
            raise CliFailure(
                "E-INPUT-02",
                f"E-INPUT-02 検証対象が通常ファイルではありません: {one_line(path)}",
                detail={"path": str(path)},
                remedy=REMEDIES["E-INPUT-02"],
            )
        payload = path.read_bytes()
    except CliFailure:
        raise
    except OSError as exc:
        raise CliFailure(
            "E-INPUT-02",
            "E-INPUT-02 検証対象ファイルが存在しないか読み取れません: "
            f"{one_line(path)}: {one_line(exc)}",
            detail={"error": str(exc), "path": str(path)},
            remedy=REMEDIES["E-INPUT-02"],
        ) from exc
    return parse_json_payload(payload, source_name)


def read_set_json_document(path: Path) -> Any | None:
    try:
        file_status = path.lstat()
        if not stat.S_ISREG(file_status.st_mode):
            raise CliFailure(
                "E-INPUT-02",
                f"E-INPUT-02 set.jsonが通常ファイルではありません: {one_line(path)}",
                detail={"path": str(path)},
                remedy=REMEDIES["E-INPUT-02"],
            )
        payload = path.read_bytes()
    except FileNotFoundError:
        return None
    except CliFailure:
        raise
    except OSError as exc:
        raise CliFailure(
            "E-INPUT-02",
            f"E-INPUT-02 set.jsonを読み取れません: {one_line(path)}: {one_line(exc)}",
            detail={"error": str(exc), "path": str(path)},
            remedy=REMEDIES["E-INPUT-02"],
        ) from exc
    return parse_json_payload(payload, str(path))


def load_schema(repo_root: Path, schema_name: str) -> tuple[dict[str, Any], str]:
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
            "E-ENV-04 スキーマファイルが欠落または破損しています: "
            f"{one_line(schema_path)}",
            detail={"error": str(exc), "path": str(schema_path)},
            remedy=REMEDIES["E-ENV-04"],
        ) from exc
    except Exception as exc:
        raise CliFailure(
            "E-ENV-04",
            f"E-ENV-04 スキーマを検証器へ読み込めません: {one_line(schema_path)}",
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
            f"E-ENV-04 スキーマ$idが規定書式ではありません: {one_line(schema_path)}: "
            f"{one_line(repr(schema_id))}",
            detail={"id": schema_id, "path": str(schema_path)},
            remedy=REMEDIES["E-ENV-04"],
        )
    return schema, version


def exact_schema_errors(
    instance: Any,
    schema: dict[str, Any],
) -> list[dict[str, str]]:
    jsonschema = importlib.import_module("jsonschema")
    base_validator = jsonschema.Draft202012Validator

    def is_exact_integer(checker: Any, value: Any) -> bool:
        if isinstance(value, ExactJsonNumber):
            return value.is_integer()
        return base_validator.TYPE_CHECKER.is_type(value, "integer")

    def is_exact_number(checker: Any, value: Any) -> bool:
        if isinstance(value, ExactJsonNumber):
            return True
        return base_validator.TYPE_CHECKER.is_type(value, "number")

    def validate_ecma262_pattern(
        validator: Any,
        pattern: str,
        value: Any,
        current_schema: dict[str, Any],
    ) -> Any:
        if validator.is_type(value, "string") and not re.search(
            ecma262_pattern_for_python(pattern), value
        ):
            yield jsonschema.ValidationError(
                f"{value!r} does not match {pattern!r}"
            )

    type_checker = base_validator.TYPE_CHECKER.redefine_many(
        {"integer": is_exact_integer, "number": is_exact_number}
    )
    validator_class = jsonschema.validators.extend(
        base_validator,
        validators={"pattern": validate_ecma262_pattern},
        type_checker=type_checker,
    )
    validator = validator_class(selected_schema_branch(instance, schema))
    root_errors = validator.iter_errors(instance)
    errors = [leaf for error in root_errors for leaf in leaf_schema_errors(error)]

    def rendered_message(error: Any) -> str:
        if error.validator == "type" and isinstance(error.instance, ExactJsonNumber):
            constraint = error.validator_value
            expected = constraint if isinstance(constraint, str) else "|".join(constraint)
            return f"型が不正です: 期待{expected}、実際number"
        if error.validator == "contains" and isinstance(error.schema, dict):
            contains = error.schema.get("contains", {})
            properties = contains.get("properties", {})
            check_id = properties.get("check_id", {}).get("const")
            if isinstance(check_id, str):
                return f"配列に必須チェック{check_id}がありません"
        return japanese_schema_message(error)

    def stable_path(path: Any) -> tuple[tuple[int, Any], ...]:
        return tuple(
            (0, part) if isinstance(part, int) else (1, str(part)) for part in path
        )

    rendered = [
        (
            json_pointer(error.absolute_path),
            stable_path(error.absolute_schema_path),
            rendered_message(error),
        )
        for error in errors
    ]
    return [
        {"json_pointer": pointer, "message": message}
        for pointer, _schema_path, message in sorted(rendered)
    ]


def validation_result(
    document: Any,
    schema_name: str,
    schema: dict[str, Any],
    schema_version: str,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    all_errors = exact_schema_errors(document, schema)
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
    rendered = one_line("; ".join(
        f"{error['json_pointer'] or '/'} {error['message']}" for error in errors[:50]
    ))
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
    schema, schema_version = load_schema(repo_root, schema_name)
    document = read_json_document(path_text)
    return validation_result(document, schema_name, schema, schema_version)


def inspect_set_directory(
    repo_root: Path,
    set_dir_text: str,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    set_dir = Path(set_dir_text)
    set_id = set_dir.name
    if not SET_ID_PATTERN.fullmatch(set_id):
        raise CliFailure(
            "E-INPUT-05",
            f"E-INPUT-05 set_idの書式が不正です: 受取{one_line(repr(set_id))}、"
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
            f"{one_line(set_dir)}: {one_line(exc)}",
            detail={"error": str(exc), "path": str(set_dir)},
            remedy=REMEDIES["E-INPUT-02"],
        ) from exc

    set_json = set_dir / "set.json"
    document = read_set_json_document(set_json)
    if document is None:
        return (
            {
                "set_dir": set_dir_text,
                "set_json_path": None,
                "status": "incomplete",
                "validation": None,
            },
            [],
        )
    schema, schema_version = load_schema(repo_root, "set")
    result, errors = validation_result(document, "set", schema, schema_version)
    return (
        {
            "set_dir": set_dir_text,
            "set_json_path": set_json.as_posix(),
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
