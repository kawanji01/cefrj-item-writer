#!/usr/bin/env python3
"""M5の監査収集・セット横断検査・確定処理で共有する決定的ロジック。"""

from __future__ import annotations

import base64
import binascii
import copy
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_normalized import CliFailure, schema_errors, strict_json_loads


SET_ID_PATTERN = re.compile(r"^[0-9]{8}-[0-9]{6}-[a-z0-9]{4}$")
QUESTION_ID_PATTERN = re.compile(r"^q(0[1-9]|1[0-9]|20)$")
GENERATION_PATTERN = re.compile(r"^gen[1-3]$")
REGULAR_AUDIT_PATTERN = re.compile(
    r"^(q(?:0[1-9]|1[0-9]|20))\.(gen[1-3])\."
    r"(candidate|machine|request|review)\.json$"
)
CANDIDATE_INVALID_PATTERN = re.compile(
    r"^(q(?:0[1-9]|1[0-9]|20))\.(gen[1-3])\.candidate\.invalid([12])\.txt$"
)
REVIEW_INVALID_PATTERN = re.compile(
    r"^(q(?:0[1-9]|1[0-9]|20))\.(gen[1-3])\.review\.invalid([123])\.txt$"
)
INVALID_AUDIT_FORMAT = "aud09-v2"
INVALID_AUDIT_KEYS = {
    "validation_failure": {
        "audit_format",
        "diagnostic",
        "kind",
        "raw_output_base64",
    },
    "utf8_encode_failure": {"audit_format", "kind", "position", "reason"},
    "process_failure": {"audit_format", "exit_code", "kind", "stderr_base64"},
}
SET_CHECK_PATTERN = re.compile(
    r"^set_check\.(q(?:0[1-9]|1[0-9]|20))\.(gen[1-3])\.json$"
)
SLOT_OUTCOME_PATTERN = re.compile(
    r"^slot\.(q(?:0[1-9]|1[0-9]|20))\.outcome\.json$"
)
FINAL_SET_CHECK_NAME = "set_check.final.json"
CODEX_WORK_PATTERN = re.compile(
    r"^q(?:0[1-9]|1[0-9]|20)\.gen[1-3]\.codex-(?:prompt|last)\.txt$"
)
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
VOCAB_FORMATS = set(FORMAT_VALUES[:4])
GRAMMAR_FORMATS = set(FORMAT_VALUES[4:])
BRIEF_EXPLANATION_FORMATS = {
    "grammar_mcq",
    "grammar_cloze",
    "grammar_reorder",
    "grammar_rewrite",
}
CEFR_VALUES = ("A1", "A2", "B1", "B2")
CEFRJ_VALUES = (
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
CEFR_CEILING = {
    "A1": "A1.3",
    "A2": "A2.2",
    "B1": "B1.2",
    "B2": "B2.2",
}
READABLE_RESOURCES = (
    "data/normalized/lexicon.json",
    "data/normalized/grammar.json",
    "data/normalized/meta.json",
    "data/config/limits.json",
    "data/config/proper_nouns.json",
    "docs/cefrj-validation-spec.md",
    "docs/subagent-review-spec.md",
    "agent/reviewer-core.md",
)
SCHEMA_FILE_BY_KIND = {
    "candidate": "candidate.schema.json",
    "machine": "machine_report.schema.json",
    "request": "review_request.schema.json",
    "review": "review_result.schema.json",
    "set_check": "machine_report.schema.json",
}
SCHEMA_LABEL_BY_KIND = {
    "candidate": "candidate",
    "machine": "machine_report",
    "request": "review_request",
    "review": "review_result",
    "set_check": "machine_report",
}
SLOT_OUTCOME_KEYS = {
    "accepted_question_id",
    "attempted_question_ids",
    "set_id",
    "slot_question_id",
    "status",
    "teacher_decision",
}
SENTENCE_FIELDS_BY_FORMAT = {
    "vocab_mcq_en2ja": {"body.stem"},
    "vocab_mcq_ja2en": {"body.sentence_with_blank#filled:answer"},
    "vocab_flashcard_en2ja": {"body.example.en"},
    "vocab_flashcard_ja2en": {"body.example.en"},
    "grammar_mcq": {
        "body.context_sentence",
        "body.sentence_with_blank#filled:answer",
    },
    "grammar_cloze": {
        "body.context_sentence",
        "body.sentence_with_blank#filled:answer",
    },
    "grammar_reorder": {"body.answer_sentence"},
    "grammar_rewrite": {
        "body.source_sentence",
        "body.target_sentence_with_blank#filled:answer",
    },
    "grammar_example_selfcheck": {"body.context_sentence", "body.example.en"},
}
GRAMMAR_MCQ_CHOICE_SENTENCE_PATTERN = re.compile(
    r"^body\.sentence_with_blank#filled:choices\[[0-3]\]$"
)

REMEDIES = {
    "E-CONTRACT-01": (
        "内部契約違反として報告し、監査ファイルを変更せず新しいset_idで"
        "セットを最初から作成してください。"
    ),
    "E-CONTRACT-03": (
        "当該セットは再開せず、監査ファイルを保持したまま新しいset_idで"
        "セットを最初から作成してください。"
    ),
    "E-CONTRACT-04": (
        "docs/interaction-flow.mdの不成立時教師照会フローに戻り、確定を強行しないでください。"
    ),
    "E-INPUT-02": "パスの綴りと存在、読み取り権限を確認してください。",
    "E-INPUT-03": "入力をUTF-8の標準JSONに修正してください。",
}


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def schema_version(repo_root: Path, schema_file_name: str) -> str:
    schema = read_json_file(
        repo_root / "schemas" / schema_file_name,
        "スキーマ",
        input_error=False,
    )
    schema_id = schema.get("$id") if isinstance(schema, dict) else None
    if not isinstance(schema_id, str) or not re.search(r"/[0-9]+\.[0-9]+\.[0-9]+$", schema_id):
        raise contract_failure(
            "E-CONTRACT-01",
            [f"schemas/{schema_file_name} の$idからsemverを取得できません"],
        )
    return schema_id.rsplit("/", 1)[1]


def contract_failure(code: str, problems: list[str], detail: Any = None) -> CliFailure:
    reported_problems = problems if code == "E-CONTRACT-03" else problems[:50]
    rendered = "; ".join(reported_problems)
    if code != "E-CONTRACT-03" and len(problems) > 50:
        rendered = f"先頭50件: {rendered}; 総数{len(problems)}件"
    labels = {
        "E-CONTRACT-01": "スキーマまたは内部契約に適合しません",
        "E-CONTRACT-03": "監査ファイルの配置・命名・対応関係が不整合です",
        "E-CONTRACT-04": "セット確定条件を満たしていません",
    }
    if detail is None:
        failure_detail: Any = {
            "problems": list(reported_problems),
            "total": len(problems),
        }
    elif code == "E-CONTRACT-03" and isinstance(detail, dict):
        failure_detail = {
            **detail,
            "problems": list(problems),
            "total": len(problems),
        }
    else:
        failure_detail = detail
    return CliFailure(
        code,
        f"{code} {labels[code]}: {rendered}",
        detail=failure_detail,
        remedy=REMEDIES[code],
    )


def read_json_file(path: Path, label: str, input_error: bool = True) -> Any:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise CliFailure(
            "E-INPUT-02" if input_error else "E-CONTRACT-01",
            f"{'E-INPUT-02' if input_error else 'E-CONTRACT-01'} {label}を読み取れません: {path}",
            detail={"error": str(exc), "path": str(path)},
            remedy=REMEDIES["E-INPUT-02" if input_error else "E-CONTRACT-01"],
        ) from exc
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CliFailure(
            "E-INPUT-03",
            f"E-INPUT-03 {label}がUTF-8ではありません: {path}（{exc.start}バイト目）。",
            detail={"byte_offset": exc.start, "path": str(path)},
            remedy=REMEDIES["E-INPUT-03"],
        ) from exc
    try:
        return strict_json_loads(text)
    except json.JSONDecodeError as exc:
        raise CliFailure(
            "E-INPUT-03",
            f"E-INPUT-03 {label}をJSONとしてパースできません: {path}"
            f"（{exc.lineno}行{exc.colno}列）。",
            detail={"column": exc.colno, "error": str(exc), "line": exc.lineno, "path": str(path)},
            remedy=REMEDIES["E-INPUT-03"],
        ) from exc
    except ValueError as exc:
        raise CliFailure(
            "E-INPUT-03",
            f"E-INPUT-03 {label}が標準JSONではありません: {path}（1行1列）。",
            detail={"column": 1, "error": str(exc), "line": 1, "path": str(path)},
            remedy=REMEDIES["E-INPUT-03"],
        ) from exc


def strict_utf8_json_problems(value: Any, location: str = "$") -> list[str]:
    """JSON値内の全string値・object keyのstrict UTF-8不適合を列挙する。"""

    problems: list[str] = []
    stack: list[tuple[str, str, Any]] = [("value", location, value)]
    while stack:
        value_kind, current_location, current = stack.pop()
        if isinstance(current, str):
            try:
                current.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                problems.append(
                    f"{current_location} の{value_kind}がstrict UTF-8へ符号化できません"
                    f"（文字位置{exc.start}、U+{ord(current[exc.start]):04X}）"
                )
            continue
        if isinstance(current, list):
            for index in range(len(current) - 1, -1, -1):
                stack.append(("string値", f"{current_location}[{index}]", current[index]))
            continue
        if isinstance(current, dict):
            for key, child in reversed(list(current.items())):
                key_label = json.dumps(key, ensure_ascii=True)
                stack.append(("string値", f"{current_location}[{key_label}]", child))
                stack.append(("object key", f"{current_location}[key={key_label}]", key))
    return problems


def read_canonical_audit_json(path: Path) -> tuple[Any | None, list[str]]:
    """JSON監査をstrict UTF-8・標準JSON・JS-01正準バイトで読み込む。"""

    prefix = f"review/{path.name}"
    try:
        payload = path.read_bytes()
    except OSError as exc:
        return None, [f"{prefix} を読み取れません（{type(exc).__name__}）"]
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        return None, [f"{prefix} がstrict UTF-8ではありません（{exc.start}バイト目）"]
    try:
        document = strict_json_loads(text)
    except json.JSONDecodeError as exc:
        return None, [
            f"{prefix} が標準JSONではありません（{exc.lineno}行{exc.colno}列）"
        ]
    except ValueError as exc:
        return None, [f"{prefix} が標準JSONではありません（{type(exc).__name__}）"]

    utf8_problems = strict_utf8_json_problems(document)
    if utf8_problems:
        return None, [f"{prefix} {problem}" for problem in utf8_problems]
    try:
        expected_payload = canonical_bytes(document)
    except (TypeError, ValueError, UnicodeError) as exc:
        return None, [
            f"{prefix} をJS-01正準JSONへ直列化できません（{type(exc).__name__}）"
        ]
    if payload != expected_payload:
        return None, [f"{prefix} がJS-01正準JSONのバイト列と一致しません"]
    return document, []


def validate_schema_document(
    repo_root: Path,
    path: Path,
    document: Any,
    kind: str,
) -> None:
    schema_file = SCHEMA_FILE_BY_KIND[kind]
    errors = schema_errors(document, repo_root / "schemas" / schema_file)
    if not errors:
        return
    version = schema_version(repo_root, schema_file)
    rendered = [
        f"{path.as_posix()} {error['json_pointer'] or '/'} {error['message']}"
        for error in errors
    ]
    raise CliFailure(
        "E-CONTRACT-01",
        f"E-CONTRACT-01 {path.as_posix()}が{SCHEMA_LABEL_BY_KIND[kind]}"
        f"スキーマ{version}に適合しません: {'; '.join(rendered[:50])}",
        detail={
            "errors": errors[:50],
            "path": path.as_posix(),
            "schema": SCHEMA_LABEL_BY_KIND[kind],
            "schema_version": version,
            "total_errors": len(errors),
        },
        remedy=REMEDIES["E-CONTRACT-01"],
    )


def generation_number(value: str) -> int:
    return int(value[3:])


def question_number(value: str) -> int:
    return int(value[1:])


def set_id_from_set_dir(set_dir: Path) -> str:
    """set directory名からI/Oなしでset_id候補を取得する。"""

    return set_dir.name


def validate_set_dir(repo_root: Path, set_dir: Path) -> str:
    set_id = set_id_from_set_dir(set_dir)
    if SET_ID_PATTERN.fullmatch(set_id) is None:
        raise CliFailure(
            "E-INPUT-05",
            f"E-INPUT-05 セットディレクトリ名がset_id書式ではありません: {set_dir}",
            detail={"path": str(set_dir), "set_id": set_id},
            remedy=(
                "set_idを書式例20260816-142530-k7x2に一致させたディレクトリを指定してください。"
            ),
        )
    expected_output = repo_root / "output"
    lexical_set_dir = set_dir if set_dir.is_absolute() else repo_root / set_dir
    placement_problems: list[str] = []
    if lexical_set_dir.parent != expected_output:
        placement_problems.append(
            f"--set-dirはリポジトリのoutput/直下ではありません: {set_dir}"
        )
    if expected_output.is_symlink():
        placement_problems.append("output/ がシンボリックリンクです")
    if lexical_set_dir.is_symlink():
        placement_problems.append(f"--set-dirがシンボリックリンクです: {set_dir}")
    if placement_problems:
        raise contract_failure("E-CONTRACT-03", placement_problems)

    try:
        if not lexical_set_dir.is_dir():
            raise OSError("通常ディレクトリではありません")
        next(lexical_set_dir.iterdir(), None)
        output_real = expected_output.resolve(strict=True)
        set_dir_real = lexical_set_dir.resolve(strict=True)
    except OSError as exc:
        raise CliFailure(
            "E-INPUT-02",
            f"E-INPUT-02 セットディレクトリが存在しないか読み取れません: {set_dir}",
            detail={"error": str(exc), "path": str(set_dir)},
            remedy=REMEDIES["E-INPUT-02"],
        ) from exc
    if set_dir_real.parent != output_real:
        raise contract_failure(
            "E-CONTRACT-03",
            [f"--set-dirの実体がリポジトリのoutput/直下ではありません: {set_dir}"],
        )
    return set_id


def classify_audit_name(name: str) -> tuple[str, Any]:
    regular = REGULAR_AUDIT_PATTERN.fullmatch(name)
    if regular:
        return "regular", regular.groups()
    candidate_invalid = CANDIDATE_INVALID_PATTERN.fullmatch(name)
    if candidate_invalid:
        return "candidate_invalid", candidate_invalid.groups()
    review_invalid = REVIEW_INVALID_PATTERN.fullmatch(name)
    if review_invalid:
        return "review_invalid", review_invalid.groups()
    set_check = SET_CHECK_PATTERN.fullmatch(name)
    if set_check:
        return "set_check", set_check.groups()
    slot_outcome = SLOT_OUTCOME_PATTERN.fullmatch(name)
    if slot_outcome:
        return "slot_outcome", slot_outcome.groups()
    if name == FINAL_SET_CHECK_NAME:
        return "final_set_check", None
    if CODEX_WORK_PATTERN.fullmatch(name):
        return "adapter_work", None
    return "invalid", None


def validate_invalid_audit(path: Path) -> list[str]:
    """AUD-09の3形式を検証し、不適合理由をファイル名付きで返す。"""

    prefix = f"review/{path.name}"
    try:
        payload = path.read_bytes()
    except OSError as exc:
        return [f"{prefix} を読み取れません: {exc}"]
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [f"{prefix} がstrict UTF-8ではありません（{exc.start}バイト目）"]

    try:
        document = strict_json_loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        return [f"{prefix} がAUD-09の標準JSONではありません: {exc}"]
    if not isinstance(document, dict):
        return [f"{prefix} のAUD-09トップレベルがobjectではありません"]
    try:
        if payload != canonical_bytes(document):
            return [f"{prefix} がAUD-09のJS-01正準JSONではありません"]
    except (TypeError, ValueError, UnicodeError) as exc:
        return [f"{prefix} をAUD-09のJS-01正準JSONへ直列化できません: {exc}"]

    if document.get("audit_format") != INVALID_AUDIT_FORMAT:
        return [f"{prefix} のaudit_formatが{INVALID_AUDIT_FORMAT!r}ではありません"]
    kind = document.get("kind")
    if not isinstance(kind, str) or kind not in INVALID_AUDIT_KEYS:
        return [f"{prefix} のkindがAUD-09の3種ではありません"]
    expected_keys = INVALID_AUDIT_KEYS[kind]
    actual_keys = set(document)
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        parts = []
        if missing:
            parts.append(f"必須フィールド欠落: {', '.join(missing)}")
        if extra:
            parts.append(f"未定義フィールド: {', '.join(extra)}")
        return [f"{prefix} の{kind}固定キーが不正です（{'; '.join(parts)}）"]

    def validate_base64(field: str, allow_empty: bool) -> list[str]:
        value = document[field]
        if not isinstance(value, str):
            return [f"{prefix} の{field}がstringではありません"]
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as exc:
            return [f"{prefix} の{field}がRFC 4648標準Base64ではありません: {exc}"]
        if base64.b64encode(decoded).decode("ascii") != value:
            return [f"{prefix} の{field}が正準Base64ではありません"]
        if not allow_empty and not decoded:
            return [f"{prefix} の{field}が空バイト列です"]
        return []

    if kind == "validation_failure":
        base64_problems = validate_base64("raw_output_base64", allow_empty=False)
        if base64_problems:
            return base64_problems
        diagnostic = document["diagnostic"]
        if not isinstance(diagnostic, str) or not diagnostic.strip():
            return [f"{prefix} のdiagnosticが非空UTF-8文字列ではありません"]
    elif kind == "utf8_encode_failure":
        for field in ("reason", "position"):
            value = document[field]
            if not isinstance(value, str) or not value.strip():
                return [f"{prefix} の{field}が非空UTF-8文字列ではありません"]
    else:
        exit_code = document["exit_code"]
        if exit_code is not None and (
            isinstance(exit_code, bool) or not isinstance(exit_code, int)
        ):
            return [f"{prefix} のexit_codeがintegerまたはnullではありません"]
        base64_problems = validate_base64("stderr_base64", allow_empty=True)
        if base64_problems:
            return base64_problems
    return []


def validate_slot_outcome(
    path: Path,
    document: Any,
    set_id: str,
    file_slot_id: str,
) -> list[str]:
    prefix = f"review/{path.name}"
    if not isinstance(document, dict):
        return [f"{prefix} のトップレベルがobjectではありません"]
    problems: list[str] = []
    actual_keys = set(document)
    if actual_keys != SLOT_OUTCOME_KEYS:
        missing = sorted(SLOT_OUTCOME_KEYS - actual_keys)
        extra = sorted(actual_keys - SLOT_OUTCOME_KEYS)
        if missing:
            problems.append(f"{prefix} の必須フィールド欠落: {', '.join(missing)}")
        if extra:
            problems.append(f"{prefix} の未定義フィールド: {', '.join(extra)}")
        return problems

    if document["set_id"] != set_id:
        problems.append(f"{prefix} のset_idがディレクトリ名と一致しません")
    slot_id = document["slot_question_id"]
    if not isinstance(slot_id, str) or QUESTION_ID_PATTERN.fullmatch(slot_id) is None:
        problems.append(f"{prefix} のslot_question_idがq01〜q20ではありません")
    elif slot_id != file_slot_id:
        problems.append(f"{prefix} のslot_question_idがファイル名と一致しません")

    status = document["status"]
    if not isinstance(status, str) or status not in {"accepted", "reduced"}:
        problems.append(f"{prefix} のstatusがaccepted/reducedではありません")
    attempted = document["attempted_question_ids"]
    attempted_valid = (
        isinstance(attempted, list)
        and bool(attempted)
        and all(
            isinstance(qid, str) and QUESTION_ID_PATTERN.fullmatch(qid) is not None
            for qid in attempted
        )
    )
    if not attempted_valid:
        problems.append(f"{prefix} のattempted_question_idsがq01〜q20の非空配列ではありません")
    elif len(set(attempted)) != len(attempted):
        problems.append(f"{prefix} のattempted_question_idsが一意ではありません")
    elif attempted != sorted(attempted, key=question_number):
        problems.append(f"{prefix} のattempted_question_idsが割当順の昇順ではありません")
    elif isinstance(slot_id, str) and attempted[0] != slot_id:
        problems.append(f"{prefix} の先頭試行IDがslot_question_idではありません")

    accepted_id = document["accepted_question_id"]
    teacher_decision = document["teacher_decision"]
    if status == "accepted":
        if not attempted_valid or accepted_id != attempted[-1]:
            problems.append(f"{prefix} のaccepted_question_idが最終試行IDではありません")
        if teacher_decision is not None:
            problems.append(f"{prefix} のacceptedでteacher_decisionがnullではありません")
    elif status == "reduced":
        if accepted_id is not None:
            problems.append(f"{prefix} のreducedでaccepted_question_idがnullではありません")
        if teacher_decision != "reduce":
            problems.append(f"{prefix} のreducedでteacher_decisionがreduceではありません")
    return problems


def load_audit_state(
    repo_root: Path,
    set_dir: Path,
    data_version: str,
    generation_max: int,
    limits: dict[str, Any],
    proper_nouns: list[str],
) -> dict[str, Any]:
    set_id = validate_set_dir(repo_root, set_dir)
    review_dir = set_dir / "review"
    if review_dir.is_symlink():
        raise contract_failure(
            "E-CONTRACT-03",
            ["review/ ディレクトリがシンボリックリンクです"],
        )
    if not review_dir.is_dir():
        raise contract_failure(
            "E-CONTRACT-03",
            ["review/ ディレクトリが存在しません"],
            {"missing": ["review/"]},
        )

    attempts: dict[tuple[str, str], dict[str, Any]] = defaultdict(dict)
    candidate_invalids: dict[tuple[str, str], set[int]] = defaultdict(set)
    review_invalids: dict[tuple[str, str], set[int]] = defaultdict(set)
    set_checks: dict[tuple[str, str], dict[str, Any]] = {}
    slot_outcomes: dict[str, dict[str, Any]] = {}
    final_report = None
    placement_problems: list[str] = []

    try:
        children = sorted(review_dir.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise CliFailure(
            "E-INPUT-02",
            f"E-INPUT-02 reviewディレクトリを読み取れません: {review_dir}",
            detail={"error": str(exc), "path": str(review_dir)},
            remedy=REMEDIES["E-INPUT-02"],
        ) from exc

    for path in children:
        if path.is_symlink() or not path.is_file():
            placement_problems.append(f"review/{path.name} は通常ファイルではありません")
            continue
        category, groups = classify_audit_name(path.name)
        if category == "invalid":
            placement_problems.append(f"review/{path.name} は監査命名規則に一致しません")
            continue
        generation = None
        if category in {"regular", "candidate_invalid", "review_invalid", "set_check"}:
            generation = groups[1]
        if generation is not None and generation_number(generation) > generation_max:
            placement_problems.append(
                f"review/{path.name} の世代がgeneration_max={generation_max}を超えています"
            )
            continue
        if category == "candidate_invalid":
            qid, generation, index = groups
            invalid_problems = validate_invalid_audit(path)
            if invalid_problems:
                placement_problems.extend(invalid_problems)
                continue
            candidate_invalids[(qid, generation)].add(int(index))
            continue
        if category == "review_invalid":
            qid, generation, index = groups
            invalid_problems = validate_invalid_audit(path)
            if invalid_problems:
                placement_problems.extend(invalid_problems)
                continue
            review_invalids[(qid, generation)].add(int(index))
            continue
        if category == "adapter_work":
            continue

        if category == "slot_outcome":
            file_slot_id = groups[0]
            document, audit_problems = read_canonical_audit_json(path)
            if audit_problems:
                placement_problems.extend(audit_problems)
                continue
            placement_problems.extend(
                validate_slot_outcome(path, document, set_id, file_slot_id)
            )
            slot_outcomes[file_slot_id] = document
            continue

        kind = "set_check" if category in {"set_check", "final_set_check"} else groups[2]
        document, audit_problems = read_canonical_audit_json(path)
        if audit_problems:
            placement_problems.extend(audit_problems)
            continue
        validate_schema_document(repo_root, path, document, kind)
        if category == "regular":
            qid, generation, regular_kind = groups
            attempts[(qid, generation)][regular_kind] = document
            attempts[(qid, generation)].setdefault("paths", {})[regular_kind] = path
        elif category == "set_check":
            qid, generation = groups
            set_checks[(qid, generation)] = document
        else:
            final_report = document

    if placement_problems:
        raise contract_failure("E-CONTRACT-03", placement_problems)

    required_kinds = {"candidate", "machine", "request", "review"}
    all_attempt_keys = set(attempts) | set(candidate_invalids) | set(review_invalids)
    relation_problems: list[str] = []
    complete_attempts: dict[tuple[str, str], dict[str, Any]] = {}
    for key in sorted(all_attempt_keys, key=lambda item: (question_number(item[0]), generation_number(item[1]))):
        qid, generation = key
        docs = attempts.get(key, {})
        present = set(docs) & required_kinds
        candidate_invalid_indexes = candidate_invalids.get(key, set())
        review_invalid_indexes = review_invalids.get(key, set())
        if candidate_invalid_indexes not in (set(), {1}, {1, 2}):
            relation_problems.append(f"{qid}.{generation} のcandidate.invalid連番が不正です")
        if review_invalid_indexes not in (set(), {1}, {1, 2}, {1, 2, 3}):
            relation_problems.append(f"{qid}.{generation} のreview.invalid連番が不正です")
        if 2 in candidate_invalid_indexes and present:
            relation_problems.append(
                f"{qid}.{generation} はcandidate.invalid2後に正規監査ファイルが存在します"
            )
        if 3 in review_invalid_indexes and "review" in present:
            relation_problems.append(
                f"{qid}.{generation} はreview.invalid3後にreview.jsonが存在します"
            )
        if present:
            missing = required_kinds - present
            for kind in sorted(missing):
                relation_problems.append(f"review/{qid}.{generation}.{kind}.json が欠落しています")
        if present == required_kinds:
            complete_attempts[key] = docs
        if review_invalid_indexes and not {"candidate", "machine", "request"}.issubset(present):
            relation_problems.append(
                f"{qid}.{generation} のreview.invalidに対応するcandidate/machine/requestが欠落しています"
            )

    for key, report in sorted(set_checks.items()):
        qid, generation = key
        if key not in complete_attempts:
            relation_problems.append(
                f"review/set_check.{qid}.{generation}.json に対応する完全な世代監査がありません"
            )
            continue
        if (
            report.get("scope") != "set"
            or report.get("set_id") != set_id
            or report.get("target_question_id") != qid
            or qid not in report.get("checked_question_ids", [])
        ):
            relation_problems.append(
                f"review/set_check.{qid}.{generation}.json の識別情報がファイル名と一致しません"
            )
        if report.get("data_version") != data_version:
            relation_problems.append(
                f"review/set_check.{qid}.{generation}.json のdata_versionが現在値と一致しません"
            )
        attempt = complete_attempts.get(key)
        if attempt is not None and (
            attempt["machine"].get("verdict") != "pass"
            or attempt["review"].get("verdict") != "pass"
        ):
            relation_problems.append(
                f"review/set_check.{qid}.{generation}.json にmachine/review両方passの世代が対応していません"
            )

    if final_report is not None:
        if (
            final_report.get("scope") != "set"
            or final_report.get("set_id") != set_id
            or final_report.get("target_question_id") is not None
            or final_report.get("data_version") != data_version
        ):
            relation_problems.append("review/set_check.final.json の識別情報が不正です")

    for key, docs in complete_attempts.items():
        qid, generation = key
        candidate = docs["candidate"]
        machine = docs["machine"]
        request = docs["request"]
        review = docs["review"]
        if candidate.get("question_id") != qid:
            relation_problems.append(f"{qid}.{generation}.candidate.json のquestion_idが不一致です")
        if any(
            document.get("set_id") != set_id
            or document.get("question_id") != qid
            or document.get("generation") != generation
            for document in (machine, request, review)
        ):
            relation_problems.append(f"{qid}.{generation} のset_id/question_id/generationが不一致です")
        if machine.get("scope") != "question" or machine.get("data_version") != data_version:
            relation_problems.append(f"{qid}.{generation}.machine.json のscope/data_versionが不一致です")
        if machine.get("format") != candidate.get("format") or machine.get("level") != candidate.get("level"):
            relation_problems.append(f"{qid}.{generation} のcandidateとmachineの条件が不一致です")
        if (
            request.get("format") != candidate.get("format")
            or request.get("level") != candidate.get("level")
            or request.get("target_ref") != candidate.get("target", {}).get("ref")
            or request.get("candidate") != candidate
            or request.get("machine_report") != machine
        ):
            relation_problems.append(f"{qid}.{generation}.request.json の封筒内容が監査正本と不一致です")
        format_value = candidate["format"]
        level_value = candidate["level"]["value"]
        cefr_band = level_value if format_value in VOCAB_FORMATS else level_value.split(".", 1)[0]
        expected_level_limits = {
            "vocabulary_level_max": cefr_band,
            "grammar_intro_level_max": (
                CEFR_CEILING[cefr_band]
                if format_value in VOCAB_FORMATS
                else level_value
            ),
        }
        if format_value in VOCAB_FORMATS:
            explanation_char_limit = None
        elif format_value in BRIEF_EXPLANATION_FORMATS:
            explanation_char_limit = limits["explanation_char_limits"]["brief"]
        else:
            explanation_char_limit = limits["explanation_char_limits"]["detailed"]
        expected_constraints = {
            "limits": {
                "sentence_word_limit": limits["sentence_word_limits"][cefr_band],
                "explanation_char_limit": explanation_char_limit,
            },
            "proper_nouns": proper_nouns,
        }
        if request.get("level_limits") != expected_level_limits:
            relation_problems.append(
                f"{qid}.{generation}.request.json のlevel_limitsがformat/levelからの導出値と不一致です"
            )
        constraints = request.get("constraints_snapshot", {})
        if (
            constraints.get("limits") != expected_constraints["limits"]
            or constraints.get("proper_nouns") != expected_constraints["proper_nouns"]
        ):
            relation_problems.append(
                f"{qid}.{generation}.request.json のconstraints_snapshotが設定スナップショットと不一致です"
            )
        if tuple(request.get("readable_resources", [])) != READABLE_RESOURCES:
            relation_problems.append(f"{qid}.{generation}.request.json の読み取り許可一覧がRC-10と不一致です")
        if (machine.get("verdict") == "pass") != (len(machine.get("violations", [])) == 0):
            relation_problems.append(f"{qid}.{generation}.machine.json のverdictとviolationsが不一致です")

    if relation_problems:
        raise contract_failure("E-CONTRACT-03", relation_problems)

    return {
        "attempts": complete_attempts,
        "candidate_invalids": dict(candidate_invalids),
        "final_report": final_report,
        "review_invalids": dict(review_invalids),
        "set_checks": set_checks,
        "set_id": set_id,
        "slot_outcomes": slot_outcomes,
    }


def validate_request_topics(
    state: dict[str, Any],
    expected_topic: str | None,
) -> None:
    problems = []
    for (qid, generation), attempt in sorted(
        state["attempts"].items(),
        key=lambda item: (question_number(item[0][0]), generation_number(item[0][1])),
    ):
        actual_topic = attempt["request"]["constraints_snapshot"]["topic"]
        if actual_topic != expected_topic:
            problems.append(
                f"{qid}.{generation}.request.json のtopicがFIN-01メタデータと不一致です"
            )
    if problems:
        raise contract_failure("E-CONTRACT-03", problems)


def generation_terminal_status(
    state: dict[str, Any],
    key: tuple[str, str],
) -> str:
    if 2 in state["candidate_invalids"].get(key, set()):
        return "consumed"
    attempt = state["attempts"].get(key)
    if attempt is None:
        return "incomplete"
    if (
        attempt["machine"].get("verdict") == "fail"
        or attempt["review"].get("verdict") == "fail"
    ):
        return "consumed"
    set_report = state["set_checks"].get(key)
    if set_report is None:
        return "incomplete"
    return "accepted" if set_report.get("verdict") == "pass" else "consumed"


def validate_terminal_outcomes(
    state: dict[str, Any],
    requested_count: int,
    declared_ids: list[str],
    generation_max: int,
) -> None:
    expected_slots = {f"q{number:02d}" for number in range(1, requested_count + 1)}
    actual_slots = set(state["slot_outcomes"])
    unexpected_slots = sorted(actual_slots - expected_slots, key=question_number)
    if unexpected_slots:
        raise contract_failure(
            "E-CONTRACT-03",
            [f"要求スロット外の終端監査があります: {unexpected_slots}"],
        )

    missing_slots = sorted(expected_slots - actual_slots, key=question_number)
    if missing_slots:
        raise contract_failure(
            "E-CONTRACT-04",
            [f"要求スロットの終端監査が欠落しています: {missing_slots}"],
            {"actual_slots": sorted(actual_slots), "expected_slots": sorted(expected_slots)},
        )

    listed_owner: dict[str, str] = {}
    relation_problems: list[str] = []
    for slot_id in sorted(actual_slots, key=question_number):
        outcome = state["slot_outcomes"][slot_id]
        for qid in outcome["attempted_question_ids"]:
            previous = listed_owner.get(qid)
            if previous is not None:
                relation_problems.append(
                    f"{qid} が複数スロットに属します: {previous}, {slot_id}"
                )
            else:
                listed_owner[qid] = slot_id

    audit_keys = (
        set(state["attempts"])
        | set(state["candidate_invalids"])
        | set(state["review_invalids"])
        | set(state["set_checks"])
    )
    audited_ids = {qid for qid, _generation in audit_keys}
    listed_ids = set(listed_owner)
    if audited_ids != listed_ids:
        unrecorded = sorted(audited_ids - listed_ids, key=question_number)
        unaudited = sorted(listed_ids - audited_ids, key=question_number)
        if unrecorded:
            relation_problems.append(f"終端監査に属さない試行IDがあります: {unrecorded}")
        if unaudited:
            relation_problems.append(f"世代監査が存在しない試行IDがあります: {unaudited}")
    if audited_ids:
        maximum_id = max(question_number(qid) for qid in audited_ids)
        expected_ids = {f"q{number:02d}" for number in range(1, maximum_id + 1)}
        if audited_ids != expected_ids:
            relation_problems.append(
                f"試行question_idがq01から連続していません: {sorted(audited_ids, key=question_number)}"
            )
    if relation_problems:
        raise contract_failure("E-CONTRACT-03", relation_problems)

    attempted_limit = 2 * requested_count
    if len(listed_ids) > attempted_limit:
        raise contract_failure(
            "E-CONTRACT-04",
            [
                "終端監査の一意な試行question_id数が"
                f"2 * requested_count={attempted_limit}を超えています: {len(listed_ids)}"
            ],
            {
                "attempted_question_ids": sorted(listed_ids, key=question_number),
                "attempted_question_limit": attempted_limit,
                "requested_count": requested_count,
            },
        )

    terminal_problems: list[str] = []
    accepted_by_outcome: list[str] = []
    for slot_id in sorted(actual_slots, key=question_number):
        outcome = state["slot_outcomes"][slot_id]
        accepted_id = outcome["accepted_question_id"]
        if accepted_id is not None:
            accepted_by_outcome.append(accepted_id)
        for qid in outcome["attempted_question_ids"]:
            generations = sorted(
                {generation_number(generation) for audit_qid, generation in audit_keys if audit_qid == qid}
            )
            if not generations:
                terminal_problems.append(f"{qid} に世代監査がありません")
                continue
            expected_generations = list(range(1, generations[-1] + 1))
            if generations != expected_generations:
                terminal_problems.append(f"{qid} の世代がgen1から連続していません: {generations}")
                continue
            statuses = [
                generation_terminal_status(state, (qid, f"gen{number}"))
                for number in generations
            ]
            if qid == accepted_id:
                if statuses[-1] != "accepted" or any(
                    status != "consumed" for status in statuses[:-1]
                ):
                    terminal_problems.append(
                        f"{qid} が消費済み世代の後のT10採用で終端していません: {statuses}"
                    )
            elif generations[-1] != generation_max or any(
                status != "consumed" for status in statuses
            ):
                terminal_problems.append(
                    f"{qid} がgeneration_max={generation_max}まで正当に消費されていません: "
                    f"世代={generations} 状態={statuses}"
                )

    accepted_by_outcome.sort(key=question_number)
    accepted_by_audit = sorted(accepted_attempts(state), key=question_number)
    if accepted_by_outcome != declared_ids or accepted_by_audit != declared_ids:
        terminal_problems.extend(
            [
                f"終端監査の採用集合={accepted_by_outcome}",
                f"監査上の合格集合={accepted_by_audit}",
                f"宣言集合={declared_ids}",
            ]
        )
    if terminal_problems:
        raise contract_failure(
            "E-CONTRACT-04",
            terminal_problems,
            {
                "accepted_by_audit": accepted_by_audit,
                "accepted_by_outcome": accepted_by_outcome,
                "declared_question_ids": declared_ids,
                "generation_max": generation_max,
            },
        )


def accepted_attempts(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    accepted: dict[str, dict[str, Any]] = {}
    for key, attempt in sorted(
        state["attempts"].items(),
        key=lambda item: (question_number(item[0][0]), generation_number(item[0][1])),
    ):
        qid, generation = key
        set_report = state["set_checks"].get(key)
        if (
            attempt["machine"].get("verdict") == "pass"
            and attempt["review"].get("verdict") == "pass"
            and set_report is not None
            and set_report.get("verdict") == "pass"
        ):
            current = accepted.get(qid)
            if current is None or generation_number(generation) > generation_number(current["generation"]):
                accepted[qid] = {**attempt, "generation": generation, "set_report": set_report}
    return accepted


def select_attempts_for_check(
    state: dict[str, Any],
    target_question_id: str | None,
) -> list[dict[str, Any]]:
    accepted = accepted_attempts(state)
    selected = dict(accepted)
    if target_question_id is not None:
        target_attempts = []
        for (qid, generation), attempt in state["attempts"].items():
            if (
                qid == target_question_id
                and attempt["machine"].get("verdict") == "pass"
                and attempt["review"].get("verdict") == "pass"
            ):
                target_attempts.append((generation_number(generation), generation, attempt))
        if not target_attempts:
            raise contract_failure(
                "E-CONTRACT-03",
                [f"{target_question_id} にmachine/reviewともpassの世代がありません"],
            )
        _number, generation, attempt = max(target_attempts, key=lambda item: item[0])
        selected[target_question_id] = {**attempt, "generation": generation}
    elif not selected:
        raise contract_failure("E-CONTRACT-03", ["合格世代を持つ問題が1問もありません"])

    return [
        {"question_id": qid, **selected[qid]}
        for qid in sorted(selected, key=question_number)
    ]


def normalize_sentence(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).lower().split())


def is_sentence_text_field(format_value: str, field: Any) -> bool:
    if not isinstance(field, str):
        return False
    if field in SENTENCE_FIELDS_BY_FORMAT.get(format_value, set()):
        return True
    return (
        format_value == "grammar_mcq"
        and GRAMMAR_MCQ_CHOICE_SENTENCE_PATTERN.fullmatch(field) is not None
    )


def set_violation(code: str, location: str, evidence: str, suggestion: str) -> dict[str, Any]:
    return {
        "actual_level": None,
        "code": code,
        "evidence": evidence,
        "expected_level": None,
        "location": location,
        "suggestion": suggestion,
    }


def build_set_report(
    selected: list[dict[str, Any]],
    set_id: str,
    data_version: str,
    schema_version_value: str,
    distractor_reuse_max: int,
    target_question_id: str | None,
) -> dict[str, Any]:
    target_to_questions: dict[str, set[str]] = defaultdict(set)
    sentence_to_questions: dict[str, set[str]] = defaultdict(set)
    sentence_examples: dict[str, set[str]] = defaultdict(set)
    distractor_to_questions: dict[str, set[str]] = defaultdict(set)

    for item in selected:
        qid = item["question_id"]
        candidate = item["candidate"]
        machine = item["machine"]
        target_to_questions[candidate["target"]["ref"]].add(qid)
        for text_record in machine.get("stats", {}).get("texts", []):
            if not is_sentence_text_field(candidate["format"], text_record.get("field")):
                continue
            text = text_record.get("text")
            if isinstance(text, str):
                normalized = normalize_sentence(text)
                sentence_to_questions[normalized].add(qid)
                sentence_examples[normalized].add(text)
        if candidate["format"] in {"vocab_mcq_en2ja", "vocab_mcq_ja2en"}:
            for choice in candidate["body"]["choices"]:
                if not choice["is_correct"]:
                    distractor_to_questions[choice["anchor"]["entry_id"]].add(qid)

    violations: list[dict[str, Any]] = []
    for target_ref in sorted(target_to_questions):
        qids = sorted(target_to_questions[target_ref], key=question_number)
        if len(qids) > 1:
            violations.append(
                set_violation(
                    "V-SET-01",
                    f"questions[{', '.join(qids)}].target.ref",
                    f"対象ID {target_ref} が{len(qids)}問で重複しています。",
                    "重複対象を、同じ指定レベルの未使用対象へ差し替えてください。",
                )
            )
    for normalized in sorted(sentence_to_questions):
        qids = sorted(sentence_to_questions[normalized], key=question_number)
        if len(qids) > 1:
            example = sorted(sentence_examples[normalized])[0]
            violations.append(
                set_violation(
                    "V-SET-02",
                    f"questions[{', '.join(qids)}] の英文検査対象",
                    f"正規化後に同一となる例文が{len(qids)}問で使われています: {example!r}",
                    "意味を保ったまま、他問と一致しない新しい例文へ差し替えてください。",
                )
            )
    for entry_id in sorted(distractor_to_questions):
        qids = sorted(distractor_to_questions[entry_id], key=question_number)
        if len(qids) > distractor_reuse_max:
            violations.append(
                set_violation(
                    "V-SET-03",
                    f"questions[{', '.join(qids)}].body.choices[].anchor.entry_id",
                    f"誤答由来ID {entry_id} が{len(qids)}問で使われ、上限{distractor_reuse_max}問を超えています。",
                    "上限を超えた問の誤答を、未使用または使用回数の少ない適格語へ差し替えてください。",
                )
            )

    return {
        "checked_question_ids": [item["question_id"] for item in selected],
        "data_version": data_version,
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "schema_version": schema_version_value,
        "scope": "set",
        "set_id": set_id,
        "target_question_id": target_question_id,
        "verdict": "fail" if violations else "pass",
        "violations": violations,
        "warnings": [],
    }


def report_without_generated_at(report: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(report)
    value.pop("generated_at", None)
    return value


def derive_answer_tokens(answer_sentence: str) -> list[str]:
    normalized = unicodedata.normalize("NFC", answer_sentence).replace("\u2019", "'")
    pieces = re.split(r"[ \t]+", normalized)
    punctuation = str.maketrans("", "", ".,?!;:")
    return [piece.translate(punctuation).lower() for piece in pieces if piece.translate(punctuation)]


def build_attribution(meta: dict[str, Any]) -> dict[str, Any]:
    by_role = {source["role"]: source for source in meta["sources"]}
    wordlist = by_role["wordlist"]
    grammar = by_role["grammar_profile"]

    def date_parts(source: dict[str, Any]) -> tuple[str, str]:
        date = source["retrieved_date"]
        return date[:4], str(int(date[5:7]))

    word_year, word_month = date_parts(wordlist)
    grammar_year, grammar_month = date_parts(grammar)
    return {
        "grammar_profile": {
            "citation_en": (
                f"The CEFR-J Grammar Profile ({grammar['version_label']}). Compiled by Yukio Tono, "
                f"Tokyo University of Foreign Studies. Retrieved from {grammar['url']} on "
                f"{grammar['retrieved_date']}."
            ),
            "citation_ja": (
                f"『CEFR-J Grammar Profile』（{grammar['version_label']}版） "
                f"東京外国語大学投野由紀夫研究室.（URL: {grammar['url']} より"
                f"{grammar_year}年{grammar_month}月ダウンロード）"
            ),
            "retrieved_date": grammar["retrieved_date"],
            "url": grammar["url"],
            "version_label": grammar["version_label"],
        },
        "wordlist": {
            "citation_en": (
                f"The CEFR-J Wordlist Version {wordlist['version_label']}. Compiled by Yukio Tono, "
                f"Tokyo University of Foreign Studies. Retrieved from {wordlist['url']} on "
                f"{wordlist['retrieved_date']}."
            ),
            "citation_ja": (
                f"『CEFR-J Wordlist Version {wordlist['version_label']}』 "
                f"東京外国語大学投野由紀夫研究室.（URL: {wordlist['url']} より"
                f"{word_year}年{word_month}月ダウンロード）"
            ),
            "retrieved_date": wordlist["retrieved_date"],
            "url": wordlist["url"],
            "version_label": wordlist["version_label"],
        },
    }


def build_question_for_set(attempt: dict[str, Any]) -> dict[str, Any]:
    candidate = copy.deepcopy(attempt["candidate"])
    qid = candidate["question_id"]
    generation = attempt["generation"]
    candidate["provenance"] = {
        "candidate_ref": f"review/{qid}.{generation}.candidate.json",
        "generation": generation,
        "machine_report_ref": f"review/{qid}.{generation}.machine.json",
        "review_ref": f"review/{qid}.{generation}.review.json",
    }
    if candidate["format"] == "grammar_reorder":
        answer_tokens = derive_answer_tokens(candidate["body"]["answer_sentence"])
        shuffled = candidate["body"]["tokens_shuffled"]
        if Counter(answer_tokens) != Counter(shuffled) or answer_tokens == shuffled:
            raise contract_failure(
                "E-CONTRACT-01",
                [
                    f"{qid} のanswer_tokens導出結果がtokens_shuffledとFIN-05の整合条件を満たしません"
                ],
                {"answer_tokens": answer_tokens, "question_id": qid, "tokens_shuffled": shuffled},
            )
        candidate["body"]["answer_tokens"] = answer_tokens
    return candidate
