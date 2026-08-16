#!/usr/bin/env python3
"""正規化済みCEFR-J語彙・文法項目を決定的に照会する。"""

from __future__ import annotations

import argparse
import re
import sys
import traceback
import unicodedata
from pathlib import Path
from typing import Any

from build_normalized import (
    CEFRJ_RANK,
    PIPELINE_VERSION,
    POS_VALUES,
    CliFailure,
    checksum_mismatches,
    emit_json,
    load_json_file,
    load_sources,
    require_basic_environment,
    schema_errors,
    source_checksums,
    source_data_version,
    validate_normalized_set,
)


CEFR_VALUES = ("A1", "A2", "B1", "B2")
CEFRJ_VALUES = tuple(CEFRJ_RANK)
POS_VALUE_ORDER = (
    "noun",
    "verb",
    "adjective",
    "adverb",
    "pronoun",
    "preposition",
    "determiner",
    "conjunction",
    "number",
    "modal auxiliary",
    "be-verb",
    "interjection",
    "do-verb",
    "have-verb",
    "infinitive-to",
)
GP_ID_PATTERN = re.compile(r"^gp:[0-9]+(?:-[0-9]+)?$")
CONTEXT_REQUIRED_VALUES = {"前文が肯定平叙", "前文が否定平叙"}

REMEDIES = {
    "E-DATA-02": (
        "意図的な原本更新はsources.jsonのversion_labelを更新し、"
        "python scripts/build_normalized.py --diffで確認後、"
        "python scripts/build_normalized.py --accept-source-changeを実行してください。"
    ),
    "E-DATA-05": (
        "git checkoutで設定を復元し、M3以降はpython scripts/validate.pyで"
        "config_limitsまたはconfig_proper_nounsを検証してください。"
    ),
    "E-INPUT-01": "python scripts/lookup.py --help の日本語ヘルプを参照して引数を修正してください。",
    "E-INPUT-04": (
        "docs/architecture.md CLI-29〜CLI-30とschemas/の列挙定義に従って値を修正してください。"
    ),
}


class LookupArgumentParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        return (
            super()
            .format_help()
            .replace("usage:", "使用法:", 1)
            .replace("options:", "オプション:", 1)
            .replace("positional arguments:", "位置引数:", 1)
            .replace("show this help message and exit", "このヘルプを表示して終了します", 1)
        )

    def error(self, message: str) -> None:
        translated = translate_argument_error(message)
        raise CliFailure(
            "E-INPUT-01",
            f"E-INPUT-01 lookup.pyの引数が不正です: {translated}",
            detail={"parser_message": message},
            remedy=REMEDIES["E-INPUT-01"],
        )


def translate_argument_error(message: str) -> str:
    if message.startswith("unrecognized arguments:"):
        return f"未知の引数です:{message.removeprefix('unrecognized arguments:')}"
    if message.startswith("the following arguments are required:"):
        return f"必須引数が欠落しています:{message.removeprefix('the following arguments are required:')}"
    missing_value = re.fullmatch(r"argument (.+): expected one argument", message)
    if missing_value:
        return f"引数 {missing_value.group(1)} に値が必要です"
    invalid_choice = re.fullmatch(r"argument (.+): invalid choice: (.+) \(choose from (.+)\)", message)
    if invalid_choice:
        return (
            f"引数 {invalid_choice.group(1)} の値{invalid_choice.group(2)}が不正です。"
            f"許容値は{invalid_choice.group(3)}です"
        )
    return f"引数の書式が不正です: {message}"


def nfc_casefold(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def input_value_failure(field: str, value: Any, allowed: str) -> CliFailure:
    return CliFailure(
        "E-INPUT-04",
        f"E-INPUT-04 {field}が値域外です: 受取{value!r}、許容{allowed}。",
        detail={"allowed": allowed, "field": field, "received": value},
        remedy=REMEDIES["E-INPUT-04"],
    )


def validate_config(
    repo_root: Path,
    file_name: str,
    schema_name: str,
) -> dict[str, Any]:
    path = repo_root / "data/config" / file_name
    if not path.is_file():
        raise CliFailure(
            "E-DATA-05",
            f"E-DATA-05 設定ファイルが欠落しています: {path}",
            detail={"missing": [str(path)]},
            remedy=REMEDIES["E-DATA-05"],
        )
    document = load_json_file(path, "E-DATA-05")
    errors = schema_errors(document, repo_root / "schemas" / schema_name)
    if errors:
        rendered = "; ".join(
            f"{error['json_pointer'] or '/'} {error['message']}" for error in errors[:50]
        )
        if len(errors) > 50:
            rendered = f"先頭50件: {rendered}; 総数{len(errors)}件"
        raise CliFailure(
            "E-DATA-05",
            f"E-DATA-05 設定ファイルがスキーマに適合しません: {path}: {rendered}",
            detail={"errors": errors[:50], "path": str(path), "total_errors": len(errors)},
            remedy=REMEDIES["E-DATA-05"],
        )
    return document


def load_validated_resources(repo_root: Path) -> dict[str, Any]:
    """CLI-08【基本】【データ】を検証し、読み込み済みリソースを返す。"""

    require_basic_environment(repo_root)
    source_dir = repo_root / "data/source"
    sources = load_sources(source_dir)
    source_versions = {source["role"]: source["version_label"] for source in sources}
    expected_data_version = source_data_version(sources)
    lexicon, grammar, meta = validate_normalized_set(
        repo_root,
        repo_root / "data/normalized",
        expected_data_version=expected_data_version,
        expected_pipeline_version=PIPELINE_VERSION,
        expected_source_versions=source_versions,
    )

    expected_checksums = {source["file"]: source["sha256"] for source in meta["sources"]}
    actual_checksums = source_checksums(source_dir)
    mismatches = checksum_mismatches(expected_checksums, actual_checksums)
    if mismatches:
        detail_text = "; ".join(
            f"{item['file']} 期待{item['expected']} 実測{item['actual']}" for item in mismatches
        )
        raise CliFailure(
            "E-DATA-02",
            f"E-DATA-02 原本チェックサムが一致しません: {detail_text}",
            detail={"mismatches": mismatches},
            remedy=REMEDIES["E-DATA-02"],
        )

    limits = validate_config(repo_root, "limits.json", "config_limits.schema.json")
    proper_nouns = validate_config(
        repo_root, "proper_nouns.json", "config_proper_nouns.schema.json"
    )
    return {
        "grammar": grammar,
        "lexicon": lexicon,
        "limits": limits,
        "meta": meta,
        "proper_nouns": proper_nouns,
    }


def parse_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise input_value_failure("limit", value, "1..200の整数") from exc
    if not 1 <= limit <= 200:
        raise input_value_failure("limit", value, "1..200の整数")
    return limit


def lex_matches(args: argparse.Namespace, lexicon: dict[str, Any]) -> dict[str, Any]:
    limit = parse_limit(args.limit)
    if args.pos is not None and args.pos not in POS_VALUES:
        raise input_value_failure("pos", args.pos, "|".join(POS_VALUE_ORDER))
    if args.level is not None and args.level not in CEFR_VALUES:
        raise input_value_failure("level", args.level, "A1|A2|B1|B2")

    filters = (args.headword, args.pos, args.level, args.category)
    if args.pool_for is not None and any(value is not None for value in filters):
        raise CliFailure(
            "E-INPUT-01",
            "E-INPUT-01 --pool-forは--headword・--pos・--level・--categoryと併用できません。",
            detail={"conflicting_options": ["--pool-for", "--headword/--pos/--level/--category"]},
            remedy=REMEDIES["E-INPUT-01"],
        )

    entries = lexicon["entries"]
    if args.pool_for is not None:
        target = next((entry for entry in entries if entry["id"] == args.pool_for), None)
        if target is None:
            raise input_value_failure("pool-for", args.pool_for, "実在するlex:<headword>:<pos>")
        candidates = [
            entry
            for entry in entries
            if entry["id"] != target["id"]
            and entry["level"] == target["level"]
            and entry["pos"] == target["pos"]
        ]

        def category_priority(entry: dict[str, Any]) -> int:
            if target["core_inventory_1"] is not None and (
                entry["core_inventory_1"] == target["core_inventory_1"]
            ):
                return 0
            if target["threshold"] is not None and entry["threshold"] == target["threshold"]:
                return 1
            if target["core_inventory_2"] is not None and (
                entry["core_inventory_2"] == target["core_inventory_2"]
            ):
                return 2
            return 3

        ordered = sorted(enumerate(candidates), key=lambda pair: (category_priority(pair[1]), pair[0]))
        matches = [entry for _index, entry in ordered]
    else:
        matches = entries
        if args.headword is not None:
            headword_key = nfc_casefold(args.headword)
            directly_matched = [
                entry for entry in entries if nfc_casefold(entry["headword"]) == headword_key
            ]
            group_ids = {
                group_id for entry in directly_matched for group_id in entry["group_ids"]
            }
            expanded_ids = {
                member_id
                for group in lexicon["groups"]
                if group["group_id"] in group_ids
                for member_id in group["member_ids"]
            }
            direct_ids = {entry["id"] for entry in directly_matched}
            matches = [entry for entry in entries if entry["id"] in direct_ids | expanded_ids]
        if args.pos is not None:
            matches = [entry for entry in matches if entry["pos"] == args.pos]
        if args.level is not None:
            matches = [entry for entry in matches if entry["level"] == args.level]
        if args.category is not None:
            matches = [
                entry
                for entry in matches
                if args.category
                in (
                    entry["core_inventory_1"],
                    entry["core_inventory_2"],
                    entry["threshold"],
                )
            ]

    return {"matches": matches[:limit], "total": len(matches)}


def gp_matches(args: argparse.Namespace, grammar: dict[str, Any]) -> dict[str, Any]:
    limit = parse_limit(args.limit)
    if args.id is not None and not GP_ID_PATTERN.fullmatch(args.id):
        raise input_value_failure("id", args.id, "gp:<数字>またはgp:<数字>-<数字>")
    if args.level is not None and args.level not in CEFRJ_RANK:
        raise input_value_failure("level", args.level, "|".join(CEFRJ_VALUES))

    matches = grammar["entries"]
    if args.id is not None:
        matches = [entry for entry in matches if entry["id"] == args.id]
    if args.level is not None:
        requested_rank = CEFRJ_RANK[args.level]
        matches = [
            entry
            for entry in matches
            if entry["target_eligible"]
            and entry["level"]["min"] is not None
            and CEFRJ_RANK[entry["level"]["min"]]
            <= requested_rank
            <= CEFRJ_RANK[entry["level"]["max"]]
        ]
    if args.keyword is not None:
        keyword = nfc_casefold(args.keyword)
        matches = [
            entry
            for entry in matches
            if keyword in nfc_casefold(entry["item_list"]["name_ja"])
            or (
                entry["kyoinban"]["name_simple_ja"] is not None
                and keyword in nfc_casefold(entry["kyoinban"]["name_simple_ja"])
            )
        ]
    if args.exclude_context_required:
        matches = [
            entry
            for entry in matches
            if entry["item_list"]["sentence_type_ja"] not in CONTEXT_REQUIRED_VALUES
        ]
    return {"matches": matches[:limit], "total": len(matches)}


def make_parser() -> LookupArgumentParser:
    parser = LookupArgumentParser(description="CEFR-J正規化データを照会します。")
    subparsers = parser.add_subparsers(dest="command", parser_class=LookupArgumentParser)

    lex = subparsers.add_parser("lex", help="語彙エントリを照会します。")
    lex.add_argument("--headword", help="見出し語を大文字小文字無視で完全一致します。")
    lex.add_argument("--pos", help="Wordlist品詞15種で絞り込みます。")
    lex.add_argument("--level", help="CEFR帯（A1〜B2）で絞り込みます。")
    lex.add_argument("--category", help="意味分野カテゴリ値で絞り込みます。")
    lex.add_argument("--pool-for", help="指定lex ID向け誤答候補プールを返します。")
    lex.add_argument("--limit", default="20", help="返却上限（1〜200、既定20）。")

    gp = subparsers.add_parser("gp", help="文法項目を照会します。")
    gp.add_argument("--id", help="文法項目ID（gp:<ID>）で完全一致します。")
    gp.add_argument("--level", help="CEFR-Jレベル9種の範囲包含で絞り込みます。")
    gp.add_argument("--keyword", help="文法項目名をNFC・casefold部分一致します。")
    gp.add_argument(
        "--exclude-context-required",
        action="store_true",
        help="先行文脈を要求する文タイプを除外します。",
    )
    gp.add_argument("--limit", default="20", help="返却上限（1〜200、既定20）。")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = make_parser().parse_args(argv)
        if args.command is None:
            raise CliFailure(
                "E-INPUT-01",
                "E-INPUT-01 lookup.pyの必須サブコマンドが欠落しています: lexまたはgpを指定してください。",
                detail={"required": ["lex", "gp"]},
                remedy=REMEDIES["E-INPUT-01"],
            )
        resources = load_validated_resources(Path.cwd())
        if args.command == "lex":
            result = lex_matches(args, resources["lexicon"])
        else:
            result = gp_matches(args, resources["grammar"])
        emit_json(result)
        return 0
    except CliFailure as exc:
        emit_json(exc.as_dict(), sys.stderr)
        return 1
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
