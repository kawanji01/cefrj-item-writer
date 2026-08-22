#!/usr/bin/env python3
"""生成・独立レビュー境界以外の作問フローを決定的に制御する。"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

from build_normalized import (
    CliFailure,
    emit_json,
    require_basic_environment,
    strict_json_loads,
)
from lookup import load_validated_resources
from set_support import (
    CEFR_CEILING,
    CEFRJ_VALUES,
    READABLE_RESOURCES,
    canonical_bytes,
    contract_failure,
    question_number,
    schema_version,
    strict_utf8_json_problems,
)


STATE_NAME = "flow-state.json"
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
SESSION_KEYS = {
    "created_at",
    "format",
    "level",
    "mode",
    "model",
    "preferred_proper_nouns",
    "requested_count",
    "set_id",
    "targets",
    "tool",
    "topic",
}
REMEDIES = {
    "E-INPUT-01": "python scripts/flow_control.py --help の日本語ヘルプを参照して引数を修正してください。",
    "E-INPUT-02": "指定パスの綴りと存在、読み取り権限を確認してください。",
    "E-INPUT-03": "入力をstrict UTF-8の標準JSONへ修正してください。",
    "E-INPUT-04": "確定済み条件または教師判断を仕様の値域へ修正してください。",
    "E-INPUT-05": "set_idを書式例20260816-142530-k7x2に一致させてください。",
    "E-DATA-07": "既存ファイルを変更せず、新しいset_idでセットを最初から作成してください。",
    "E-DATA-08": "進行中セットの監査を保持したまま中止し、python scripts/doctor.py を実行して新しいset_idで最初から作成してください。",
    "E-ENV-05": "outputディレクトリの権限と空き容量を確認してください。",
}
FORMAT_NUMERALS = dict(zip(FORMAT_VALUES, "①②③④⑤⑥⑦⑧⑨", strict=True))
CHECK_FORMATS = {
    "CHK-01": set(FORMAT_VALUES[4:]),
    "CHK-02": set(FORMAT_VALUES[:4]),
    "CHK-03": set(FORMAT_VALUES),
    "CHK-04": set(FORMAT_VALUES),
    "CHK-05": {FORMAT_VALUES[index] for index in (0, 1, 4, 5, 7)},
    "CHK-06": set(FORMAT_VALUES[:2]),
    "CHK-07": {FORMAT_VALUES[4]},
    "CHK-08": set(FORMAT_VALUES),
    "CHK-09": {FORMAT_VALUES[3]},
    "CHK-10": set(FORMAT_VALUES[4:]),
    "CHK-11": set(FORMAT_VALUES),
    "CHK-12": set(FORMAT_VALUES),
    "CHK-13": set(FORMAT_VALUES),
    "CHK-14": {FORMAT_VALUES[6]},
    "CHK-15": {FORMAT_VALUES[5]},
    "CHK-16": {FORMAT_VALUES[7]},
    "CHK-17": set(FORMAT_VALUES[4:]),
    "CHK-18": set(FORMAT_VALUES),
    "CHK-19": set(FORMAT_VALUES),
}
LEVEL_REVIEW_CODES = {"CHK-02", "CHK-03", "CHK-04", "CHK-07", "CHK-13"}
CEFRJ_RANK = {value: index for index, value in enumerate(CEFRJ_VALUES)}
KNOWN_CLI_ERROR_CODES = frozenset(
    {
        *(f"E-ENV-{number:02d}" for number in range(1, 7)),
        *(f"E-DATA-{number:02d}" for number in range(1, 9)),
        *(f"E-CONTRACT-{number:02d}" for number in range(1, 6)),
        *(f"E-INPUT-{number:02d}" for number in range(1, 6)),
    }
)
DISPUTE_REGENERATION_INSTRUCTION = (
    "機械検査誤検出の疑いがあっても機械検査違反は回避対象です。"
    "疑いのある箇所を温存せず、このセットでは機械検査を正として再生成してください。"
)


class FlowArgumentParser(argparse.ArgumentParser):
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
        raise CliFailure(
            "E-INPUT-01",
            f"E-INPUT-01 flow_control.pyの引数が不正です: {message}",
            detail={"parser_message": message},
            remedy=REMEDIES["E-INPUT-01"],
        )


def make_parser() -> FlowArgumentParser:
    parser = FlowArgumentParser(
        description="作問フローの世代管理・補充・監査・確定を決定的に進めます。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "candidate", "status"):
        child = subparsers.add_parser(command)
        child.add_argument("--set-dir", required=True)
        if command in {"init", "candidate"}:
            child.add_argument("--file", required=True, help="入力JSONパス。- はstdin。")
    review_preflight = subparsers.add_parser("review-preflight")
    review_preflight.add_argument("--set-dir", required=True)
    review_preflight.add_argument("--request", required=True)
    review = subparsers.add_parser("review")
    review.add_argument("--set-dir", required=True)
    review_input = review.add_mutually_exclusive_group(required=True)
    review_input.add_argument("--file", help="review_result JSONパス。- はstdin。")
    review_input.add_argument(
        "--process-failure",
        type=int,
        metavar="EXIT_CODE",
        help="レビュアープロセス失敗。stdinからstderr生バイト列を読む。",
    )
    decide = subparsers.add_parser("decide")
    decide.add_argument("--set-dir", required=True)
    decide.add_argument(
        "--decision", required=True, choices=("alternative", "reduce", "abort")
    )
    decide.add_argument("--target-ref")
    return parser


def read_bytes(path_text: str) -> bytes:
    if path_text == "-":
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        payload = stream.read()
        return payload.encode("utf-8") if isinstance(payload, str) else payload
    try:
        return Path(path_text).read_bytes()
    except OSError as exc:
        raise CliFailure(
            "E-INPUT-02",
            f"E-INPUT-02 入力ファイルを読み取れません: {path_text}",
            detail={"error": str(exc), "path": path_text},
            remedy=REMEDIES["E-INPUT-02"],
        ) from exc


def parse_json_bytes(payload: bytes, label: str) -> Any:
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CliFailure(
            "E-INPUT-03",
            f"E-INPUT-03 {label}がstrict UTF-8ではありません",
            detail={"byte_offset": exc.start, "source": label},
            remedy=REMEDIES["E-INPUT-03"],
        ) from exc
    try:
        value = strict_json_loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise CliFailure(
            "E-INPUT-03",
            f"E-INPUT-03 {label}が標準JSONではありません",
            detail={"error": str(exc), "source": label},
            remedy=REMEDIES["E-INPUT-03"],
        ) from exc
    utf8_problems = strict_utf8_json_problems(value)
    if utf8_problems:
        raise CliFailure(
            "E-INPUT-03",
            f"E-INPUT-03 {label}にstrict UTF-8へ符号化不能な文字列があります",
            detail={"problems": utf8_problems, "source": label},
            remedy=REMEDIES["E-INPUT-03"],
        )
    return value


def state_path(set_dir: Path) -> Path:
    return set_dir / ".staging" / STATE_NAME


def validate_flow_set_path(
    repo_root: Path, set_dir: Path, *, must_exist: bool
) -> None:
    set_id = set_dir.name
    if re.fullmatch(r"[0-9]{8}-[0-9]{6}-[a-z0-9]{4}", set_id) is None:
        raise CliFailure(
            "E-INPUT-05",
            f"E-INPUT-05 セットディレクトリ名がset_id書式ではありません: {set_dir}",
            detail={"path": str(set_dir), "set_id": set_id},
            remedy=REMEDIES["E-INPUT-05"],
        )
    expected_output = repo_root / "output"
    if set_dir.parent != expected_output or expected_output.is_symlink():
        raise contract_failure(
            "E-CONTRACT-03", [f"--set-dirは通常のoutput/直下ではありません: {set_dir}"]
        )
    if must_exist:
        if set_dir.is_symlink() or not set_dir.is_dir():
            raise CliFailure(
                "E-INPUT-02",
                f"E-INPUT-02 セットディレクトリが存在しないか通常ディレクトリではありません: {set_dir}",
                detail={"path": str(set_dir)},
                remedy=REMEDIES["E-INPUT-02"],
            )
        staging = set_dir / ".staging"
        state = state_path(set_dir)
        if staging.is_symlink() or state.is_symlink() or not state.is_file():
            raise contract_failure(
                "E-CONTRACT-03", [".staging/flow-state.jsonが通常ファイルではありません"]
            )
    elif set_dir.exists() or set_dir.is_symlink():
        raise CliFailure(
            "E-DATA-07",
            f"E-DATA-07 セットディレクトリが既に存在します: {set_dir}",
            detail={"path": str(set_dir)},
            remedy=REMEDIES["E-DATA-07"],
        )


def write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise CliFailure(
            "E-DATA-07",
            f"E-DATA-07 上書き禁止ファイルが既に存在します: {path}",
            detail={"path": str(path)},
            remedy=REMEDIES["E-DATA-07"],
        ) from exc
    except OSError as exc:
        raise CliFailure(
            "E-ENV-05",
            f"E-ENV-05 ファイルを作成できません: {path}",
            detail={"error": str(exc), "path": str(path)},
            remedy=REMEDIES["E-ENV-05"],
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def replace_state(path: Path, state: dict[str, Any]) -> None:
    payload = canonical_bytes(state)
    temporary = path.with_name(f".{STATE_NAME}.tmp.{os.getpid()}")
    write_exclusive(temporary, payload)
    try:
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise CliFailure(
            "E-ENV-05",
            f"E-ENV-05 フロー状態を更新できません: {path}",
            detail={"error": str(exc), "path": str(path)},
            remedy=REMEDIES["E-ENV-05"],
        ) from exc


def load_state(set_dir: Path) -> dict[str, Any]:
    path = state_path(set_dir)
    value = parse_json_bytes(read_bytes(str(path)), "flow-state")
    if not isinstance(value, dict):
        raise contract_failure("E-CONTRACT-01", ["flow-stateのトップレベルがobjectではありません"])
    if value.get("set_id") != set_dir.name:
        raise contract_failure("E-CONTRACT-01", ["flow-stateのset_idがディレクトリ名と一致しません"])
    return value


def persist(set_dir: Path, state: dict[str, Any]) -> None:
    replace_state(state_path(set_dir), state)


def cleanup_state(set_dir: Path) -> None:
    path = state_path(set_dir)
    try:
        path.unlink()
    except FileNotFoundError:
        return
    try:
        path.parent.rmdir()
    except OSError:
        pass


def ensure_config_snapshot(
    repo_root: Path, set_dir: Path, state: dict[str, Any]
) -> dict[str, Any]:
    """開始時設定と現在の検証済み設定をJSON値として完全一致比較する。"""

    resources = load_validated_resources(repo_root)
    current = build_config_snapshot(
        resources["limits"], resources["proper_nouns"]["words"]
    )
    snapshot = state.get("config_snapshot")
    if snapshot == current:
        return resources
    differences = {
        path: {"current": current[key], "snapshot": snapshot.get(key) if isinstance(snapshot, dict) else None}
        for path, key in (
            ("data/config/limits.json", "limits"),
            ("data/config/proper_nouns.json", "proper_nouns"),
        )
        if not isinstance(snapshot, dict) or snapshot.get(key) != current[key]
    }
    cleanup_state(set_dir)
    raise CliFailure(
        "E-DATA-08",
        "E-DATA-08 セッション設定スナップショットと現在の設定が一致しません",
        detail={"differences": differences},
        remedy=REMEDIES["E-DATA-08"],
    )


def load_checked_state(
    repo_root: Path, set_dir: Path
) -> dict[str, Any]:
    state = load_state(set_dir)
    ensure_config_snapshot(repo_root, set_dir, state)
    return state


def review_preflight(
    repo_root: Path, set_dir: Path, request_path: str
) -> dict[str, Any]:
    """子レビュアー起動前に現在requestと適用timeoutをC12で一括確定する。"""

    state = load_state(set_dir)
    resources = ensure_config_snapshot(repo_root, set_dir, state)
    action = state.get("last_action")
    if (
        state.get("outcome") != "running"
        or not isinstance(action, dict)
        or action.get("action") != "run_review"
        or action.get("request_path") != request_path
    ):
        raise contract_failure(
            "E-CONTRACT-01",
            ["レビュアー起動対象が直前のrun_review actionと一致しません"],
        )
    request_file = Path(request_path)
    if not request_file.is_absolute():
        request_file = repo_root / request_file
    review_dir = set_dir / "review"
    if (
        request_file.parent != review_dir
        or review_dir.is_symlink()
        or request_file.is_symlink()
        or not request_file.is_file()
    ):
        raise contract_failure(
            "E-CONTRACT-03",
            [f"直前actionが指すreview_request監査が通常ファイルではありません: {request_path}"],
        )
    payload = read_bytes(str(request_file))
    request, diagnostic, _invalid = validate_external(
        repo_root, "review_request", request_path, payload
    )
    if request is None:
        raise contract_failure(
            "E-CONTRACT-01",
            [f"review_requestの起動前再検証に失敗しました: {diagnostic}"],
        )
    current = state.get("current")
    if not isinstance(current, dict):
        raise contract_failure(
            "E-CONTRACT-01", ["現在のレビュー対象stateがobjectではありません"]
        )
    try:
        expected = build_review_request(
            current["candidate"],
            current["machine"],
            state["set_id"],
            f"gen{current['generation_number']}",
            limits=state["config_snapshot"]["limits"],
            proper_nouns=state["config_snapshot"]["proper_nouns"],
            topic=state["session"]["topic"],
        )
    except (KeyError, TypeError) as exc:
        raise contract_failure(
            "E-CONTRACT-01",
            [f"現在stateからreview_requestを再構築できません: {exc}"],
        ) from exc
    if payload != canonical_bytes(expected):
        raise contract_failure(
            "E-CONTRACT-01",
            ["review_requestが現在stateから再構築したJS-01正準バイト列と一致しません"],
        )
    return {
        "request_path": request_path,
        "review_timeout_seconds": resources["limits"]["review_timeout_seconds"],
    }


def cleanup_candidate_provider_input(input_path: str, set_dir: Path) -> None:
    """M7D-12の固定candidate rawだけを受理後に削除する。"""

    if input_path == "-":
        return
    path = Path(input_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    expected_parent = set_dir / ".staging"
    if path.parent != expected_parent or re.fullmatch(
        r"q(?:0[1-9]|1[0-9]|20)\.gen[123]\.candidate\.raw[12]\.json",
        path.name,
    ) is None:
        return
    try:
        path.unlink()
    except OSError as exc:
        raise CliFailure(
            "E-ENV-05",
            f"E-ENV-05 candidate一時入力を削除できません: {path}",
            detail={"error": str(exc), "path": str(path)},
            remedy=REMEDIES["E-ENV-05"],
        ) from exc


def run_child(
    repo_root: Path,
    script_name: str,
    *arguments: str,
    stdin: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(repo_root / "scripts" / script_name), *arguments],
        cwd=repo_root,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def child_json(completed: subprocess.CompletedProcess[bytes], stream: str = "stdout") -> Any:
    payload = completed.stdout if stream == "stdout" else completed.stderr
    return parse_json_bytes(payload, f"child-{stream}")


def require_child_success(
    completed: subprocess.CompletedProcess[bytes], fallback_code: str
) -> None:
    """定義済み子CLIエラーはコード・詳細・対処を変えずに伝播する。"""

    if completed.returncode == 0:
        return
    failure = child_cli_failure(completed)
    if failure is not None:
        raise failure
    diagnostic = (completed.stderr or completed.stdout).decode(
        "utf-8", errors="backslashreplace"
    )
    raise RuntimeError(
        f"子CLIが内部エラー終了{completed.returncode}を返しました"
        f"（従来のfallback={fallback_code}）: "
        f"{diagnostic or '出力なし'}"
    )


def child_cli_failure(
    completed: subprocess.CompletedProcess[bytes],
) -> CliFailure | None:
    """終了1のstderr末尾が既知CLI-05完全形なら同じCliFailureへ復元する。"""

    if completed.returncode != 1:
        return None
    try:
        stderr = completed.stderr.decode("utf-8", errors="strict").rstrip()
    except UnicodeDecodeError:
        return None
    error: Any = None
    line_starts = [0, *(match.end() for match in re.finditer(r"\r?\n", stderr))]
    for start in reversed(line_starts):
        candidate = stderr[start:].lstrip()
        if not candidate:
            continue
        try:
            error = strict_json_loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        break
    if error is None:
        return None
    if not (
        isinstance(error, dict)
        and set(error) == {"detail", "error_code", "message", "remedy"}
        and all(
            isinstance(error[key], str) and error[key]
            for key in ("error_code", "message", "remedy")
        )
        and error["error_code"] in KNOWN_CLI_ERROR_CODES
    ):
        return None
    return CliFailure(
        error["error_code"],
        error["message"],
        detail=error["detail"],
        remedy=error["remedy"],
    )


def relative_or_absolute(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return str(path)


def build_session_input(
    request: dict[str, Any],
    set_id: str,
    *,
    created_at: str,
    model: str,
    tool: str,
    topic: str | None = None,
    preferred_proper_nouns: list[str] | None = None,
) -> dict[str, Any]:
    """確定済み教師条件からflow_control init入力を組み立てる製品実装。"""

    return {
        "created_at": created_at,
        "format": request["format"],
        "level": {"scale": request["level_scale"], "value": request["level"]},
        "mode": request["mode"],
        "model": model,
        "preferred_proper_nouns": preferred_proper_nouns or [],
        "requested_count": request["question_count"],
        "set_id": set_id,
        "targets": list(request["targets"]),
        "tool": tool,
        "topic": topic,
    }


def build_session_from_candidate(
    candidate: dict[str, Any],
    set_id: str,
    requested_count: int,
    *,
    created_at: str,
    mode: str,
    model: str,
    tool: str,
    topic: str | None = None,
    preferred_proper_nouns: list[str] | None = None,
) -> dict[str, Any]:
    """既存candidateから決定的CI・確定処理用のセッション入力を構築する。"""

    return {
        "created_at": created_at,
        "format": candidate["format"],
        "level": candidate["level"],
        "mode": mode,
        "model": model,
        "preferred_proper_nouns": preferred_proper_nouns or [],
        "requested_count": requested_count,
        "set_id": set_id,
        "targets": [candidate["target"]["ref"]],
        "tool": tool,
        "topic": topic,
    }


def build_review_request(
    candidate: dict[str, Any],
    machine: dict[str, Any],
    set_id: str,
    generation: str,
    *,
    limits: dict[str, Any],
    proper_nouns: list[str],
    topic: str | None,
) -> dict[str, Any]:
    """RC-01〜RC-08のreview_requestを単一の製品実装で構築する。"""

    band = candidate["level"]["value"].split(".", 1)[0]
    if candidate["format"] in VOCAB_FORMATS:
        grammar_max = CEFR_CEILING[band]
        explanation_limit = None
    else:
        grammar_max = candidate["level"]["value"]
        explanation_limit = limits["explanation_char_limits"][candidate["explanation"]["type"]]
    return {
        "candidate": candidate,
        "constraints_snapshot": {
            "limits": {
                "explanation_char_limit": explanation_limit,
                "sentence_word_limit": limits["sentence_word_limits"][band],
            },
            "proper_nouns": proper_nouns,
            "topic": topic,
        },
        "format": candidate["format"],
        "generation": generation,
        "level": candidate["level"],
        "level_limits": {
            "grammar_intro_level_max": grammar_max,
            "vocabulary_level_max": band,
        },
        "machine_report": machine,
        "question_id": candidate["question_id"],
        "readable_resources": list(READABLE_RESOURCES),
        "schema_version": "1.0.0",
        "set_id": set_id,
        "target_ref": candidate["target"]["ref"],
    }


def build_slot_outcome(
    set_id: str,
    slot_id: str,
    attempted_ids: list[str],
    accepted_id: str | None,
    *,
    reduced: bool = False,
) -> dict[str, Any]:
    """AUD-11の6フィールドを単一の製品実装で構築する。"""

    return {
        "accepted_question_id": None if reduced else accepted_id,
        "attempted_question_ids": list(attempted_ids),
        "set_id": set_id,
        "slot_question_id": slot_id,
        "status": "reduced" if reduced else "accepted",
        "teacher_decision": "reduce" if reduced else None,
    }


def build_finalize_metadata(
    session: dict[str, Any],
    config_snapshot: dict[str, Any],
    final_ids: list[str],
) -> dict[str, Any]:
    """FIN-01入力を単一の製品実装で構築する。"""

    return {
        "config_snapshot": config_snapshot,
        "created_at": session["created_at"],
        "final_question_ids": list(final_ids),
        "format": session["format"],
        "level": session["level"],
        "mode": session["mode"],
        "model": session["model"],
        "preferred_proper_nouns": session["preferred_proper_nouns"],
        "requested_count": session["requested_count"],
        "set_id": session["set_id"],
        "tool": session["tool"],
        "topic": session["topic"],
    }


def build_config_snapshot(
    limits: dict[str, Any], proper_nouns: list[str]
) -> dict[str, Any]:
    """FIN-01とフロー状態が共有する設定スナップショットを構築する。"""

    return {"limits": limits, "proper_nouns": list(proper_nouns)}


def validate_session(session: Any, resources: dict[str, Any], set_dir: Path) -> dict[str, Any]:
    if not isinstance(session, dict) or set(session) != SESSION_KEYS:
        raise contract_failure("E-CONTRACT-01", ["init入力の固定フィールドが不正です"])
    problems: list[str] = []
    set_id = session["set_id"]
    if not isinstance(set_id, str) or re.fullmatch(r"[0-9]{8}-[0-9]{6}-[a-z0-9]{4}", set_id) is None:
        problems.append("set_idが固定書式ではありません")
    elif set_id != set_dir.name:
        problems.append("set_idが--set-dirのディレクトリ名と一致しません")
    fmt = session["format"]
    if fmt not in FORMAT_VALUES:
        problems.append("formatが9形式ではありません")
    level = session["level"]
    if not isinstance(level, dict) or set(level) != {"scale", "value"}:
        problems.append("levelがscale/valueだけを持つobjectではありません")
    elif fmt in VOCAB_FORMATS and level not in (
        {"scale": "cefr", "value": "A1"},
        {"scale": "cefr", "value": "A2"},
        {"scale": "cefr", "value": "B1"},
        {"scale": "cefr", "value": "B2"},
    ):
        problems.append("語彙形式のlevelがCEFR 4段階ではありません")
    elif fmt not in VOCAB_FORMATS and (
        level.get("scale") != "cefrj"
        or level.get("value") not in {"A1.1", "A1.2", "A1.3", "A2.1", "A2.2", "B1.1", "B1.2", "B2.1", "B2.2"}
    ):
        problems.append("文法形式のlevelがCEFR-J 9段階ではありません")
    requested = session["requested_count"]
    maximum = resources["limits"]["set_question_max"]
    if isinstance(requested, bool) or not isinstance(requested, int) or not 1 <= requested <= maximum:
        problems.append("requested_countが1..set_question_maxではありません")
    mode = session["mode"]
    if mode not in {"explicit", "proposal"}:
        problems.append("modeがexplicit/proposalではありません")
    targets = session["targets"]
    if not isinstance(targets, list) or any(not isinstance(item, str) or not item for item in targets):
        problems.append("targetsが非空文字列配列ではありません")
    elif isinstance(requested, int):
        cap = min(2 * requested, 20)
        if mode == "explicit" and len(targets) != requested:
            problems.append("明示モードのtargets件数がrequested_countと一致しません")
        if mode == "proposal" and not requested <= len(targets) <= cap:
            problems.append("提案モードのtargets件数がrequested_count..min(2N,20)ではありません")
    for field in ("created_at", "model", "tool"):
        if not isinstance(session[field], str) or not session[field]:
            problems.append(f"{field}が非空文字列ではありません")
    if session["tool"] not in {"claude_code", "codex"}:
        problems.append("toolがclaude_code/codexではありません")
    if session["topic"] is not None and (
        not isinstance(session["topic"], str) or not session["topic"]
    ):
        problems.append("topicが非空文字列またはnullではありません")
    preferred = session["preferred_proper_nouns"]
    if not isinstance(preferred, list) or any(
        not isinstance(item, str) or item not in resources["proper_nouns"]["words"]
        for item in preferred
    ):
        problems.append("preferred_proper_nounsがallowlist内の文字列配列ではありません")
    if problems:
        raise contract_failure("E-CONTRACT-01", problems)
    return session


def action_for_current(state: dict[str, Any]) -> dict[str, Any]:
    current = state["current"]
    action = {
        "action": "generate_candidate",
        "candidate_output_number": current["candidate_attempt"] + 1,
        "generation": f"gen{current['generation_number']}",
        "question_id": current["question_id"],
        "regeneration": current["regeneration"],
        "slot_question_id": current["slot_question_id"],
        "target_ref": current["target_ref"],
    }
    state["last_action"] = action
    return action


def terminal_payload(state: dict[str, Any], outcome: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "action": outcome,
        "attempts_total": state["generation_attempts_total"],
        "generation_verdicts": state["generation_verdicts"],
        "machine_check_dispute_count": state["machine_check_dispute_count"],
        "outcome": outcome,
        "regeneration_payloads": state["regeneration_payloads"],
        "target_attempts_total": state["target_attempts_total"],
        **extra,
    }
    state["last_action"] = payload
    state["outcome"] = outcome
    return payload


def start_assignment(state: dict[str, Any], assignment: dict[str, str]) -> dict[str, Any]:
    state["target_attempts_total"] += 1
    state["current"] = {
        **assignment,
        "candidate_attempt": 0,
        "generation_counted": False,
        "generation_number": 1,
        "regeneration": None,
        "review_attempt": 0,
    }
    return action_for_current(state)


def next_unused_qid(state: dict[str, Any]) -> str | None:
    used = set(state["owner_by_question"])
    for number in range(1, 21):
        qid = f"q{number:02d}"
        if qid not in used:
            return qid
    return None


def allocate_replacement(state: dict[str, Any], slot_id: str, target_ref: str) -> dict[str, str]:
    qid = next_unused_qid(state)
    if qid is None:
        raise contract_failure("E-CONTRACT-04", ["未使用question_idがありません"])
    state["owner_by_question"][qid] = slot_id
    state["slot_attempts"][slot_id].append(qid)
    state["target_by_question"][qid] = target_ref
    return {
        "question_id": qid,
        "slot_question_id": slot_id,
        "target_ref": target_ref,
    }


def consultation(state: dict[str, Any], failed: dict[str, Any]) -> dict[str, Any]:
    qid = failed["question_id"]
    slot_ids = [failed["slot_question_id"]]
    if state["session"]["mode"] == "proposal":
        slot_ids.extend(
            slot_id for slot_id in state["unresolved_slots"] if slot_id not in slot_ids
        )
    attempted_qids = [
        attempted_qid
        for slot_id in slot_ids
        for attempted_qid in state["slot_attempts"][slot_id]
    ]
    generations = [
        item
        for item in state["generation_verdicts"]
        if item["question_id"] in attempted_qids
    ]
    failed_targets = [
        {
            "generations": [
                item for item in generations if item["question_id"] == attempted_qid
            ],
            "question_id": attempted_qid,
            "target_ref": state["target_by_question"][attempted_qid],
        }
        for attempted_qid in attempted_qids
    ]
    cap = min(2 * state["session"]["requested_count"], 20)
    choices = ["abort"]
    if state["accepted_slots"] or state["pending_assignments"]:
        choices.insert(0, "reduce")
    if state["target_attempts_total"] < cap and next_unused_qid(state) is not None:
        choices.insert(0, "alternative")
    summary = {
        "accepted_count": len(state["accepted_slots"]),
        "choices": choices,
        "failed_question_id": qid,
        "failed_target_ref": failed["target_ref"],
        "failed_targets": failed_targets,
        "generations": generations,
        "requested_count": state["session"]["requested_count"],
        "slot_question_id": failed["slot_question_id"],
        "target_attempt_limit": cap,
        "target_attempts_total": state["target_attempts_total"],
    }
    state["consultation"] = summary
    state["current"] = failed
    return terminal_payload(state, "teacher_consult", consultation=summary)


def write_audit(path: Path, value: Any) -> None:
    write_exclusive(path, canonical_bytes(value))


def validation_failure(payload: bytes, diagnostic: str) -> dict[str, Any]:
    return {
        "audit_format": "aud09-v2",
        "diagnostic": diagnostic,
        "kind": "validation_failure",
        "raw_output_base64": base64.b64encode(payload).decode("ascii"),
    }


def process_failure(exit_code: int | None, stderr: bytes) -> dict[str, Any]:
    return {
        "audit_format": "aud09-v2",
        "exit_code": exit_code,
        "kind": "process_failure",
        "stderr_base64": base64.b64encode(stderr).decode("ascii"),
    }


def utf8_failure(exc: UnicodeEncodeError) -> dict[str, Any]:
    return {
        "audit_format": "aud09-v2",
        "kind": "utf8_encode_failure",
        "position": f"JSON string value U+{ord(exc.object[exc.start]):04X}",
        "reason": "孤立サロゲートをstrict UTF-8へ符号化できません",
    }


def validate_external(
    repo_root: Path, schema: str, path_text: str, payload: bytes
) -> tuple[Any | None, str | None, dict[str, Any] | None]:
    if not payload:
        return None, "providerの生出力が空です", process_failure(None, b"")
    completed = run_child(
        repo_root,
        "validate.py",
        "--schema",
        schema,
        "--file",
        path_text,
        stdin=payload if path_text == "-" else None,
    )
    if completed.returncode == 0:
        try:
            value = parse_json_bytes(payload, path_text)
            canonical_bytes(value)
        except CliFailure as exc:
            return None, exc.message, validation_failure(payload, exc.message)
        except UnicodeEncodeError as exc:
            return None, str(exc), utf8_failure(exc)
        return value, None, None
    failure = child_cli_failure(completed)
    if completed.returncode == 1 and failure is not None:
        if failure.error_code not in {"E-CONTRACT-01", "E-INPUT-03"}:
            raise failure
        diagnostic = failure.message
    elif completed.returncode == 1:
        raise RuntimeError("validate.pyが終了1でCLI-05完全形を返しませんでした")
    else:
        raise RuntimeError(
            f"validate.pyが内部エラー終了{completed.returncode}を返しました: "
            + (completed.stderr or completed.stdout).decode(
                "utf-8", errors="backslashreplace"
            )
        )
    try:
        value = strict_json_loads(payload.decode("utf-8", errors="strict"))
        utf8_problems = strict_utf8_json_problems(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        utf8_problems = []
    if utf8_problems:
        first = utf8_problems[0]
        match = re.search(r"U\+([0-9A-F]{4,6})", first)
        codepoint = int(match.group(1), 16) if match else 0xD800
        surrogate_exc = UnicodeEncodeError("utf-8", chr(codepoint), 0, 1, first)
        return None, diagnostic, utf8_failure(surrogate_exc)
    return None, diagnostic, validation_failure(payload, diagnostic or "検証に失敗しました")


def expected_not_applicable_reason(
    check_id: str, candidate: dict[str, Any], topic: str | None
) -> str | None:
    fmt = candidate["format"]
    if fmt not in CHECK_FORMATS[check_id]:
        return f"形式{FORMAT_NUMERALS[fmt]}のため"
    if check_id == "CHK-17" and candidate["body"].get("context_sentence") is None:
        return "例文が1文のため"
    if check_id == "CHK-19" and topic is None:
        return "トピック指定なしのため"
    return None


def grammar_intro_level_max(candidate: dict[str, Any]) -> str:
    value = candidate["level"]["value"]
    return CEFR_CEILING[value] if candidate["format"] in VOCAB_FORMATS else value


def inventory_intro_level(item: dict[str, Any]) -> str:
    return item["level"].split("-", 1)[0]


def evidence_gp_ids(evidence: str) -> set[str]:
    """gp IDを英数字・ハイフン境界付きの完全トークンとして抽出する。"""

    return set(
        re.findall(
            r"(?<![A-Za-z0-9-])gp:[0-9]+(?:-[0-9]+)?(?![A-Za-z0-9-])",
            evidence,
        )
    )


def evidence_cefrj_levels(evidence: str) -> set[str]:
    """CEFR-J単一値・範囲値を英数字・ピリオド境界付きで抽出する。"""

    value = r"(?:A1\.[123]|A2\.[12]|B1\.[12]|B2\.[12])"
    return set(
        re.findall(
            rf"(?<![A-Za-z0-9.]){value}(?:-{value})?(?![A-Za-z0-9.])",
            evidence,
        )
    )


def kyoinban_reference(
    item: dict[str, Any], grammar_index: dict[str, dict[str, Any]]
) -> tuple[str, str | None, str] | None:
    """正規化grammarから教員版level_raw・継承元ID・文法項目名を導出する。"""

    entry = grammar_index.get(item["grammar_item_id"])
    if entry is None:
        return None
    direct_raw = entry["kyoinban"]["level_raw"]
    if entry["kyoinban"]["present"] and isinstance(direct_raw, str):
        structure = entry["kyoinban"]["name_ja"]
        if not isinstance(structure, str):
            return None
        return direct_raw, None, structure
    parent_id = entry["level"]["inherited_from"]
    parent = grammar_index.get(parent_id) if isinstance(parent_id, str) else None
    if parent is None:
        return None
    parent_raw = parent["kyoinban"]["level_raw"]
    structure = parent["kyoinban"]["name_ja"]
    if (
        not parent["kyoinban"]["present"]
        or not isinstance(parent_raw, str)
        or not isinstance(structure, str)
    ):
        return None
    return parent_raw, parent_id, structure


def kyoinban_evidence_matches(
    evidence: str,
    grammar_item_id: str,
    level_raw: str,
    inherited_from: str | None,
) -> bool:
    ids = evidence_gp_ids(evidence)
    levels = evidence_cefrj_levels(evidence)
    if grammar_item_id not in ids or level_raw not in levels:
        return False
    if inherited_from is None:
        return True
    return inherited_from in ids and "継承" in evidence


def fill_review_blank(template: str, answer: str) -> str:
    return template.replace("____", answer)


def chk03_candidate_texts(candidate: dict[str, Any]) -> list[tuple[str, str]]:
    """CHK-03が全文法構造を列挙する完成英文を形式別に返す。"""

    body = candidate["body"]
    fmt = candidate["format"]
    if fmt == "vocab_mcq_en2ja":
        return [("body.stem", body["stem"])]
    if fmt == "vocab_mcq_ja2en":
        return [("body.sentence_complete", body["sentence_complete"])]
    if fmt in {"vocab_flashcard_en2ja", "vocab_flashcard_ja2en"}:
        return [("body.example.en", body["example"]["en"])]
    if fmt == "grammar_mcq":
        correct = next(choice for choice in body["choices"] if choice["is_correct"])
        texts = [
            (
                "body.sentence_with_blank#filled:answer",
                fill_review_blank(body["sentence_with_blank"], correct["text"]),
            )
        ]
    elif fmt == "grammar_cloze":
        texts = [
            (
                "body.sentence_with_blank#filled:answer",
                fill_review_blank(body["sentence_with_blank"], body["answer"]),
            )
        ]
    elif fmt == "grammar_reorder":
        return [("body.answer_sentence", body["answer_sentence"])]
    elif fmt == "grammar_rewrite":
        return [
            ("body.source_sentence", body["source_sentence"]),
            (
                "body.target_sentence_with_blank#filled:answer",
                fill_review_blank(
                    body["target_sentence_with_blank"], body["answer"]
                ),
            ),
        ]
    else:
        texts = [("body.example.en", body["example"]["en"])]
    if body.get("context_sentence") is not None:
        texts.insert(0, ("body.context_sentence", body["context_sentence"]))
    return texts


def text_contains_complete_span(text: str, span: str) -> bool:
    """語の途中を切った部分一致を除き、候補英文中の完全な語列だけを受理する。"""

    start = 0
    while (index := text.find(span, start)) >= 0:
        before = text[index - 1] if index else ""
        end = index + len(span)
        after = text[end] if end < len(text) else ""
        starts_midword = span[0].isalnum() and before.isalnum()
        ends_midword = span[-1].isalnum() and after.isalnum()
        if not starts_midword and not ends_midword:
            return True
        start = index + 1
    return False


def chk03_violation_matches_inventory_item(
    violation: dict[str, Any],
    item: dict[str, Any],
    candidate_texts: list[tuple[str, str]],
    grammar_index: dict[str, dict[str, Any]] | None,
) -> bool:
    """CHK-03違反を同一span・導入レベル・level_source根拠へ結び付ける。"""

    actual_level = violation["actual_level"]
    location = violation["location"]
    evidence = violation["evidence"]
    span = item["span"]
    matching_fields = [
        field
        for field, text in candidate_texts
        if text_contains_complete_span(text, span)
    ]
    if (
        inventory_intro_level(item) != actual_level
        or not matching_fields
        or json.dumps(span, ensure_ascii=False) not in location
        or not any(field in location for field in matching_fields)
    ):
        return False
    if item["level_source"] == "kyoinban":
        grammar_item_id = item["grammar_item_id"]
        if grammar_index is None:
            return evidence == item["evidence"]
        reference = kyoinban_reference(item, grammar_index)
        if reference is None:
            return False
        level_raw, inherited_from, structure = reference
        return (
            item["level"] == level_raw
            and all(
                kyoinban_evidence_matches(
                    source, grammar_item_id, level_raw, inherited_from
                )
                for source in (item["evidence"], evidence)
            )
            and item["structure"] == structure
        )
    if item["level_source"] == "reviewer_estimate":
        return evidence == item["evidence"] and "reviewer_estimate" in evidence
    return False


def chk03_inventory_matches(
    violation: dict[str, Any],
    inventory: list[dict[str, Any]],
    candidate_texts: list[tuple[str, str]],
    grammar_index: dict[str, dict[str, Any]] | None,
) -> bool:
    return any(
        chk03_violation_matches_inventory_item(
            violation, item, candidate_texts, grammar_index
        )
        for item in inventory
    )


def review_semantic_problems(
    review: dict[str, Any],
    candidate: dict[str, Any],
    topic: str | None,
    machine_report: dict[str, Any] | None = None,
    grammar_index: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """RR-01/04/05・RC-13のスキーマ横断意味契約を検査する。"""

    problems: list[str] = []
    candidate_texts = chk03_candidate_texts(candidate)
    inventory = review["sentence_grammar_inventory"]
    if not inventory:
        problems.append("sentence_grammar_inventoryが空でCHK-03の全文法構造を列挙していません")
    for index, item in enumerate(inventory):
        if not any(
            text_contains_complete_span(text, item["span"])
            for _field, text in candidate_texts
        ):
            problems.append(
                f"sentence_grammar_inventory[{index}].spanがCHK-03対象英文中の"
                "完全な語列ではありません"
            )
        if item["level_source"] == "kyoinban" and grammar_index is not None:
            reference = kyoinban_reference(item, grammar_index)
            if reference is None:
                problems.append(
                    f"sentence_grammar_inventory[{index}]のgrammar_item_idが"
                    "教員版レベル根拠を持つ正規化grammar項目へ解決できません"
                )
            else:
                level_raw, inherited_from, structure = reference
                if item["structure"] != structure:
                    problems.append(
                        f"sentence_grammar_inventory[{index}].structureが正規化grammarの"
                        f"教員版文法項目名と一致しません: expected={structure}, "
                        f"actual={item['structure']}"
                    )
                if item["level"] != level_raw:
                    problems.append(
                        f"sentence_grammar_inventory[{index}].levelが正規化grammarの"
                        f"教員版level_rawと一致しません: expected={level_raw}, "
                        f"actual={item['level']}"
                    )
                if not kyoinban_evidence_matches(
                    item["evidence"],
                    item["grammar_item_id"],
                    level_raw,
                    inherited_from,
                ):
                    problems.append(
                        f"sentence_grammar_inventory[{index}].evidenceがgp ID・"
                        "level_raw・継承元を完全引用していません"
                    )
        elif item["level_source"] == "reviewer_estimate":
            evidence = item["evidence"]
            if item["level"] not in evidence_cefrj_levels(evidence):
                problems.append(
                    f"sentence_grammar_inventory[{index}].evidenceが推定導入レベルを"
                    "完全引用していません"
                )
            if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", evidence) is None:
                problems.append(
                    f"sentence_grammar_inventory[{index}].evidenceに日本語の推定根拠がありません"
                )
    checks = {item["check_id"]: item for item in review["checks"]}
    failed_checks = {
        check_id for check_id, item in checks.items() if item["result"] == "fail"
    }
    violation_codes = [item["code"] for item in review["violations"]]
    level_max = grammar_intro_level_max(candidate)
    chk03_violations = [
        item for item in review["violations"] if item["code"] == "CHK-03"
    ]
    excess_inventory = [
        (index, item)
        for index, item in enumerate(inventory)
        if CEFRJ_RANK[inventory_intro_level(item)] > CEFRJ_RANK[level_max]
    ]
    violation_matches: dict[int, int] = {}

    def assign_excess(inventory_position: int, seen: set[int]) -> bool:
        _index, item = excess_inventory[inventory_position]
        for violation_index, violation in enumerate(chk03_violations):
            if violation_index in seen:
                continue
            if violation["expected_level"] != level_max or not (
                chk03_violation_matches_inventory_item(
                    violation, item, candidate_texts, grammar_index
                )
            ):
                continue
            seen.add(violation_index)
            previous = violation_matches.get(violation_index)
            if previous is None or assign_excess(previous, seen):
                violation_matches[violation_index] = inventory_position
                return True
        return False

    matched_inventory: set[int] = set()
    for inventory_position in range(len(excess_inventory)):
        if assign_excess(inventory_position, set()):
            matched_inventory.add(inventory_position)

    for inventory_position, (index, item) in enumerate(excess_inventory):
        intro_level = inventory_intro_level(item)
        if checks["CHK-03"]["result"] != "fail":
            problems.append(
                f"sentence_grammar_inventory[{index}]の導入レベル{intro_level}が"
                f"L_ctx={level_max}を超えていますがCHK-03がfailではありません"
            )
        if inventory_position not in matched_inventory:
            problems.append(
                f"sentence_grammar_inventory[{index}]の上限超過構造に対応する"
                "未使用の同一span・導入レベル・level_source根拠の"
                "CHK-03 violationがありません"
            )
    for violation_index in sorted(set(range(len(chk03_violations))) - violation_matches.keys()):
        problems.append(
            f"CHK-03 violations[{violation_index}]が上限超過構造との一対一対応で余剰です"
        )
    for check_id in sorted(failed_checks):
        if check_id not in violation_codes:
            problems.append(f"{check_id}がfailですが対応するviolationがありません")
    for code in sorted(set(violation_codes)):
        if code not in failed_checks:
            problems.append(f"{code}のviolationがありますがcheck結果がfailではありません")
    expected_verdict = "fail" if failed_checks else "pass"
    if review["verdict"] != expected_verdict:
        problems.append(
            f"verdictがcheck結果と一致しません: expected={expected_verdict}, actual={review['verdict']}"
        )
    for check_id, item in checks.items():
        expected_reason = expected_not_applicable_reason(check_id, candidate, topic)
        if expected_reason is None and item["result"] == "not_applicable":
            problems.append(f"{check_id}は現在の形式・条件で適用対象です")
        elif expected_reason is not None and (
            item["result"] != "not_applicable" or item["note"] != expected_reason
        ):
            problems.append(
                f"{check_id}の適用外記録はresult=not_applicable、note={expected_reason!r}でなければなりません"
            )
    for index, violation in enumerate(review["violations"]):
        level_values = (violation["expected_level"], violation["actual_level"])
        if violation["code"] in LEVEL_REVIEW_CODES:
            if any(value is None for value in level_values):
                problems.append(
                    f"violations[{index}] {violation['code']}のレベル値がnullです"
                )
        elif any(value is not None for value in level_values):
            problems.append(
                f"violations[{index}] {violation['code']}の非レベル違反でレベル値がnullではありません"
            )
        if violation["code"] == "CHK-03" and all(
            isinstance(value, str) for value in level_values
        ):
            expected_level, actual_level = level_values
            if expected_level != level_max:
                problems.append(
                    f"violations[{index}] CHK-03のexpected_levelがL_ctxと一致しません: "
                    f"expected={level_max}, actual={expected_level}"
                )
            if actual_level not in CEFRJ_RANK:
                problems.append(
                    f"violations[{index}] CHK-03のactual_levelがCEFR-J 9段階ではありません: "
                    f"{actual_level}"
                )
            elif CEFRJ_RANK[actual_level] <= CEFRJ_RANK[level_max]:
                problems.append(
                    f"violations[{index}] CHK-03のactual_levelがL_ctxを超えていません: "
                    f"L_ctx={level_max}, actual={actual_level}"
                )
            if actual_level in CEFRJ_RANK and not chk03_inventory_matches(
                violation,
                review["sentence_grammar_inventory"],
                candidate_texts,
                grammar_index,
            ):
                problems.append(
                    f"violations[{index}] CHK-03に対応する同一span・導入レベル・根拠の"
                    "sentence_grammar_inventory記録がありません"
                )
    if machine_report is not None:
        machine_locations = {
            (violation["code"], violation["location"])
            for violation in machine_report["violations"]
        }
        for index, dispute in enumerate(review["machine_check_disputes"]):
            reference = (
                dispute["machine_violation_code"],
                dispute["location"],
            )
            if reference not in machine_locations:
                problems.append(
                    "machine_check_disputes["
                    f"{index}]のcode/locationがmachine_report.violations[]に存在しません: "
                    f"code={reference[0]}, location={reference[1]}"
                )
    return problems


def record_generation_failure(
    state: dict[str, Any], reason: str, violations: list[dict[str, Any]], **extra: Any
) -> None:
    current = state["current"]
    state["generation_verdicts"].append(
        {
            "generation": f"gen{current['generation_number']}",
            "question_id": current["question_id"],
            "reason": reason,
            "verdict": "fail",
            "violations": violations,
            **extra,
        }
    )


def advance_generation(
    state: dict[str, Any],
    reason: str,
    violations: list[dict[str, Any]],
    *,
    regeneration: dict[str, Any],
    **extra: Any,
) -> dict[str, Any] | None:
    current = state["current"]
    record_generation_failure(state, reason, violations, **extra)
    if current["generation_number"] >= state["generation_max"]:
        return None
    state["regeneration_payloads"].append(regeneration)
    current.update(
        {
            "candidate_attempt": 0,
            "generation_counted": False,
            "generation_number": current["generation_number"] + 1,
            "regeneration": regeneration,
            "review_attempt": 0,
        }
    )
    return action_for_current(state)


def candidate_validation_regeneration(
    current: dict[str, Any], diagnostic: str | None
) -> dict[str, Any]:
    return {
        "candidate_validation_diagnostic": diagnostic,
        "generation": f"gen{current['generation_number']}",
        "question_id": current["question_id"],
    }


def reviewed_regeneration(
    current: dict[str, Any],
    review: dict[str, Any],
    *,
    set_check_violations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    disputes = list(review["machine_check_disputes"])
    return {
        "generation": f"gen{current['generation_number']}",
        "machine_check_disputes": disputes,
        "machine_check_dispute_instruction": (
            DISPUTE_REGENERATION_INSTRUCTION if disputes else None
        ),
        "machine_violations": list(current["machine"]["violations"]),
        "previous_candidate": current["candidate"],
        "question_id": current["question_id"],
        "review_violations": list(review["violations"]),
        "set_check_violations": list(set_check_violations or []),
    }


def finalized_warning(
    completed: subprocess.CompletedProcess[bytes], repo_root: Path, set_dir: Path
) -> dict[str, Any] | None:
    """終了0のfinalize stderrをCLI-22aの正準警告として厳格検証する。"""

    if not completed.stderr:
        return None
    warning = parse_json_bytes(completed.stderr, "finalize_set.py stderr")
    expected_message = "set.jsonは完成しましたが一時リンクを削除できませんでした"
    expected_remedy = (
        "set.jsonを変更せず、権限を確認して表示された一時リンクだけを削除してください。"
        "finalize_set.pyは再実行しないでください。"
    )
    expected_parent = relative_or_absolute(set_dir, repo_root)
    problems: list[str] = []
    if not isinstance(warning, dict) or set(warning) != {
        "detail",
        "message",
        "remedy",
        "warning_code",
    }:
        problems.append("警告JSONのフィールドがCLI-22aと一致しません")
    else:
        detail = warning["detail"]
        temp_path = detail.get("temp_path") if isinstance(detail, dict) else None
        if warning["warning_code"] != "W-CLEANUP-01":
            problems.append("warning_codeがW-CLEANUP-01ではありません")
        if warning["message"] != expected_message:
            problems.append("messageがCLI-22aの固定値と一致しません")
        if warning["remedy"] != expected_remedy:
            problems.append("remedyがCLI-22aの固定値と一致しません")
        if not (
            isinstance(detail, dict)
            and set(detail) == {"temp_path"}
            and isinstance(temp_path, str)
            and Path(temp_path).parent.as_posix() == expected_parent
            and Path(temp_path).name.startswith(".set.json.tmp.")
        ):
            problems.append("detail.temp_pathが当該set-dirの一時リンクではありません")
    if not problems and canonical_bytes(warning) != completed.stderr:
        problems.append("警告JSONがJS-01正準バイト列ではありません")
    if problems:
        raise contract_failure("E-CONTRACT-01", problems)
    return warning


def finish_or_next(repo_root: Path, set_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    if state["unresolved_slots"]:
        slot_id = state["unresolved_slots"].pop(0)
        cap = min(2 * state["session"]["requested_count"], 20)
        if (
            state["session"]["mode"] == "proposal"
            and state["target_attempts_total"] < cap
            and state["supplement_pool"]
            and next_unused_qid(state) is not None
        ):
            target_ref = state["supplement_pool"].pop(0)
            return start_assignment(state, allocate_replacement(state, slot_id, target_ref))
        failed = state["last_failed_by_slot"][slot_id]
        return consultation(state, failed)
    if state["pending_assignments"]:
        assignment = state["pending_assignments"].pop(0)
        return start_assignment(state, assignment)
    return finalize_flow(repo_root, set_dir, state)


def handle_target_failure(
    repo_root: Path, set_dir: Path, state: dict[str, Any]
) -> dict[str, Any]:
    failed = dict(state["current"])
    slot_id = failed["slot_question_id"]
    state["last_failed_by_slot"][slot_id] = failed
    if state["session"]["mode"] == "explicit":
        return consultation(state, failed)
    state["unresolved_slots"].append(slot_id)
    return finish_or_next(repo_root, set_dir, state)


def finalize_flow(repo_root: Path, set_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    ensure_config_snapshot(repo_root, set_dir, state)
    if not state["accepted_slots"]:
        return terminal_payload(state, "aborted", reason="zero_accepted")
    completed = run_child(
        repo_root,
        "set_check.py",
        "--set-dir",
        relative_or_absolute(set_dir, repo_root),
    )
    require_child_success(completed, "E-CONTRACT-04")
    report = child_json(completed)
    write_audit(set_dir / "review" / "set_check.final.json", report)
    if report["verdict"] != "pass":
        problems = [
            f"{violation['code']} {violation['location']}: {violation['evidence']}"
            for violation in report["violations"]
        ] or ["最終set_checkのverdictがfailです"]
        failure = contract_failure(
            "E-CONTRACT-04",
            problems,
            detail={
                "accepted_question_ids": sorted(
                    state["accepted_slots"].values(), key=question_number
                ),
                "requested_count": state["session"]["requested_count"],
                "set_check_violations": report["violations"],
            },
        )
        return terminal_payload(
            state,
            "aborted",
            reason="final_set_check",
            error=failure.as_dict(),
        )
    final_ids = sorted(state["accepted_slots"].values(), key=question_number)
    metadata = build_finalize_metadata(
        state["session"], state["config_snapshot"], final_ids
    )
    finalized = run_child(
        repo_root,
        "finalize_set.py",
        "--set-dir",
        relative_or_absolute(set_dir, repo_root),
        stdin=canonical_bytes(metadata),
    )
    require_child_success(finalized, "E-CONTRACT-04")
    warning = finalized_warning(finalized, repo_root, set_dir)
    validated = run_child(
        repo_root,
        "validate.py",
        "--set-dir",
        relative_or_absolute(set_dir, repo_root),
    )
    require_child_success(validated, "E-CONTRACT-01")
    return terminal_payload(
        state,
        "completed",
        final_question_ids=final_ids,
        **(warning or {}),
    )


def initialize(repo_root: Path, set_dir: Path, input_path: str) -> dict[str, Any]:
    validate_flow_set_path(repo_root, set_dir, must_exist=False)
    session = parse_json_bytes(read_bytes(input_path), "init入力")
    resources = load_validated_resources(repo_root)
    session = validate_session(session, resources, set_dir)
    try:
        (set_dir / "review").mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise CliFailure(
            "E-ENV-05",
            f"E-ENV-05 セットディレクトリを作成できません: {set_dir}",
            detail={"error": str(exc), "path": str(set_dir)},
            remedy=REMEDIES["E-ENV-05"],
        ) from exc
    requested = session["requested_count"]
    assignments = []
    owner_by_question: dict[str, str] = {}
    slot_attempts: dict[str, list[str]] = {}
    target_by_question: dict[str, str] = {}
    for index, target_ref in enumerate(session["targets"][:requested], start=1):
        qid = f"q{index:02d}"
        assignments.append(
            {"question_id": qid, "slot_question_id": qid, "target_ref": target_ref}
        )
        owner_by_question[qid] = qid
        slot_attempts[qid] = [qid]
        target_by_question[qid] = target_ref
    state = {
        "accepted_slots": {},
        "config_snapshot": build_config_snapshot(
            resources["limits"], resources["proper_nouns"]["words"]
        ),
        "consultation": None,
        "current": None,
        "generation_attempts_total": 0,
        "generation_max": resources["limits"]["generation_max"],
        "generation_verdicts": [],
        "last_action": None,
        "last_failed_by_slot": {},
        "machine_check_dispute_count": 0,
        "outcome": "running",
        "owner_by_question": owner_by_question,
        "pending_assignments": assignments[1:],
        "regeneration_payloads": [],
        "session": session,
        "set_id": session["set_id"],
        "slot_attempts": slot_attempts,
        "supplement_pool": session["targets"][requested:] if session["mode"] == "proposal" else [],
        "target_by_question": target_by_question,
        "target_attempts_total": 0,
        "unresolved_slots": [],
    }
    first_action = start_assignment(state, assignments[0])
    write_exclusive(state_path(set_dir), canonical_bytes(state))
    return first_action


def submit_candidate(
    repo_root: Path, set_dir: Path, input_path: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = load_checked_state(repo_root, set_dir)
    if state["outcome"] != "running" or state["last_action"]["action"] != "generate_candidate":
        raise contract_failure("E-CONTRACT-01", ["candidateを受理できる状態ではありません"])
    current = state["current"]
    if not current["generation_counted"]:
        state["generation_attempts_total"] += 1
        current["generation_counted"] = True
    current["candidate_attempt"] += 1
    payload = read_bytes(input_path)
    candidate, diagnostic, invalid = validate_external(
        repo_root, "candidate", input_path, payload
    )
    qid = current["question_id"]
    generation = f"gen{current['generation_number']}"
    if candidate is not None and (
        candidate.get("question_id") != qid
        or candidate.get("target", {}).get("ref") != current["target_ref"]
    ):
        diagnostic = "candidateのquestion_idまたはtarget.refが現在の割当と一致しません"
        invalid = validation_failure(payload, diagnostic)
        candidate = None
    review_dir = set_dir / "review"
    if candidate is None:
        invalid_number = current["candidate_attempt"]
        if invalid_number > 2:
            raise contract_failure("E-CONTRACT-01", ["candidate再指示上限を超えました"])
        write_audit(
            review_dir / f"{qid}.{generation}.candidate.invalid{invalid_number}.txt",
            invalid,
        )
        cleanup_candidate_provider_input(input_path, set_dir)
        if invalid_number == 1:
            current["regeneration"] = candidate_validation_regeneration(
                current, diagnostic
            )
            return action_for_current(state), state
        action = advance_generation(
            state,
            "candidate_invalid",
            [],
            regeneration=candidate_validation_regeneration(current, diagnostic),
            audit_files=[
                f"review/{qid}.{generation}.candidate.invalid1.txt",
                f"review/{qid}.{generation}.candidate.invalid2.txt",
            ],
            diagnostic=diagnostic,
        )
        if action is None:
            action = handle_target_failure(repo_root, set_dir, state)
        return action, state
    candidate_path = review_dir / f"{qid}.{generation}.candidate.json"
    write_audit(candidate_path, candidate)
    cleanup_candidate_provider_input(input_path, set_dir)
    machine_completed = run_child(
        repo_root,
        "machine_check.py",
        "--candidate",
        relative_or_absolute(candidate_path, repo_root),
        "--set-id",
        state["set_id"],
        "--generation",
        generation,
        "--expected-format",
        state["session"]["format"],
        "--expected-level",
        state["session"]["level"]["value"],
        "--requested-count",
        str(state["session"]["requested_count"]),
    )
    require_child_success(machine_completed, "E-CONTRACT-01")
    machine = child_json(machine_completed)
    write_audit(review_dir / f"{qid}.{generation}.machine.json", machine)
    envelope = build_review_request(
        candidate,
        machine,
        state["set_id"],
        generation,
        limits=state["config_snapshot"]["limits"],
        proper_nouns=state["config_snapshot"]["proper_nouns"],
        topic=state["session"]["topic"],
    )
    raw_request_path = set_dir / ".staging" / f"{qid}.{generation}.request.raw.json"
    write_audit(raw_request_path, envelope)
    try:
        validated_request = run_child(
            repo_root,
            "validate.py",
            "--schema",
            "review_request",
            "--file",
            relative_or_absolute(raw_request_path, repo_root),
        )
        require_child_success(validated_request, "E-CONTRACT-01")
        request_path = review_dir / f"{qid}.{generation}.request.json"
        write_audit(request_path, envelope)
    finally:
        try:
            raw_request_path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise CliFailure(
                "E-ENV-05",
                f"E-ENV-05 review_request一時入力を削除できません: {raw_request_path}",
                detail={"error": str(exc), "path": str(raw_request_path)},
                remedy=REMEDIES["E-ENV-05"],
            ) from exc
    current["candidate"] = candidate
    current["machine"] = machine
    current["review_attempt"] = 0
    action = {
        "action": "run_review",
        "generation": generation,
        "question_id": qid,
        "request_path": relative_or_absolute(request_path, repo_root),
    }
    state["last_action"] = action
    return action, state


def submit_review(
    repo_root: Path,
    set_dir: Path,
    input_path: str | None,
    process_exit_code: int | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = load_state(set_dir)
    resources = ensure_config_snapshot(repo_root, set_dir, state)
    grammar_index = {
        entry["id"]: entry for entry in resources["grammar"]["entries"]
    }
    if state["outcome"] != "running" or state["last_action"]["action"] != "run_review":
        raise contract_failure("E-CONTRACT-01", ["reviewを受理できる状態ではありません"])
    current = state["current"]
    current["review_attempt"] += 1
    if process_exit_code is not None:
        payload = read_bytes("-")
        review = None
        diagnostic = f"レビュアープロセスが終了コード{process_exit_code}で失敗しました"
        invalid = process_failure(process_exit_code, payload)
    else:
        assert input_path is not None
        payload = read_bytes(input_path)
        review, diagnostic, invalid = validate_external(
            repo_root, "review_result", input_path, payload
        )
    qid = current["question_id"]
    generation = f"gen{current['generation_number']}"
    if review is not None and (
        review.get("set_id") != state["set_id"]
        or review.get("question_id") != qid
        or review.get("generation") != generation
    ):
        diagnostic = "review_resultの識別子が現在のrequestと一致しません"
        invalid = validation_failure(payload, diagnostic)
        review = None
    if review is not None:
        semantic_problems = review_semantic_problems(
            review,
            current["candidate"],
            state["session"]["topic"],
            current["machine"],
            grammar_index,
        )
        if semantic_problems:
            diagnostic = "review_resultの意味契約に適合しません: " + "; ".join(
                semantic_problems
            )
            invalid = validation_failure(payload, diagnostic)
            review = None
    review_dir = set_dir / "review"
    if review is None:
        invalid_number = current["review_attempt"]
        if invalid_number > 3:
            raise contract_failure("E-CONTRACT-01", ["review再実行上限を超えました"])
        write_audit(
            review_dir / f"{qid}.{generation}.review.invalid{invalid_number}.txt",
            invalid,
        )
        if invalid_number < 3:
            action = dict(state["last_action"])
            action["retry_number"] = invalid_number
            state["last_action"] = action
            return action, state
        state["generation_verdicts"].append(
            {
                "generation": generation,
                "question_id": qid,
                "reason": "review_invalid",
                "verdict": "aborted",
            }
        )
        invalid_audits = [
            f"review/{qid}.{generation}.review.invalid{number}.txt"
            for number in range(1, 4)
        ]
        failure = contract_failure(
            "E-CONTRACT-01",
            [
                "review_result schema "
                f"{schema_version(repo_root, 'review_result.schema.json')} の受理が"
                "3回連続で失敗しました: "
                + ", ".join(invalid_audits)
            ],
            detail={
                "invalid_audits": invalid_audits,
                "schema": "review_result",
                "schema_version": schema_version(
                    repo_root, "review_result.schema.json"
                ),
            },
        )
        return terminal_payload(
            state,
            "aborted",
            reason="review_invalid",
            error=failure.as_dict(),
        ), state
    write_audit(review_dir / f"{qid}.{generation}.review.json", review)
    state["machine_check_dispute_count"] += len(review["machine_check_disputes"])
    machine = current["machine"]
    if machine["verdict"] == "fail" or review["verdict"] == "fail":
        violations = [*machine["violations"], *review["violations"]]
        action = advance_generation(
            state,
            "machine_or_review",
            violations,
            regeneration=reviewed_regeneration(current, review),
            audit_files=[
                f"review/{qid}.{generation}.candidate.json",
                f"review/{qid}.{generation}.machine.json",
                f"review/{qid}.{generation}.request.json",
                f"review/{qid}.{generation}.review.json",
            ],
        )
        if action is None:
            action = handle_target_failure(repo_root, set_dir, state)
        return action, state
    checked = run_child(
        repo_root,
        "set_check.py",
        "--set-dir",
        relative_or_absolute(set_dir, repo_root),
        "--target",
        qid,
    )
    require_child_success(checked, "E-CONTRACT-01")
    set_report = child_json(checked)
    write_audit(review_dir / f"set_check.{qid}.{generation}.json", set_report)
    if set_report["verdict"] == "fail":
        action = advance_generation(
            state,
            "set_check",
            set_report["violations"],
            regeneration=reviewed_regeneration(
                current,
                review,
                set_check_violations=set_report["violations"],
            ),
            audit_files=[
                f"review/{qid}.{generation}.candidate.json",
                f"review/{qid}.{generation}.machine.json",
                f"review/{qid}.{generation}.request.json",
                f"review/{qid}.{generation}.review.json",
                f"review/set_check.{qid}.{generation}.json",
            ],
        )
        if action is None:
            action = handle_target_failure(repo_root, set_dir, state)
        return action, state
    slot_id = current["slot_question_id"]
    state["accepted_slots"][slot_id] = qid
    state["generation_verdicts"].append(
        {
            "generation": generation,
            "question_id": qid,
            "reason": "accepted",
            "verdict": "pass",
        }
    )
    write_audit(
        review_dir / f"slot.{slot_id}.outcome.json",
        build_slot_outcome(
            state["set_id"], slot_id, state["slot_attempts"][slot_id], qid
        ),
    )
    action = finish_or_next(repo_root, set_dir, state)
    return action, state


def decide(
    repo_root: Path,
    set_dir: Path,
    decision: str,
    target_ref: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = load_checked_state(repo_root, set_dir)
    if state["outcome"] != "teacher_consult" or state["consultation"] is None:
        raise contract_failure("E-CONTRACT-01", ["教師判断を受理できる状態ではありません"])
    consultation_data = state["consultation"]
    if decision not in consultation_data["choices"]:
        raise CliFailure(
            "E-INPUT-04",
            f"E-INPUT-04 現在提示されていない教師判断です: {decision}",
            detail={"allowed": consultation_data["choices"], "received": decision},
            remedy=REMEDIES["E-INPUT-04"],
        )
    state["outcome"] = "running"
    state["consultation"] = None
    slot_id = consultation_data["slot_question_id"]
    if decision == "abort":
        return terminal_payload(state, "aborted", reason="teacher_abort"), state
    if decision == "alternative":
        if not target_ref:
            raise CliFailure(
                "E-INPUT-04",
                "E-INPUT-04 alternativeには--target-refが必要です",
                detail={"field": "target_ref"},
                remedy=REMEDIES["E-INPUT-04"],
            )
        assignment = allocate_replacement(state, slot_id, target_ref)
        return start_assignment(state, assignment), state
    write_audit(
        set_dir / "review" / f"slot.{slot_id}.outcome.json",
        build_slot_outcome(
            state["set_id"],
            slot_id,
            state["slot_attempts"][slot_id],
            None,
            reduced=True,
        ),
    )
    state["unresolved_slots"] = [
        value for value in state["unresolved_slots"] if value != slot_id
    ]
    return finish_or_next(repo_root, set_dir, state), state


def run(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    repo_root = Path.cwd()
    set_dir = Path(args.set_dir)
    if not set_dir.is_absolute():
        set_dir = repo_root / set_dir
    if args.command == "init":
        require_basic_environment(repo_root)
        action = initialize(repo_root, set_dir, args.file)
        emit_json(action)
        return 0
    cleanup_allowed = False
    try:
        validate_flow_set_path(repo_root, set_dir, must_exist=True)
        cleanup_allowed = True
        require_basic_environment(repo_root)
        if args.command == "status":
            emit_json(load_checked_state(repo_root, set_dir)["last_action"])
            return 0
        if args.command == "review-preflight":
            emit_json(review_preflight(repo_root, set_dir, args.request))
            return 0
        if args.command == "candidate":
            action, state = submit_candidate(repo_root, set_dir, args.file)
        elif args.command == "review":
            action, state = submit_review(
                repo_root, set_dir, args.file, args.process_failure
            )
        else:
            action, state = decide(repo_root, set_dir, args.decision, args.target_ref)
        terminal = action["action"] in {"completed", "aborted"}
        if terminal:
            cleanup_state(set_dir)
        else:
            persist(set_dir, state)
        emit_json(action)
        return 0
    except Exception:
        # S80後は定義済み停止・内部バグとも再開不能にし、監査正本は保持する。
        if cleanup_allowed:
            cleanup_state(set_dir)
        raise


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
