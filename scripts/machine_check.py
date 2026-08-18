#!/usr/bin/env python3
"""候補問題1問をCEFR-J仕様に従って決定的に機械検査する。"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_normalized import (
    CEFRJ_RANK,
    MODEL_NAME,
    CliFailure,
    emit_json,
    load_spacy_model,
    schema_errors,
    strict_json_loads,
)
from lookup import CONTEXT_REQUIRED_VALUES, load_validated_resources, translate_argument_error


SET_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[a-z0-9]{4}$")
NUMERIC_PATTERNS = (
    re.compile(r"^[0-9]+(?:[.,:][0-9]+)*$"),
    re.compile(r"^[0-9]+(?:st|nd|rd|th)$", re.IGNORECASE),
)
JAPANESE_PATTERN = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]")
SYMBOL_ONLY_PATTERN = re.compile(r"^[^\w]+$", re.UNICODE)
JSON_NUMBER_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
NONSTANDARD_JSON_CONSTANTS = ("-Infinity", "Infinity", "NaN")
GENERATION_VALUES = ("gen1", "gen2", "gen3")
JSON_INTEGER_MAX_DIGITS = 4300
QUESTION_ID_MAX = 20
FORMAT_VALUES = (
    "vocab_mcq_en2ja",
    "vocab_mcq_ja2en",
    "vocab_flashcard_en2ja",
    "vocab_flashcard_ja2en",
    "grammar_mcq",
    "grammar_cloze",
    "grammar_reorder",
    "grammar_rewrite",
    "grammar_example_selfcheck",
)
MACHINE_REPORT_SCHEMA_VERSION = "1.1.0"
VOCAB_FORMATS = {
    "vocab_mcq_en2ja",
    "vocab_mcq_ja2en",
    "vocab_flashcard_en2ja",
    "vocab_flashcard_ja2en",
}
CHOICE_FORMATS = {"vocab_mcq_en2ja", "vocab_mcq_ja2en", "grammar_mcq"}
CONTEXT_FORMATS = {"grammar_mcq", "grammar_cloze", "grammar_example_selfcheck"}
CEFR_RANK = {"A1": 1, "A2": 2, "B1": 3, "B2": 4}
LEMMA_CORRECTIONS = {"gon": "go", "na": "to", "ca": "can", "wo": "will", "sha": "shall"}
POS_CANDIDATES = {
    "NN": ("noun",),
    "NNS": ("noun",),
    "NNP": ("noun",),
    "NNPS": ("noun",),
    "JJ": ("adjective",),
    "JJR": ("adjective",),
    "JJS": ("adjective",),
    "VB": ("verb",),
    "VBP": ("verb",),
    "VBZ": ("verb",),
    "VBD": ("verb",),
    "VBN": ("verb",),
    "VBG": ("verb",),
    "MD": ("modal auxiliary",),
    "RB": ("adverb",),
    "RBR": ("adverb",),
    "RBS": ("adverb",),
    "WRB": ("adverb",),
    "PRP": ("pronoun",),
    "PRP$": ("pronoun",),
    "WP": ("pronoun",),
    "WP$": ("pronoun",),
    "DT": ("determiner", "pronoun"),
    "PDT": ("determiner", "pronoun"),
    "WDT": ("determiner", "pronoun"),
    "IN": ("preposition", "conjunction"),
    "CC": ("conjunction",),
    "CD": ("number",),
    "UH": ("interjection",),
    "EX": ("adverb", "pronoun"),
    "RP": ("adverb", "preposition"),
}
COMPATIBLE_POS_GROUPS = (
    {"noun", "number"},
    {"verb", "be-verb", "do-verb", "have-verb", "modal auxiliary"},
    {"adjective", "determiner"},
    {"adverb"},
    {"pronoun", "preposition", "conjunction", "interjection", "infinitive-to"},
)

REMEDIES = {
    "E-CONTRACT-01": (
        "candidateの場合は同一世代内の再指示を1回行ってください。machine_reportの場合は"
        "内部バグとして報告してください。"
    ),
    "E-INPUT-01": "python scripts/machine_check.py --help の日本語ヘルプを参照して引数を修正してください。",
    "E-INPUT-02": "指定パスの綴り・存在・読み取り権限を確認してください。",
    "E-INPUT-03": "入力をUTF-8の標準JSONに修正してください。エージェント生成入力の場合は生成をやり直してください。",
    "E-INPUT-04": "docs/architecture.md CLI-16の値域に従って入力値を修正してください。",
    "E-INPUT-05": "set_idを書式例20260816-142530-k7x2に一致させてください。",
}


@dataclass(frozen=True)
class TextTarget:
    field: str
    text: str
    sentence_checks: bool
    target_occurrence: bool = False
    declared_anchor: dict[str, Any] | None = None


class JsonIntegerTooLong(json.JSONDecodeError):
    def __init__(self, document: str, position: int, digit_count: int) -> None:
        super().__init__(
            f"JSON整数が上限{JSON_INTEGER_MAX_DIGITS}桁を超えています（実測{digit_count}桁）",
            document,
            position,
        )
        self.digit_count = digit_count
        self.digit_limit = JSON_INTEGER_MAX_DIGITS


class MachineArgumentParser(argparse.ArgumentParser):
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
            f"E-INPUT-01 machine_check.pyの引数が不正です: {translated}",
            detail={"parser_message": message},
            remedy=REMEDIES["E-INPUT-01"],
        )


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def lookup_key(value: str) -> str:
    return nfc(value).lower()


def normalized_comparison(value: str) -> str:
    return " ".join(nfc(value).strip().lower().split())


def answer_equivalent_key(value: str) -> str:
    return value.strip().lower()


def english_choice_key(value: str) -> str:
    return value.strip().lower()


def japanese_choice_key(value: str) -> str:
    return nfc(value.strip())


def lexical_pos_from_ref(target_ref: str) -> str:
    pos_slug = target_ref.rsplit(":", 1)[1]
    return "modal auxiliary" if pos_slug == "modal-auxiliary" else pos_slug


def validate_json_number_tokens(text: str) -> None:
    """標準外定数とPythonで表現不能なJSON数値を位置付きで拒否する。"""

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
                try:
                    if "." in token or "e" in token.lower():
                        value = float(token)
                        if value == float("inf") or value == float("-inf"):
                            raise ValueError("finite float required")
                    else:
                        digit_count = len(token.lstrip("-"))
                        if digit_count > JSON_INTEGER_MAX_DIGITS:
                            raise JsonIntegerTooLong(text, index, digit_count)
                        int(token)
                except json.JSONDecodeError:
                    raise
                except ValueError as exc:
                    raise json.JSONDecodeError(
                        f"有限値として表現できないJSON数値です: {token}", text, index
                    ) from exc
                index = match.end()
                continue
        index += 1


def strict_candidate_json_loads(text: str) -> Any:
    set_int_limit = getattr(sys, "set_int_max_str_digits", None)
    if set_int_limit is not None:
        set_int_limit(JSON_INTEGER_MAX_DIGITS)
    json.loads(
        text,
        parse_constant=lambda token: token,
        parse_float=lambda token: token,
        parse_int=lambda token: token,
    )
    validate_json_number_tokens(text)
    try:
        return strict_json_loads(text)
    except json.JSONDecodeError:
        raise
    except ValueError as exc:
        raise json.JSONDecodeError(str(exc), text, 0) from exc


def make_parser() -> MachineArgumentParser:
    parser = MachineArgumentParser(description="候補問題1問を決定的に機械検査します。")
    parser.add_argument("--candidate", required=True, help="candidate JSONのパス。-はstdin。")
    parser.add_argument("--set-id", required=True, help="セットID。")
    parser.add_argument("--generation", required=True, help="候補世代（gen1〜gen3）。")
    parser.add_argument("--expected-format", required=True, help="セットの確定済み形式コード。")
    parser.add_argument("--expected-level", required=True, help="セットの確定済みレベル値。")
    parser.add_argument("--requested-count", required=True, help="セットの依頼問題数。")
    return parser


def validate_identifiers(set_id: str, generation: str) -> None:
    if not SET_ID_PATTERN.fullmatch(set_id):
        raise CliFailure(
            "E-INPUT-05",
            f"E-INPUT-05 set_idの書式が不正です: 受取{set_id!r}、要求^\\d{{8}}-\\d{{6}}-[a-z0-9]{{4}}$。",
            detail={"pattern": r"^\d{8}-\d{6}-[a-z0-9]{4}$", "received": set_id},
            remedy=REMEDIES["E-INPUT-05"],
        )
    if generation not in GENERATION_VALUES:
        raise CliFailure(
            "E-INPUT-04",
            f"E-INPUT-04 generationが値域外です: 受取{generation!r}、許容gen1|gen2|gen3。",
            detail={"allowed": list(GENERATION_VALUES), "field": "generation", "received": generation},
            remedy=REMEDIES["E-INPUT-04"],
        )


def invalid_input_value(field: str, received: Any, allowed: Any) -> CliFailure:
    return CliFailure(
        "E-INPUT-04",
        f"E-INPUT-04 {field}が値域外です: 受取{received!r}、許容{allowed}。",
        detail={"allowed": allowed, "field": field, "received": received},
        remedy=REMEDIES["E-INPUT-04"],
    )


def validate_set_conditions(
    expected_format: str,
    expected_level: str,
    requested_count_text: str,
    resources: dict[str, Any],
) -> tuple[dict[str, str], int]:
    if expected_format not in FORMAT_VALUES:
        raise invalid_input_value("expected_format", expected_format, list(FORMAT_VALUES))
    if expected_format in VOCAB_FORMATS:
        scale = "cefr"
        allowed_levels = tuple(CEFR_RANK)
    else:
        scale = "cefrj"
        allowed_levels = tuple(CEFRJ_RANK)
    if expected_level not in allowed_levels:
        raise invalid_input_value("expected_level", expected_level, list(allowed_levels))
    try:
        requested_count = int(requested_count_text)
    except ValueError as exc:
        raise invalid_input_value("requested_count", requested_count_text, "1以上の整数") from exc
    maximum = resources["limits"]["set_question_max"]
    if str(requested_count) != requested_count_text or not 1 <= requested_count <= maximum:
        raise invalid_input_value("requested_count", requested_count_text, f"1〜{maximum}の10進整数")
    return {"scale": scale, "value": expected_level}, requested_count


def decode_candidate_utf8(payload: bytes, source_name: str) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        prefix = payload[: exc.start]
        line = prefix.count(b"\n") + 1
        line_start = prefix.rfind(b"\n") + 1
        column = exc.start - line_start + 1
        raise CliFailure(
            "E-INPUT-03",
            f"E-INPUT-03 candidate入力がUTF-8ではありません: {source_name}（{line}行{column}列）。",
            detail={
                "column": column,
                "encoding": "utf-8",
                "error": str(exc),
                "line": line,
                "source": source_name,
            },
            remedy=REMEDIES["E-INPUT-03"],
        ) from exc


def parse_candidate(path_text: str) -> dict[str, Any]:
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
        text = payload if isinstance(payload, str) else decode_candidate_utf8(payload, source_name)
    else:
        path = Path(path_text)
        if not path.is_file():
            raise CliFailure(
                "E-INPUT-02",
                f"E-INPUT-02 candidateファイルが存在しないか読み取れません: {path}",
                detail={"path": str(path)},
                remedy=REMEDIES["E-INPUT-02"],
            )
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise CliFailure(
                "E-INPUT-02",
                f"E-INPUT-02 candidateファイルを読み取れません: {path}",
                detail={"error": str(exc), "path": str(path)},
                remedy=REMEDIES["E-INPUT-02"],
            ) from exc
        text = decode_candidate_utf8(payload, source_name)
    try:
        document = strict_candidate_json_loads(text)
    except json.JSONDecodeError as exc:
        detail: dict[str, Any] = {
            "column": exc.colno,
            "error": str(exc),
            "line": exc.lineno,
            "source": source_name,
        }
        if isinstance(exc, JsonIntegerTooLong):
            detail["digit_count"] = exc.digit_count
            detail["digit_limit"] = exc.digit_limit
        position = f"{exc.lineno}行{exc.colno}列"
        raise CliFailure(
            "E-INPUT-03",
            f"E-INPUT-03 candidate JSONをパースできません: {source_name}（{position}）。",
            detail=detail,
            remedy=REMEDIES["E-INPUT-03"],
        ) from exc
    if not isinstance(document, dict):
        return document
    return document


def contract_failure(
    target: str,
    errors: list[dict[str, str]],
    schema_version: str = "1.0.0",
) -> CliFailure:
    rendered = "; ".join(
        f"{error['json_pointer'] or '/'} {error['message']}" for error in errors[:50]
    )
    if len(errors) > 50:
        rendered = f"先頭50件: {rendered}; 総数{len(errors)}件"
    return CliFailure(
        "E-CONTRACT-01",
        f"E-CONTRACT-01 {target}がスキーマ{schema_version}に適合しません: {rendered}",
        detail={"errors": errors[:50], "schema_version": schema_version, "target": target, "total_errors": len(errors)},
        remedy=REMEDIES["E-CONTRACT-01"],
    )


def fill_blank(template: str, answer: str) -> str:
    return template.replace("____", answer)


def extract_text_targets(candidate: dict[str, Any]) -> list[TextTarget]:
    body = candidate["body"]
    fmt = candidate["format"]
    targets: list[TextTarget] = []
    if fmt == "vocab_mcq_en2ja":
        targets.append(TextTarget("body.stem", body["stem"], True, True))
    elif fmt == "vocab_mcq_ja2en":
        targets.append(
            TextTarget(
                "body.sentence_with_blank#filled:answer",
                body["sentence_complete"],
                True,
                True,
            )
        )
        targets.extend(
            TextTarget(
                f"body.choices[{index}].text",
                choice["text"],
                False,
                declared_anchor=choice["anchor"],
            )
            for index, choice in enumerate(body["choices"])
        )
    elif fmt in {"vocab_flashcard_en2ja", "vocab_flashcard_ja2en"}:
        targets.append(TextTarget("body.example.en", body["example"]["en"], True, True))
    elif fmt == "grammar_mcq":
        correct = next(choice for choice in body["choices"] if choice["is_correct"])
        targets.append(
            TextTarget(
                "body.sentence_with_blank#filled:answer",
                fill_blank(body["sentence_with_blank"], correct["text"]),
                True,
            )
        )
        targets.extend(
            TextTarget(
                f"body.sentence_with_blank#filled:choices[{index}]",
                fill_blank(body["sentence_with_blank"], choice["text"]),
                True,
            )
            for index, choice in enumerate(body["choices"])
            if not choice["is_correct"]
        )
        if body["context_sentence"] is not None:
            targets.append(TextTarget("body.context_sentence", body["context_sentence"], True))
    elif fmt == "grammar_cloze":
        targets.append(
            TextTarget(
                "body.sentence_with_blank#filled:answer",
                fill_blank(body["sentence_with_blank"], body["answer"]),
                True,
            )
        )
        if body["context_sentence"] is not None:
            targets.append(TextTarget("body.context_sentence", body["context_sentence"], True))
        targets.extend(
            TextTarget(f"body.answer_equivalents[{index}]", answer, False)
            for index, answer in enumerate(body["answer_equivalents"])
        )
    elif fmt == "grammar_reorder":
        targets.append(TextTarget("body.answer_sentence", body["answer_sentence"], True))
    elif fmt == "grammar_rewrite":
        targets.append(TextTarget("body.source_sentence", body["source_sentence"], True))
        targets.append(
            TextTarget(
                "body.target_sentence_with_blank#filled:answer",
                fill_blank(body["target_sentence_with_blank"], body["answer"]),
                True,
            )
        )
    else:
        targets.append(TextTarget("body.example.en", body["example"]["en"], True))
        if body["context_sentence"] is not None:
            targets.append(TextTarget("body.context_sentence", body["context_sentence"], True))
    return targets


def japanese_fields(candidate: dict[str, Any]) -> list[tuple[str, str]]:
    body = candidate["body"]
    fmt = candidate["format"]
    fields: list[tuple[str, str]] = []
    if fmt == "vocab_mcq_en2ja":
        fields.append(("body.stem_ja", body["stem_ja"]))
        for index, choice in enumerate(body["choices"]):
            fields.append((f"body.choices[{index}].text", choice["text"]))
            fields.append((f"body.choices[{index}].gloss", choice["gloss"]))
    elif fmt == "vocab_mcq_ja2en":
        fields.extend((("body.stem", body["stem"]), ("body.sentence_ja", body["sentence_ja"])))
        fields.extend(
            (f"body.choices[{index}].gloss", choice["gloss"])
            for index, choice in enumerate(body["choices"])
        )
    elif fmt in {"vocab_flashcard_en2ja", "vocab_flashcard_ja2en"}:
        fields.extend((("body.gloss", body["gloss"]), ("body.example.ja", body["example"]["ja"])))
    elif fmt in {"grammar_mcq", "grammar_cloze", "grammar_reorder"}:
        fields.append(("body.example_ja", body["example_ja"]))
        fields.append(("explanation.text", candidate["explanation"]["text"]))
    elif fmt == "grammar_rewrite":
        fields.extend(
            (
                ("body.instruction", body["instruction"]),
                ("body.source_ja", body["source_ja"]),
                ("body.target_ja", body["target_ja"]),
                ("explanation.text", candidate["explanation"]["text"]),
            )
        )
    else:
        fields.extend(
            (
                ("body.example.ja", body["example"]["ja"]),
                ("explanation.text", candidate["explanation"]["text"]),
            )
        )
    return fields


def corrected_lemma(token: Any) -> tuple[str, bool]:
    surface_key = lookup_key(token.text)
    if surface_key in LEMMA_CORRECTIONS:
        return LEMMA_CORRECTIONS[surface_key], True
    lemma = nfc(token.lemma_)
    return lemma if lemma else nfc(token.text), False


def pos_candidates(token: Any, lemma_key: str) -> tuple[str, ...]:
    if token.pos_ in {"VERB", "AUX"} and lemma_key in {"be", "do", "have"}:
        return (f"{lemma_key}-verb",)
    if token.tag_ == "TO":
        if token.pos_ == "PART":
            return ("infinitive-to",)
        if token.pos_ == "ADP":
            return ("preposition",)
        return ()
    return POS_CANDIDATES.get(token.tag_, ())


def violation(
    code: str,
    location: str,
    evidence: str,
    suggestion: str,
    *,
    expected_level: str | None = None,
    actual_level: str | None = None,
) -> dict[str, Any]:
    return {
        "actual_level": actual_level,
        "code": code,
        "evidence": evidence,
        "expected_level": expected_level,
        "location": location,
        "suggestion": suggestion,
    }


def warning(code: str, location: str, message: str) -> dict[str, str]:
    return {"code": code, "location": location, "message": message}


def token_location(field: str, index: int, surface: str) -> str:
    return f'{field} token {index + 1}: "{surface}"'


class LexicalMatcher:
    def __init__(self, nlp: Any, lexicon: dict[str, Any], allowlist: list[str]) -> None:
        self.nlp = nlp
        self.entries = lexicon["entries"]
        self.allowlist = set(allowlist)
        self.by_id = {entry["id"]: entry for entry in self.entries}
        self.by_key: dict[str, list[dict[str, Any]]] = {}
        for entry in self.entries:
            self.by_key.setdefault(lookup_key(entry["headword"]), []).append(entry)
        multiwords = [entry for entry in self.entries if entry["is_multiword"]]
        docs = nlp.pipe(entry["headword"] for entry in multiwords)
        self.multiword_patterns: list[tuple[tuple[str, ...], str, dict[str, Any]]] = []
        for entry, doc in zip(multiwords, docs, strict=True):
            key = tuple(lookup_key(token.text) for token in doc)
            self.multiword_patterns.append((key, entry["id"], entry))
        self.multiword_patterns.sort(key=lambda item: (-len(item[0]), item[1]))

    def match_doc(
        self,
        target: TextTarget,
        doc: Any,
        allowed_level: str,
        target_entry: dict[str, Any] | None,
    ) -> tuple[
        dict[str, Any],
        list[dict[str, Any]],
        list[dict[str, str]],
        int,
        list[str],
    ]:
        violations: list[dict[str, Any]] = []
        warnings: list[dict[str, str]] = []
        stats: list[dict[str, Any] | None] = [None] * len(doc)
        consumed: set[int] = set()
        target_occurrences = 0
        target_surfaces: list[str] = []
        target_id = target_entry["id"] if target_entry is not None else None
        target_pattern = None
        if target.target_occurrence and target_entry is not None:
            target_pattern = tuple(
                lookup_key(token.text)
                for token in self.nlp.make_doc(target_entry["headword"])
            )
        declared_entry = None
        declared_pattern = None
        if target.declared_anchor is not None:
            declared_entry = self.by_id.get(target.declared_anchor["entry_id"])
            if declared_entry is not None:
                expected_values = {
                    "headword": declared_entry["headword"],
                    "level": declared_entry["level"],
                    "pos": declared_entry["pos"],
                }
                recorded_values = {
                    "headword": target.declared_anchor["headword"],
                    "level": target.declared_anchor["level"],
                    "pos": target.declared_anchor["pos"],
                }
                if (
                    recorded_values == expected_values
                    and target.text.lower() == declared_entry["headword"].lower()
                ):
                    declared_pattern = tuple(
                        lookup_key(token.text)
                        for token in self.nlp.make_doc(declared_entry["headword"])
                    )

        surface_keys = [lookup_key(token.text) for token in doc]
        lemma_keys = [lookup_key(token.lemma_ or token.text) for token in doc]
        corrected_lemma_keys = [lookup_key(corrected_lemma(token)[0]) for token in doc]
        for start in range(len(doc)):
            if start in consumed:
                continue
            adopted: tuple[tuple[str, ...], str, dict[str, Any]] | None = None
            adopted_decision = "multiword_match"
            for pattern in self.multiword_patterns:
                keys, _entry_id, _entry = pattern
                end = start + len(keys)
                if end > len(doc) or any(index in consumed for index in range(start, end)):
                    continue
                if tuple(surface_keys[start:end]) == keys or tuple(lemma_keys[start:end]) == keys:
                    adopted = pattern
                    break
            if target_pattern:
                target_end = start + len(target_pattern)
                target_available = target_end <= len(doc) and not any(
                    index in consumed for index in range(start, target_end)
                )
                target_matches = target_available and (
                    tuple(surface_keys[start:target_end]) == target_pattern
                    or tuple(corrected_lemma_keys[start:target_end]) == target_pattern
                )
                if target_matches and (
                    adopted is None or len(target_pattern) >= len(adopted[0])
                ):
                    adopted = (target_pattern, target_id, target_entry)
                    adopted_decision = "target"
            if declared_pattern and start == 0:
                declared_end = start + len(declared_pattern)
                declared_matches = declared_end == len(doc) and (
                    tuple(surface_keys[start:declared_end]) == declared_pattern
                )
                if declared_matches and (
                    adopted is None or len(declared_pattern) >= len(adopted[0])
                ):
                    adopted = (declared_pattern, declared_entry["id"], declared_entry)
                    adopted_decision = "wordlist_match"
            if adopted is None:
                continue
            keys, _entry_id, entry = adopted
            end = start + len(keys)
            indices = range(start, end)
            consumed.update(indices)
            is_target = adopted_decision == "target"
            if is_target:
                target_occurrences += 1
                target_surfaces.append(
                    doc.text[doc[start].idx : doc[end - 1].idx + len(doc[end - 1].text)]
                )
            too_high = CEFR_RANK[entry["level"]] > CEFR_RANK[allowed_level]
            if too_high:
                quoted = " ".join(token.text for token in doc[start:end])
                violations.append(
                    violation(
                        "V-LEX-02",
                        token_location(target.field, start, quoted),
                        f"採用エントリ{entry['id']}はWordlist {entry['level']}、許容上限は{allowed_level}です。",
                        "指定帯以下のWordlist収録語へ置き換えてください。",
                        expected_level=allowed_level,
                        actual_level=entry["level"],
                    )
                )
            for index in indices:
                token = doc[index]
                lemma, corrected = corrected_lemma(token)
                if corrected:
                    warnings.append(
                        warning(
                            "W-LEMMA-01",
                            token_location(target.field, index, token.text),
                            f"レンマ補正表を適用し{lemma!r}として照合しました。",
                        )
                    )
                if token.tag_ in {"NNP", "NNPS"}:
                    warnings.append(
                        warning(
                            "W-PROPN-01",
                            token_location(target.field, index, token.text),
                            "固有名詞タグのトークンをWordlist収録語として照合しました。",
                        )
                    )
                stats[index] = self.token_stat(
                    token,
                    lemma,
                    "violation" if too_high else adopted_decision,
                    entry,
                )

        for index, token in enumerate(doc):
            if index in consumed:
                continue
            lemma, correction_applied = corrected_lemma(token)
            lemma_key = lookup_key(lemma)
            location = token_location(target.field, index, token.text)
            if correction_applied:
                warnings.append(
                    warning(
                        "W-LEMMA-01",
                        location,
                        f"レンマ補正表を適用し{lemma!r}として照合しました。",
                    )
                )

            exemption_tag = (
                token.pos_ in {"PUNCT", "SYM"}
                or token.tag_ in {"POS", "HYPH"}
                or token.text.isspace()
            )
            candidates = [] if exemption_tag else self.by_key.get(lemma_key, [])
            adopted_entry: dict[str, Any] | None = None
            for candidate_pos in pos_candidates(token, lemma_key):
                adopted_entry = next(
                    (entry for entry in candidates if entry["pos"] == candidate_pos), None
                )
                if adopted_entry is not None:
                    break
            if adopted_entry is None and candidates:
                minimum_rank = min(CEFR_RANK[entry["level"]] for entry in candidates)
                adopted_entry = next(
                    entry for entry in candidates if CEFR_RANK[entry["level"]] == minimum_rank
                )
                warnings.append(
                    warning(
                        "W-POS-01",
                        location,
                        f"品詞候補列で一致せず、品詞不問で{adopted_entry['id']}を採用しました。",
                    )
                )

            if adopted_entry is not None:
                too_high = CEFR_RANK[adopted_entry["level"]] > CEFR_RANK[allowed_level]
                if too_high:
                    violations.append(
                        violation(
                            "V-LEX-02",
                            location,
                            f"採用エントリ{adopted_entry['id']}はWordlist {adopted_entry['level']}、許容上限は{allowed_level}です。",
                            "指定帯以下のWordlist収録語へ置き換えてください。",
                            expected_level=allowed_level,
                            actual_level=adopted_entry["level"],
                        )
                    )
                if token.tag_ in {"NNP", "NNPS"}:
                    warnings.append(
                        warning(
                            "W-PROPN-01",
                            location,
                            "固有名詞タグのトークンをWordlist収録語として照合しました。",
                        )
                    )
                stats[index] = self.token_stat(
                    token,
                    lemma,
                    "violation" if too_high else "wordlist_match",
                    adopted_entry,
                )
                continue

            if token.text in self.allowlist:
                stats[index] = self.token_stat(token, lemma, "allowlist", None)
                continue

            exemption = self.exemption_class(token, lemma)
            if exemption is not None:
                stats[index] = self.token_stat(token, lemma, "exempt", None, exemption)
                continue

            violations.append(
                violation(
                    "V-LEX-01",
                    location,
                    f"表層形{token.text!r}・レンマ{lemma!r}はWordlist・allowlist・免除規則のいずれにも一致しません。",
                    "指定帯以下のWordlist収録語またはallowlist収録語へ置き換えてください。",
                )
            )
            if not correction_applied and lemma_key != lookup_key(token.text):
                warnings.append(
                    warning(
                        "W-LEMMA-01",
                        location,
                        f"表層形と異なるレンマ{lemma!r}でもWordlist照合に失敗しました。",
                    )
                )
            stats[index] = self.token_stat(token, lemma, "violation", None)

        text_stat = {
            "field": target.field,
            "sentence_count": sum(1 for _sentence in doc.sents),
            "text": target.text,
            "tokens": stats,
            "word_count": sum(1 for token in doc if token.pos_ not in {"PUNCT", "SYM"}),
        }
        return text_stat, violations, warnings, target_occurrences, target_surfaces

    @staticmethod
    def token_stat(
        token: Any,
        lemma: str,
        decision: str,
        entry: dict[str, Any] | None,
        exemption: str | None = None,
    ) -> dict[str, Any]:
        return {
            "decision": decision,
            "exemption_class": exemption,
            "lemma": lemma,
            "level": entry["level"] if entry is not None else None,
            "matched_entry_id": entry["id"] if entry is not None else None,
            "surface": token.text,
            "tag": token.tag_,
            "upos": token.pos_,
        }

    @staticmethod
    def exemption_class(token: Any, lemma: str) -> str | None:
        if any(pattern.fullmatch(token.text) for pattern in NUMERIC_PATTERNS):
            return "numeric"
        if token.pos_ in {"PUNCT", "SYM"} or token.tag_ == "HYPH" or token.text.isspace():
            return "punct_sym_space"
        if token.tag_ == "POS":
            return "possessive"
        if (not lemma.strip() or SYMBOL_ONLY_PATTERN.fullmatch(lemma)) and "'" in token.text:
            return "contraction_fragment"
        return None


def answer_tokens(answer_sentence: str) -> list[str]:
    normalized = nfc(answer_sentence).replace("\u2019", "'")
    parts = re.split(r"[ \t]", normalized)
    return [re.sub(r"[.,?!;:]", "", part).lower() for part in parts if re.sub(r"[.,?!;:]", "", part)]


def compatible_pos(first: str, second: str) -> bool:
    return any(first in group and second in group for group in COMPATIBLE_POS_GROUPS)


def check_context(candidate: dict[str, Any], violations: list[dict[str, Any]]) -> None:
    if candidate["format"] not in CONTEXT_FORMATS:
        return
    body = candidate["body"]
    sentence = body["context_sentence"]
    required_by = body["context_required_by"]
    if (sentence is None) != (required_by is None):
        violations.append(
            violation(
                "V-SENT-01",
                "body.context_sentence / body.context_required_by",
                "context_sentenceとcontext_required_byのnull状態が一致しません。",
                "両方をnullにするか、両方に先行文脈と要求元文タイプを記録してください。",
            )
        )
    if required_by is not None and required_by not in CONTEXT_REQUIRED_VALUES:
        violations.append(
            violation(
                "V-SENT-01",
                "body.context_required_by",
                f"要求元文タイプ{required_by!r}は許容2値に含まれません。",
                "前文が肯定平叙または前文が否定平叙を記録してください。",
            )
        )


def check_choice_structure(candidate: dict[str, Any], violations: list[dict[str, Any]]) -> None:
    if candidate["format"] not in CHOICE_FORMATS:
        return
    choices = candidate["body"]["choices"]
    if len(choices) != 4 or sum(1 for choice in choices if choice["is_correct"]) != 1:
        violations.append(
            violation(
                "V-CHO-01",
                "body.choices",
                f"選択肢数{len(choices)}、正解指定数{sum(1 for choice in choices if choice['is_correct'])}です。",
                "選択肢を4個、正解指定を1個にしてください。",
            )
        )
    fmt = candidate["format"]
    comparison_key = japanese_choice_key if fmt == "vocab_mcq_en2ja" else english_choice_key
    comparison_rule = "trim・NFC" if fmt == "vocab_mcq_en2ja" else "trim・英語小文字化"
    values = [comparison_key(choice["text"]) for choice in choices]
    if len(set(values)) != len(values):
        violations.append(
            violation(
                "V-CHO-01",
                "body.choices[*].text",
                f"{comparison_rule}後に重複する選択肢があります。",
                "4つの選択肢表記を互いに異なる文字列へ修正してください。",
            )
        )


def check_vocab_target(
    candidate: dict[str, Any],
    lexicon_by_id: dict[str, dict[str, Any]],
    target_occurrences: int,
    target_surfaces: list[str],
    requested_level: str,
    violations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    target_ref = candidate["target"]["ref"]
    target_entry = lexicon_by_id.get(target_ref)
    if target_entry is None or target_entry["level"] != requested_level:
        actual = target_entry["level"] if target_entry is not None else None
        violations.append(
            violation(
                "V-TGT-03",
                "target.ref",
                f"対象{target_ref}の実在・レベル一致を確認できません（指定{requested_level}、実測{actual}）。",
                "lookup.pyで指定レベルに実在する語彙エントリを選び直してください。",
                expected_level=requested_level,
                actual_level=actual,
            )
        )
    if target_occurrences != 1:
        violations.append(
            violation(
                "V-TGT-02",
                "target.ref / 対象語出現照合フィールド",
                f"対象{target_ref}の照合回数は{target_occurrences}回です。",
                "対象語を指定フィールドにちょうど1回だけ出現させてください。",
            )
        )
    body = candidate["body"]
    if body["target_surface"] not in target_surfaces:
        violations.append(
            violation(
                "V-TGT-02",
                "body.target_surface",
                f"target_surface {body['target_surface']!r}は採用対象区間{target_surfaces!r}の原文スライスと一致しません。",
                "機械照合で採用される対象区間の原文スライスをtarget_surfaceへ完全一致で記録してください。",
            )
        )
    highlighted_text = None
    if candidate["format"] == "vocab_mcq_en2ja":
        highlighted_text = body["stem"]
    elif candidate["format"] in {
        "vocab_flashcard_en2ja",
        "vocab_flashcard_ja2en",
    }:
        highlighted_text = body["example"]["en"]
    if highlighted_text is not None:
        surface = body["target_surface"]
        first = highlighted_text.find(surface)
        if first < 0 or first != highlighted_text.rfind(surface):
            violations.append(
                violation(
                    "V-TGT-02",
                    "body.target_surface",
                    f"対象英文中のtarget_surface {surface!r}の完全一致開始位置が一意ではありません。",
                    "target_surfaceと完全一致する部分文字列が対象区間の1箇所だけになる例文へ修正してください。",
                )
            )
    if candidate["format"] == "vocab_mcq_ja2en":
        if target_entry is not None and body["target_surface"] != target_entry["headword"]:
            violations.append(
                violation(
                    "V-TGT-02",
                    "body.target_surface",
                    f"target_surface {body['target_surface']!r}と対象headword {target_entry['headword']!r}が一致しません。",
                    "target_surfaceを対象エントリのheadwordと完全一致させてください。",
                )
            )
        completed = fill_blank(body["sentence_with_blank"], body["target_surface"])
        if completed != body["sentence_complete"]:
            violations.append(
                violation(
                    "V-TGT-02",
                    "body.sentence_complete",
                    f"空欄置換結果{completed!r}とsentence_completeが一致しません。",
                    "sentence_with_blankの空欄をtarget_surfaceで置換した完成文を記録してください。",
                )
            )
    return target_entry


def check_grammar_target(
    candidate: dict[str, Any],
    grammar_by_id: dict[str, dict[str, Any]],
    requested_level: str,
    violations: list[dict[str, Any]],
) -> None:
    target_ref = candidate["target"]["ref"]
    entry = grammar_by_id.get(target_ref)
    requested = requested_level
    eligible = False
    if entry is not None and entry["target_eligible"] and entry["level"]["min"] is not None:
        rank = CEFRJ_RANK[requested]
        eligible = CEFRJ_RANK[entry["level"]["min"]] <= rank <= CEFRJ_RANK[entry["level"]["max"]]
    if not eligible:
        actual = entry["level"]["min"] if entry is not None else None
        evidence = "項目が存在しません。" if entry is None else (
            f"target_eligible={entry['target_eligible']}、範囲={entry['level']['min']}〜{entry['level']['max']}、指定={requested}です。"
        )
        violations.append(
            violation(
                "V-TGT-01",
                "target.ref",
                f"対象{target_ref}は指定レベルでターゲット適格ではありません: {evidence}",
                "lookup.py gp --levelで指定レベルに適格な教員版項目を選び直してください。",
                expected_level=requested,
                actual_level=actual,
            )
        )


def check_distractor_anchors(
    candidate: dict[str, Any],
    lexicon_by_id: dict[str, dict[str, Any]],
    target_entry: dict[str, Any] | None,
    requested_level: str,
    violations: list[dict[str, Any]],
) -> None:
    if candidate["format"] not in {"vocab_mcq_en2ja", "vocab_mcq_ja2en"}:
        return
    body = candidate["body"]
    choices = body["choices"]
    target_ref = candidate["target"]["ref"]
    target_pos = (
        target_entry["pos"] if target_entry is not None else lexical_pos_from_ref(target_ref)
    )
    distractors = [choice for choice in choices if not choice["is_correct"]]
    for index, choice in enumerate(choices):
        anchor = choice["anchor"]
        entry = lexicon_by_id.get(anchor["entry_id"])
        expected_values = None if entry is None else {
            "headword": entry["headword"], "level": entry["level"], "pos": entry["pos"]
        }
        recorded_values = {
            "headword": anchor["headword"], "level": anchor["level"], "pos": anchor["pos"]
        }
        bad_source = entry is None or recorded_values != expected_values
        if candidate["format"] == "vocab_mcq_ja2en" and entry is not None:
            bad_source = bad_source or choice["text"].lower() != entry["headword"].lower()
        if bad_source:
            violations.append(
                violation(
                    "V-DIS-01",
                    f"body.choices[{index}].anchor",
                    f"記録{recorded_values}、正規化データ実値{expected_values}、選択肢表記{choice['text']!r}です。",
                    "lookup.pyの実在エントリ値をanchorへ転記してください。",
                )
            )
        if not choice["is_correct"]:
            pos_ok = anchor["pos"] == target_pos
            if body["pos_pool_relaxed"]:
                pos_ok = compatible_pos(anchor["pos"], target_pos)
            if anchor["level"] != requested_level or not pos_ok:
                violations.append(
                    violation(
                        "V-DIS-02",
                        f"body.choices[{index}].anchor",
                        f"誤答level={anchor['level']}、pos={anchor['pos']}、対象level={requested_level}、pos={target_pos}、緩和={body['pos_pool_relaxed']}です。",
                        "同レベル・同品詞、または記録済み互換品詞群の実在語へ差し替えてください。",
                        expected_level=requested_level,
                        actual_level=anchor["level"],
                    )
                )
    if body["pos_pool_relaxed"]:
        cross_pos_used = False
        for choice in distractors:
            entry = lexicon_by_id.get(choice["anchor"]["entry_id"])
            if (
                entry is not None
                and choice["anchor"]["pos"] == entry["pos"]
                and entry["pos"] != target_pos
            ):
                cross_pos_used = True
                break
        if not cross_pos_used:
            violations.append(
                violation(
                    "V-DIS-02",
                    "body.pos_pool_relaxed",
                    f"異品詞誤答使用={cross_pos_used}、緩和=trueです。",
                    "互換品詞群に属する対象と異なるposの誤答を実際に使う場合だけtrueにしてください。緩和の必要性はCHK-06で確認してください。",
                    expected_level=requested_level,
                    actual_level=requested_level,
                )
            )
    anchor_ids = [choice["anchor"]["entry_id"] for choice in choices]
    correct_ids = [choice["anchor"]["entry_id"] for choice in choices if choice["is_correct"]]
    identity_bad = len(set(anchor_ids)) != len(anchor_ids)
    identity_bad = identity_bad or correct_ids != [target_ref]
    identity_bad = identity_bad or any(
        choice["anchor"]["entry_id"] == target_ref
        for choice in choices
        if not choice["is_correct"]
    )
    if identity_bad:
        violations.append(
            violation(
                "V-DIS-03",
                "body.choices[*].anchor.entry_id",
                f"選択肢アンカー={anchor_ids}、正解アンカー={correct_ids}、対象={candidate['target']['ref']}です。",
                "4アンカーを互いに異ならせ、正解だけを対象エントリと一致させてください。",
            )
        )


def check_form_specific(candidate: dict[str, Any], violations: list[dict[str, Any]], docs_by_field: dict[str, Any]) -> None:
    fmt = candidate["format"]
    body = candidate["body"]
    if fmt == "grammar_reorder":
        correct = answer_tokens(body["answer_sentence"])
        shuffled = body["tokens_shuffled"]
        if Counter(correct) != Counter(shuffled):
            violations.append(
                violation(
                    "V-ORD-01",
                    "body.tokens_shuffled",
                    f"正解導出列={correct}、シャッフル列={shuffled}で多重集合が一致しません。",
                    "answer_sentenceからFIN-04で導出される全トークンを過不足なく並べてください。",
                )
            )
        if correct == shuffled:
            violations.append(
                violation(
                    "V-ORD-02",
                    "body.tokens_shuffled",
                    f"シャッフル列が正解順{correct}と同一です。",
                    "多重集合を保ったまま正解順と異なる順序へ並べ替えてください。",
                )
            )
    if fmt in {"grammar_cloze", "grammar_rewrite"}:
        answer = answer_equivalent_key(body["answer"])
        equivalents = [answer_equivalent_key(value) for value in body["answer_equivalents"]]
        if answer in equivalents or len(set(equivalents)) != len(equivalents):
            violations.append(
                violation(
                    "V-CLZ-02",
                    "body.answer_equivalents",
                    f"前後空白除去・小文字化後のanswer={answer!r}、同値表記={equivalents}です。",
                    "answer自身と前後空白除去・大文字小文字無視で重複する値をanswer_equivalentsから除いてください。",
                )
            )
    if fmt == "grammar_cloze":
        field = "body.sentence_with_blank#filled:answer"
        if sum(1 for _sent in docs_by_field[field].sents) != 1:
            violations.append(
                violation(
                    "V-CLZ-01",
                    field,
                    "answer代入後の完成文をspaCyで1文として解析できません。",
                    "空欄へanswerを代入した結果が完全な英文1文になるよう修正してください。",
                )
            )
    if fmt == "grammar_rewrite":
        target = fill_blank(body["target_sentence_with_blank"], body["answer"])
        if normalized_comparison(body["source_sentence"]) == normalized_comparison(target):
            violations.append(
                violation(
                    "V-RWT-01",
                    "body.source_sentence / body.target_sentence_with_blank#filled:answer",
                    "NFC・trim・小文字化・空白正規化後の元文と目標文が同一です。",
                    "元文と異なる文法構造の目標文へ書き換えてください。",
                )
            )


def machine_check(
    candidate: dict[str, Any],
    set_id: str,
    generation: str,
    resources: dict[str, Any],
    nlp: Any,
    model_version: str,
    expected_format: str,
    expected_level: dict[str, str],
    requested_count: int,
) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []

    if candidate["format"] != expected_format:
        violations.append(
            violation(
                "V-COND-01",
                "format",
                f"セット形式={expected_format}、candidate形式={candidate['format']}です。",
                "candidateのformatをセットの確定済み形式と一致させてください。",
            )
        )
    if candidate["level"] != expected_level:
        violations.append(
            violation(
                "V-COND-01",
                "level",
                f"セットレベル={expected_level}、candidateレベル={candidate['level']}です。",
                "candidateのlevel.scaleとlevel.valueをセットの確定済みレベルと一致させてください。",
                expected_level=expected_level["value"],
                actual_level=candidate["level"]["value"],
            )
        )
    question_ordinal = int(candidate["question_id"][1:])
    trial_question_id_max = min(2 * requested_count, QUESTION_ID_MAX)
    if question_ordinal > trial_question_id_max:
        violations.append(
            violation(
                "V-COND-01",
                "question_id",
                f"依頼問題数={requested_count}、試行ID上限=q{trial_question_id_max:02d}、"
                f"candidate問題ID={candidate['question_id']}です。",
                f"question_idをq01〜q{trial_question_id_max:02d}の範囲に修正してください。",
            )
        )

    lexicon_entries = resources["lexicon"]["entries"]
    lexicon_by_id = {entry["id"]: entry for entry in lexicon_entries}
    grammar_by_id = {entry["id"]: entry for entry in resources["grammar"]["entries"]}
    target_entry = lexicon_by_id.get(candidate["target"]["ref"]) if candidate["format"] in VOCAB_FORMATS else None
    matcher = LexicalMatcher(nlp, resources["lexicon"], resources["proper_nouns"]["words"])
    validation_level = (
        expected_level
        if candidate["level"]["scale"] == expected_level["scale"]
        else candidate["level"]
    )
    requested_level = validation_level["value"]
    allowed_level = (
        requested_level
        if validation_level["scale"] == "cefr"
        else requested_level.split(".", 1)[0]
    )

    targets = extract_text_targets(candidate)
    docs = list(nlp.pipe(target.text for target in targets))
    docs_by_field = {target.field: doc for target, doc in zip(targets, docs, strict=True)}

    # S4: 構造制約。全対象のS4を終えてからS5へ進む。
    check_context(candidate, violations)
    for target, doc in zip(targets, docs, strict=True):
        if target.sentence_checks:
            sentence_count = sum(1 for _sentence in doc.sents)
            word_count = sum(1 for token in doc if token.pos_ not in {"PUNCT", "SYM"})
            if sentence_count != 1:
                violations.append(
                    violation(
                        "V-SENT-01",
                        target.field,
                        f"spaCy doc.sentsの文数は{sentence_count}です。",
                        "検査対象フィールドを完全な英文1文にしてください。",
                    )
                )
            limit = resources["limits"]["sentence_word_limits"][allowed_level]
            if word_count > limit:
                violations.append(
                    violation(
                        "V-LEN-01",
                        target.field,
                        f"語数{word_count}が{allowed_level}上限{limit}を超えています。",
                        f"句読点・記号を除く語数を{limit}語以下にしてください。",
                    )
                )

    explanation_count: int | None = None
    if candidate["format"] not in VOCAB_FORMATS:
        explanation = candidate["explanation"]
        explanation_count = len(nfc(explanation["text"]))
        limit = resources["limits"]["explanation_char_limits"][explanation["type"]]
        if explanation_count > limit:
            violations.append(
                violation(
                    "V-EXP-01",
                    "explanation.text",
                    f"NFC正規化後の字数{explanation_count}が{explanation['type']}上限{limit}を超えています。",
                    f"解説を{limit}文字以下にしてください。",
                )
            )

    for field, value in japanese_fields(candidate):
        if JAPANESE_PATTERN.search(nfc(value)) is None:
            violations.append(
                violation(
                    "V-JPN-01",
                    field,
                    "NFC正規化後の文字列にひらがな・カタカナ・CJK統合漢字がありません。",
                    "日本語文字を含む訳・語義・指示・解説へ修正してください。",
                )
            )

    # S5: 語彙照合。トークン統計もこの段で確定する。
    stats: list[dict[str, Any]] = []
    target_occurrences = 0
    target_surfaces: list[str] = []
    for target, doc in zip(targets, docs, strict=True):
        (
            text_stat,
            lexical_violations,
            lexical_warnings,
            occurrences,
            matched_surfaces,
        ) = matcher.match_doc(target, doc, allowed_level, target_entry)
        stats.append(text_stat)
        warnings.extend(lexical_warnings)
        target_occurrences += occurrences
        target_surfaces.extend(matched_surfaces)
        violations.extend(lexical_violations)

    # S6: 形式固有検査。
    if candidate["format"] in VOCAB_FORMATS:
        target_entry = check_vocab_target(
            candidate,
            lexicon_by_id,
            target_occurrences,
            target_surfaces,
            requested_level,
            violations,
        )
    else:
        check_grammar_target(candidate, grammar_by_id, requested_level, violations)
    check_choice_structure(candidate, violations)
    check_distractor_anchors(
        candidate, lexicon_by_id, target_entry, requested_level, violations
    )
    check_form_specific(candidate, violations, docs_by_field)

    report = {
        "data_version": resources["meta"]["data_version"],
        "format": candidate["format"],
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "generation": generation,
        "level": candidate["level"],
        "question_id": candidate["question_id"],
        "schema_version": MACHINE_REPORT_SCHEMA_VERSION,
        "scope": "question",
        "set_id": set_id,
        "spacy_model": MODEL_NAME,
        "spacy_model_version": model_version,
        "stats": {"explanation_char_count": explanation_count, "texts": stats},
        "verdict": "fail" if violations else "pass",
        "violations": violations,
        "warnings": warnings,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    try:
        args = make_parser().parse_args(argv)
        validate_identifiers(args.set_id, args.generation)
        resources = load_validated_resources(Path.cwd())
        expected_level, requested_count = validate_set_conditions(
            args.expected_format, args.expected_level, args.requested_count, resources
        )
        nlp, model_version = load_spacy_model()
        candidate = parse_candidate(args.candidate)
        candidate_errors = schema_errors(candidate, Path.cwd() / "schemas/candidate.schema.json")
        if candidate_errors:
            raise contract_failure("candidate", candidate_errors)
        report = machine_check(
            candidate,
            args.set_id,
            args.generation,
            resources,
            nlp,
            model_version,
            args.expected_format,
            expected_level,
            requested_count,
        )
        report_errors = schema_errors(report, Path.cwd() / "schemas/machine_report.schema.json")
        if report_errors:
            raise contract_failure(
                "machine_report（内部生成結果）",
                report_errors,
                MACHINE_REPORT_SCHEMA_VERSION,
            )
        emit_json(report)
        return 0
    except CliFailure as exc:
        emit_json(exc.as_dict(), sys.stderr)
        return 1
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
