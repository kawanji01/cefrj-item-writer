#!/usr/bin/env python3
"""監査ファイルからセット横断の決定的検査を実行する。"""

from __future__ import annotations

import argparse
import re
import sys
import traceback
from pathlib import Path
from typing import Any

from build_normalized import CliFailure, emit_json, schema_errors
from lookup import load_validated_resources
from set_support import (
    QUESTION_ID_PATTERN,
    build_set_report,
    contract_failure,
    load_audit_state,
    schema_version,
    select_attempts_for_check,
)


REMEDIES = {
    "E-INPUT-01": "python scripts/set_check.py --help の日本語ヘルプを参照して引数を修正してください。",
    "E-INPUT-04": "question_idをq01〜q20の書式で指定してください。",
}


def emit_utf8_text(value: str, stream: Any = None) -> None:
    if stream is None:
        stream = sys.stdout
    payload = value.encode("utf-8")
    binary = getattr(stream, "buffer", None)
    if binary is not None:
        binary.write(payload)
    else:
        try:
            stream.write(payload)
        except TypeError:
            stream.write(value)


def translate_argument_error(message: str) -> str:
    unknown = "unrecognized arguments:"
    required = "the following arguments are required:"
    if message.startswith(unknown):
        return f"未知の引数です:{message[len(unknown):]}"
    if message.startswith(required):
        return f"必須引数が欠落しています:{message[len(required):]}"
    missing = re.fullmatch(r"argument (.+): expected one argument", message)
    if missing:
        return f"引数 {missing.group(1)} に値が必要です"
    return f"引数の書式が不正です: {message}"


class SetCheckArgumentParser(argparse.ArgumentParser):
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
        raise CliFailure(
            "E-INPUT-01",
            f"E-INPUT-01 set_check.pyの引数が不正です: {translate_argument_error(message)}",
            detail={"parser_message": message},
            remedy=REMEDIES["E-INPUT-01"],
        )


def make_parser() -> SetCheckArgumentParser:
    parser = SetCheckArgumentParser(description="セット内の対象・例文・誤答再利用を横断検査します。")
    parser.add_argument("--set-dir", required=True, help="output/<set_id> ディレクトリ。")
    parser.add_argument(
        "--target",
        help="増分検査するquestion_id（q01〜q20）。省略時は全体最終検査。",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    if args.target is not None and QUESTION_ID_PATTERN.fullmatch(args.target) is None:
        raise CliFailure(
            "E-INPUT-04",
            f"E-INPUT-04 --targetが値域外です: 受取{args.target!r}、許容q01〜q20。",
            detail={"field": "target", "received": args.target},
            remedy=REMEDIES["E-INPUT-04"],
        )

    repo_root = Path.cwd()
    resources = load_validated_resources(repo_root)
    set_dir = Path(args.set_dir)
    state = load_audit_state(
        repo_root,
        set_dir,
        resources["meta"]["data_version"],
        resources["limits"]["generation_max"],
        resources["limits"],
        resources["proper_nouns"]["words"],
    )
    selected = select_attempts_for_check(state, args.target)
    report_version = schema_version(repo_root, "machine_report.schema.json")
    report = build_set_report(
        selected,
        state["set_id"],
        resources["meta"]["data_version"],
        report_version,
        resources["limits"]["distractor_reuse_max"],
        args.target,
    )
    errors = schema_errors(report, repo_root / "schemas/machine_report.schema.json")
    if errors:
        raise contract_failure(
            "E-CONTRACT-01",
            [f"{error['json_pointer'] or '/'} {error['message']}" for error in errors],
            {"errors": errors, "schema": "machine_report", "schema_version": report_version},
        )
    emit_json(report)
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
