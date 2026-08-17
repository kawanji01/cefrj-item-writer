#!/usr/bin/env python3
"""合格済み監査からset.jsonを組み立て、原子的に確定する。"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from build_normalized import CliFailure, emit_json, schema_errors, strict_json_loads
from lookup import load_validated_resources
from set_support import (
    CEFRJ_VALUES,
    CEFR_VALUES,
    FORMAT_VALUES,
    GRAMMAR_FORMATS,
    QUESTION_ID_PATTERN,
    VOCAB_FORMATS,
    accepted_attempts,
    build_attribution,
    build_question_for_set,
    build_set_report,
    canonical_bytes,
    contract_failure,
    load_audit_state,
    question_number,
    report_without_generated_at,
    schema_version,
    set_id_from_set_dir,
    validate_request_topics,
    validate_terminal_outcomes,
    validate_set_dir,
)


CREATED_AT_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?P<offset>Z|(?P<offset_sign>[+-])(?P<offset_hour>[0-9]{2}):(?P<offset_minute>[0-9]{2}))$"
)
METADATA_KEYS = {
    "config_snapshot",
    "created_at",
    "final_question_ids",
    "format",
    "level",
    "mode",
    "model",
    "preferred_proper_nouns",
    "requested_count",
    "set_id",
    "tool",
    "topic",
}
REMEDIES = {
    "E-INPUT-01": "python scripts/finalize_set.py --help の日本語ヘルプを参照して引数を修正してください。",
    "E-INPUT-03": "stdinへUTF-8の標準JSONでFIN-01のセットメタデータを渡してください。",
    "E-DATA-08": (
        "進行中セットの監査を保持したまま中止し、設定変更後にpython scripts/doctor.pyを"
        "実行して新しいset_idで最初から作成してください。"
    ),
    "E-CONTRACT-05": (
        "既存セットを保持したまま、新しいset_idで新規セットとして実行してください。"
    ),
    "E-ENV-05": "セットディレクトリの権限と空き容量を確認してください。",
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


class FinalizeArgumentParser(argparse.ArgumentParser):
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
        unknown = "unrecognized arguments:"
        required = "the following arguments are required:"
        if message.startswith(unknown):
            translated = f"未知の引数です:{message[len(unknown):]}"
        elif message.startswith(required):
            translated = f"必須引数が欠落しています:{message[len(required):]}"
        else:
            translated = f"引数の書式が不正です: {message}"
        raise CliFailure(
            "E-INPUT-01",
            f"E-INPUT-01 finalize_set.pyの引数が不正です: {translated}",
            detail={"parser_message": message},
            remedy=REMEDIES["E-INPUT-01"],
        )


def make_parser() -> FinalizeArgumentParser:
    parser = FinalizeArgumentParser(description="合格済み監査からset.jsonを原子的に確定します。")
    parser.add_argument("--set-dir", required=True, help="output/<set_id> ディレクトリ。")
    return parser


def read_stdin_metadata() -> Any:
    stream = getattr(sys.stdin, "buffer", sys.stdin)
    try:
        payload = stream.read()
    except OSError as exc:
        raise CliFailure(
            "E-INPUT-03",
            "E-INPUT-03 stdinのセットメタデータを読み取れません（1行1列）。",
            detail={"column": 1, "error": str(exc), "line": 1, "source": "stdin"},
            remedy=REMEDIES["E-INPUT-03"],
        ) from exc
    if isinstance(payload, str):
        text = payload
    else:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CliFailure(
                "E-INPUT-03",
                "E-INPUT-03 stdinのセットメタデータがUTF-8ではありません（1行1列）。",
                detail={"byte_offset": exc.start, "column": 1, "line": 1, "source": "stdin"},
                remedy=REMEDIES["E-INPUT-03"],
            ) from exc
    try:
        return strict_json_loads(text)
    except json.JSONDecodeError as exc:
        raise CliFailure(
            "E-INPUT-03",
            f"E-INPUT-03 stdinのセットメタデータをJSONとしてパースできません"
            f"（{exc.lineno}行{exc.colno}列）。",
            detail={"column": exc.colno, "error": str(exc), "line": exc.lineno, "source": "stdin"},
            remedy=REMEDIES["E-INPUT-03"],
        ) from exc
    except ValueError as exc:
        raise CliFailure(
            "E-INPUT-03",
            "E-INPUT-03 stdinのセットメタデータが標準JSONではありません（1行1列）。",
            detail={"column": 1, "error": str(exc), "line": 1, "source": "stdin"},
            remedy=REMEDIES["E-INPUT-03"],
        ) from exc


def strict_utf8_problems(value: Any, path: str = "$") -> list[str]:
    """JSON互換値に含まれる全string/keyのstrict UTF-8不適合を列挙する。"""

    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            return [f"{path} がstrict UTF-8へ符号化できません（文字位置{exc.start}）"]
        return []
    if isinstance(value, list):
        problems: list[str] = []
        for index, item in enumerate(value):
            problems.extend(strict_utf8_problems(item, f"{path}[{index}]"))
        return problems
    if isinstance(value, dict):
        problems = []
        keys = sorted(value, key=lambda item: json.dumps(item, ensure_ascii=True))
        for index, key in enumerate(keys):
            if isinstance(key, str):
                try:
                    key.encode("utf-8")
                except UnicodeEncodeError as exc:
                    problems.append(
                        f"{path} のobjectキー{index + 1}がstrict UTF-8へ符号化できません"
                        f"（文字位置{exc.start}）"
                    )
                key_path = f"{path}[{json.dumps(key, ensure_ascii=True)}]"
            else:
                key_path = f"{path}[object-key-{index + 1}]"
            problems.extend(strict_utf8_problems(value[key], key_path))
        return problems
    return []


def validate_metadata(
    metadata: Any,
    set_id: str,
    repo_root: Path,
) -> dict[str, Any]:
    problems: list[str] = []
    if not isinstance(metadata, dict):
        raise contract_failure("E-CONTRACT-01", ["FIN-01メタデータのトップレベルがobjectではありません"])
    utf8_problems = strict_utf8_problems(metadata)
    if utf8_problems:
        raise contract_failure("E-CONTRACT-01", utf8_problems)
    missing = METADATA_KEYS - set(metadata)
    extra = set(metadata) - METADATA_KEYS
    if missing:
        problems.append(f"必須フィールド欠落: {', '.join(sorted(missing))}")
    if extra:
        problems.append(f"未定義フィールド: {', '.join(sorted(extra))}")
    if missing:
        raise contract_failure("E-CONTRACT-01", problems)

    metadata_set_id = metadata["set_id"]
    if not isinstance(metadata_set_id, str):
        problems.append("set_idがstringではありません")
    elif metadata_set_id != set_id:
        problems.append(f"set_idが--set-dirと不一致です: 宣言{metadata['set_id']!r} 実体{set_id!r}")
    format_value = metadata["format"]
    format_valid = isinstance(format_value, str) and format_value in FORMAT_VALUES
    if not isinstance(format_value, str):
        problems.append("formatがstringではありません")
    elif not format_valid:
        problems.append(f"formatが9形式ではありません: {format_value!r}")
    level = metadata["level"]
    if not isinstance(level, dict) or set(level) != {"scale", "value"}:
        problems.append("levelはscale/valueだけを持つobjectではありません")
    else:
        level_scale = level["scale"]
        level_value = level["value"]
        if not isinstance(level_scale, str):
            problems.append("level.scaleがstringではありません")
        if not isinstance(level_value, str):
            problems.append("level.valueがstringではありません")
        if (
            format_valid
            and isinstance(level_scale, str)
            and isinstance(level_value, str)
        ):
            if format_value in VOCAB_FORMATS and not (
                level_scale == "cefr" and level_value in CEFR_VALUES
            ):
                problems.append("語彙形式のlevelがcefr A1〜B2ではありません")
            elif format_value in GRAMMAR_FORMATS and not (
                level_scale == "cefrj" and level_value in CEFRJ_VALUES
            ):
                problems.append("文法形式のlevelがcefrj 9段階ではありません")
    mode = metadata["mode"]
    if not isinstance(mode, str):
        problems.append("modeがstringではありません")
    elif mode not in {"explicit", "proposal"}:
        problems.append("modeがexplicit/proposalではありません")
    requested = metadata["requested_count"]
    if isinstance(requested, bool) or not isinstance(requested, int):
        problems.append("requested_countがintegerではありません")
    if metadata["topic"] is not None and (
        not isinstance(metadata["topic"], str) or not metadata["topic"]
    ):
        problems.append("topicが非空文字列またはnullではありません")
    created_at = metadata["created_at"]
    created_at_match = (
        CREATED_AT_PATTERN.fullmatch(created_at) if isinstance(created_at, str) else None
    )
    if created_at_match is None:
        problems.append("created_atが秒精度・タイムゾーン付きISO 8601ではありません")
    else:
        offset_is_valid = True
        if created_at_match.group("offset") != "Z":
            offset_hour = int(created_at_match.group("offset_hour"))
            offset_minute = int(created_at_match.group("offset_minute"))
            offset_is_valid = (
                offset_minute <= 59
                and offset_hour <= 14
                and (offset_hour < 14 or offset_minute == 0)
            )
            if not offset_is_valid:
                problems.append(
                    "created_atのUTCオフセットが許容範囲ではありません: "
                    "分は00〜59、絶対値は14:00以下、14時は00分だけ許可します"
                )
        if offset_is_valid:
            try:
                created_datetime = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                problems.append("created_atが実在する日時・UTCオフセットではありません")
            else:
                if created_datetime.strftime("%Y%m%d-%H%M%S") != set_id[:15]:
                    problems.append(
                        "created_atのローカル日時がset_idの日時部分と一致しません: "
                        f"created_at={created_at!r} set_id={set_id!r}"
                    )
    tool = metadata["tool"]
    if not isinstance(tool, str):
        problems.append("toolがstringではありません")
    elif tool not in {"claude_code", "codex"}:
        problems.append("toolがclaude_code/codexではありません")
    if not isinstance(metadata["model"], str) or not metadata["model"]:
        problems.append("modelが非空文字列ではありません")

    snapshot = metadata["config_snapshot"]
    if not isinstance(snapshot, dict) or set(snapshot) != {"limits", "proper_nouns"}:
        problems.append("config_snapshotがlimits/proper_nounsだけを持つobjectではありません")
    else:
        limit_errors = schema_errors(snapshot["limits"], repo_root / "schemas/config_limits.schema.json")
        problems.extend(
            f"config_snapshot.limits{error['json_pointer'] or '/'} {error['message']}"
            for error in limit_errors
        )
        proper = snapshot["proper_nouns"]
        if (
            not isinstance(proper, list)
            or not proper
            or any(not isinstance(value, str) or not value for value in proper)
            or len(set(proper)) != len(proper)
        ):
            problems.append("config_snapshot.proper_nounsが一意な非空文字列の非空配列ではありません")
        if isinstance(requested, int) and not isinstance(requested, bool):
            maximum = snapshot["limits"].get("set_question_max") if isinstance(snapshot["limits"], dict) else None
            if not isinstance(maximum, int) or not 1 <= requested <= maximum:
                problems.append(f"requested_countが1..set_question_maxではありません: {requested!r}")

    preferred = metadata["preferred_proper_nouns"]
    if (
        not isinstance(preferred, list)
        or any(not isinstance(value, str) or not value for value in preferred)
        or len(set(preferred)) != len(preferred)
    ):
        problems.append("preferred_proper_nounsが一意な非空文字列の配列ではありません")
    elif isinstance(snapshot, dict) and isinstance(snapshot.get("proper_nouns"), list):
        unknown = [value for value in preferred if value not in snapshot["proper_nouns"]]
        if unknown:
            problems.append(f"preferred_proper_nounsがallowlist外です: {', '.join(unknown)}")

    final_ids = metadata["final_question_ids"]
    if not isinstance(final_ids, list) or not final_ids:
        problems.append("final_question_idsが1件以上の配列ではありません")
    elif any(not isinstance(qid, str) or QUESTION_ID_PATTERN.fullmatch(qid) is None for qid in final_ids):
        problems.append("final_question_idsにq01〜q20以外が含まれます")
    elif len(set(final_ids)) != len(final_ids) or final_ids != sorted(final_ids, key=question_number):
        problems.append("final_question_idsが昇順・一意ではありません")
    elif isinstance(requested, int) and not isinstance(requested, bool) and len(final_ids) > requested:
        problems.append("final_question_ids件数がrequested_countを超えています")

    if problems:
        raise contract_failure("E-CONTRACT-01", problems)
    return metadata


def config_snapshot_from_resources(resources: dict[str, Any]) -> dict[str, Any]:
    return {
        "limits": resources["limits"],
        "proper_nouns": resources["proper_nouns"]["words"],
    }


def ensure_snapshot_current(metadata: dict[str, Any], resources: dict[str, Any]) -> None:
    expected = metadata["config_snapshot"]
    current = config_snapshot_from_resources(resources)
    if expected == current:
        return
    changed = []
    if expected.get("limits") != current["limits"]:
        changed.append("data/config/limits.json")
    if expected.get("proper_nouns") != current["proper_nouns"]:
        changed.append("data/config/proper_nouns.json")
    raise CliFailure(
        "E-DATA-08",
        f"E-DATA-08 セッション設定スナップショットと現在値が一致しません: {', '.join(changed)}",
        detail={"changed_files": changed, "current": current, "snapshot": expected},
        remedy=REMEDIES["E-DATA-08"],
    )


def set_path_exists(path: Path) -> bool:
    return os.path.lexists(path)


def create_exclusive_temp(set_dir: Path) -> tuple[Path, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    for _attempt in range(100):
        path = set_dir / f".set.json.tmp.{os.getpid()}.{secrets.token_hex(16)}"
        try:
            return path, os.open(path, flags, 0o600)
        except FileExistsError:
            continue
        except OSError as exc:
            raise CliFailure(
                "E-ENV-05",
                f"E-ENV-05 set.json一時ファイルを排他的に作成できません: {path} ({exc})",
                detail={"error": str(exc), "path": str(path)},
                remedy=REMEDIES["E-ENV-05"],
            ) from exc
    raise CliFailure(
        "E-ENV-05",
        f"E-ENV-05 set.json一時ファイル名を確保できません: {set_dir}",
        detail={"attempts": 100, "path": str(set_dir)},
        remedy=REMEDIES["E-ENV-05"],
    )


def remove_temp(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise CliFailure(
            "E-ENV-05",
            f"E-ENV-05 set.json一時ファイルを削除できません: {path} ({exc})",
            detail={"error": str(exc), "path": str(path)},
            remedy=REMEDIES["E-ENV-05"],
        ) from exc


def cleanup_published_temp(repo_root: Path, path: Path) -> dict[str, Any] | None:
    """公開成功後の一時リンクを削除し、失敗時は非致命警告を返す。"""

    try:
        path.unlink()
        return None
    except FileNotFoundError:
        return None
    except OSError:
        lexical_path = path if path.is_absolute() else repo_root / path
        temp_path = lexical_path.relative_to(repo_root).as_posix()
        return {
            "detail": {"temp_path": temp_path},
            "message": "set.jsonは完成しましたが一時リンクを削除できませんでした",
            "remedy": (
                "set.jsonを変更せず、権限を確認して表示された一時リンクだけを削除してください。"
                "finalize_set.pyは再実行しないでください。"
            ),
            "warning_code": "W-CLEANUP-01",
        }


def finalize(argv: list[str] | None = None) -> dict[str, Any]:
    args = make_parser().parse_args(argv)
    repo_root = Path.cwd()
    raw_metadata = read_stdin_metadata()
    set_dir = Path(args.set_dir)
    set_id = set_id_from_set_dir(set_dir)
    metadata = validate_metadata(raw_metadata, set_id, repo_root)
    resources = load_validated_resources(repo_root)
    ensure_snapshot_current(metadata, resources)
    validate_set_dir(repo_root, set_dir)

    set_path = set_dir / "set.json"
    if set_path_exists(set_path):
        raise CliFailure(
            "E-CONTRACT-05",
            f"E-CONTRACT-05 確定済みset.jsonを上書きできません: {set_path}",
            detail={"path": str(set_path)},
            remedy=REMEDIES["E-CONTRACT-05"],
        )

    generation_max = metadata["config_snapshot"]["limits"]["generation_max"]
    state = load_audit_state(
        repo_root,
        set_dir,
        resources["meta"]["data_version"],
        generation_max,
        metadata["config_snapshot"]["limits"],
        metadata["config_snapshot"]["proper_nouns"],
    )
    validate_request_topics(state, metadata["topic"])
    accepted = accepted_attempts(state)
    declared_ids = metadata["final_question_ids"]
    validate_terminal_outcomes(
        state,
        metadata["requested_count"],
        declared_ids,
        generation_max,
    )
    accepted_ids = sorted(accepted, key=question_number)
    if accepted_ids != declared_ids or not 1 <= len(accepted_ids) <= metadata["requested_count"]:
        raise contract_failure(
            "E-CONTRACT-04",
            [
                f"宣言集合={declared_ids}",
                f"監査上の合格集合={accepted_ids}",
                f"requested_count={metadata['requested_count']}",
            ],
            {
                "accepted_question_ids": accepted_ids,
                "declared_question_ids": declared_ids,
                "requested_count": metadata["requested_count"],
            },
        )

    selected = [
        {"question_id": qid, **accepted[qid]} for qid in accepted_ids
    ]
    report_version = schema_version(repo_root, "machine_report.schema.json")
    internal_report = build_set_report(
        selected,
        set_id,
        resources["meta"]["data_version"],
        report_version,
        metadata["config_snapshot"]["limits"]["distractor_reuse_max"],
        None,
    )
    final_audit = state["final_report"]
    if final_audit is None:
        raise contract_failure(
            "E-CONTRACT-03",
            ["review/set_check.final.json が欠落しています"],
        )
    if (
        final_audit.get("verdict") != "pass"
        or final_audit.get("checked_question_ids") != accepted_ids
        or report_without_generated_at(final_audit) != report_without_generated_at(internal_report)
    ):
        raise contract_failure(
            "E-CONTRACT-04",
            ["保存済み最終セット横断検査とfinalize内部再検査が一致しないかfailです"],
            {"internal_report": internal_report, "saved_report": final_audit},
        )
    if internal_report["verdict"] != "pass":
        raise contract_failure(
            "E-CONTRACT-04",
            ["finalize内部のセット横断検査がfailです"],
            {"violations": internal_report["violations"]},
        )

    questions = [build_question_for_set(accepted[qid]) for qid in accepted_ids]
    meta = resources["meta"]
    set_document = {
        "attribution": build_attribution(meta),
        "config_snapshot": metadata["config_snapshot"],
        "created_at": metadata["created_at"],
        "data_version": meta["data_version"],
        "format": metadata["format"],
        "level": metadata["level"],
        "mode": metadata["mode"],
        "model": metadata["model"],
        "preferred_proper_nouns": metadata["preferred_proper_nouns"],
        "questions": questions,
        "requested_count": metadata["requested_count"],
        "schema_version": schema_version(repo_root, "set.schema.json"),
        "set_id": set_id,
        "source_checksums": {source["file"]: source["sha256"] for source in meta["sources"]},
        "tool": metadata["tool"],
        "topic": metadata["topic"],
    }
    errors = schema_errors(set_document, repo_root / "schemas/set.schema.json")
    if errors:
        raise contract_failure(
            "E-CONTRACT-01",
            [f"{error['json_pointer'] or '/'} {error['message']}" for error in errors],
            {"errors": errors, "schema": "set", "schema_version": set_document["schema_version"]},
        )
    if [question["question_id"] for question in questions] != accepted_ids:
        raise contract_failure("E-CONTRACT-01", ["questionsがquestion_id昇順ではありません"])
    if any(question["format"] != metadata["format"] or question["level"] != metadata["level"] for question in questions):
        raise contract_failure("E-CONTRACT-01", ["setのformat/levelとquestionが一致しません"])

    try:
        set_payload = canonical_bytes(set_document)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise contract_failure(
            "E-CONTRACT-01",
            [
                "set.jsonをstrict UTF-8のJS-01正準バイト列へ直列化できません"
                f"（{type(exc).__name__}）"
            ],
            {"error_type": type(exc).__name__},
        ) from exc

    tmp_path: Path | None = None
    try:
        tmp_path, descriptor = create_exclusive_temp(set_dir)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(set_payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(tmp_path, set_path, follow_symlinks=False)
        except FileExistsError as exc:
            raise CliFailure(
                "E-CONTRACT-05",
                f"E-CONTRACT-05 set.jsonを上書きせず確定を拒否しました: {set_path}",
                detail={"path": str(set_path)},
                remedy=REMEDIES["E-CONTRACT-05"],
            ) from exc
    except CliFailure:
        if tmp_path is not None:
            remove_temp(tmp_path)
        raise
    except OSError as exc:
        if tmp_path is not None:
            remove_temp(tmp_path)
        raise CliFailure(
            "E-ENV-05",
            f"E-ENV-05 set.jsonを原子的に書き込めません: {set_path} ({exc})",
            detail={"error": str(exc), "path": str(set_path)},
            remedy=REMEDIES["E-ENV-05"],
        ) from exc
    if tmp_path is not None:
        warning = cleanup_published_temp(repo_root, tmp_path)
        if warning is not None:
            emit_json(warning, sys.stderr)

    return {
        "data_version": meta["data_version"],
        "question_count": len(questions),
        "schema_version": set_document["schema_version"],
        "set_id": set_id,
        "set_json_path": f"output/{set_id}/set.json",
    }


def main(argv: list[str] | None = None) -> int:
    try:
        summary = finalize(argv)
        emit_json(summary)
        return 0
    except CliFailure as exc:
        emit_json(exc.as_dict(), sys.stderr)
        return 1
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
