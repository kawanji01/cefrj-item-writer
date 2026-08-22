"""候補生成と独立レビューだけをfixtureへ置換する決定的リプレイ。"""

from __future__ import annotations

import sys
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from tests.support import FIXTURES, ROOT, load_json, run_cli, stdout_json, write_json


SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from flow_control import build_session_input  # noqa: E402


SET_ID = "20990101-000000-rpl1"


@dataclass
class ReplayResult:
    attempts_total: int
    audit_files: list[str]
    consultation: dict[str, Any] | None
    generation_verdicts: list[dict[str, Any]]
    outcome: str
    provider_requests: list[tuple[str, str, str]]
    regeneration_payloads: list[dict[str, Any]]
    set_document: dict[str, Any] | None
    set_questions: list[str]
    teacher_decisions: list[dict[str, Any]]


class FixtureProvider:
    """RPL-R-01の2境界だけをシナリオfixtureへ差し替える。"""

    def __init__(self, scenario: dict[str, Any]) -> None:
        self.candidates: dict[tuple[str, str], deque[str]] = defaultdict(deque)
        self.reviews: dict[tuple[str, str], deque[str]] = defaultdict(deque)
        self.requests: list[tuple[str, str, str]] = []
        for step in scenario["steps"]:
            key = (step["question_id"], step["gen"])
            self.candidates[key].extend([step["candidate"], *step["candidate_retries"]])
            self.reviews[key].extend([step["review"], *step["review_retries"]])

    def candidate(self, action: dict[str, Any]) -> Path:
        key = (action["question_id"], action["generation"])
        if not self.candidates[key]:
            raise AssertionError(f"candidate fixtureが不足しています: {key}")
        self.requests.append(("candidate", *key))
        return FIXTURES / "candidates" / self.candidates[key].popleft()

    def review(self, action: dict[str, Any]) -> Path:
        key = (action["question_id"], action["generation"])
        if not self.reviews[key]:
            raise AssertionError(f"review fixtureが不足しています: {key}")
        self.requests.append(("review", *key))
        return FIXTURES / "reviews" / self.reviews[key].popleft()


def make_temporary_repo(tmp_path: Path) -> Path:
    """実output/と分離したRPL-R-04専用リポジトリを作る。"""

    repo = tmp_path / "replay-repo"
    repo.mkdir()
    (repo / "output").mkdir()
    for name in ("agent", "data", "schemas", "scripts", "templates"):
        (repo / name).symlink_to(ROOT / name, target_is_directory=True)
    return repo


def flow_cli(repo: Path, *arguments: str) -> dict[str, Any]:
    completed = run_cli(
        "scripts/flow_control.py",
        *arguments,
        cwd=repo,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr.decode("utf-8", errors="backslashreplace"))
    return stdout_json(completed)


@contextmanager
def replay_scenario(
    path: Path, tmp_path: Path
) -> Iterator[tuple[ReplayResult, Path]]:
    scenario = load_json(path)
    repo = make_temporary_repo(tmp_path)
    set_dir = repo / "output" / SET_ID
    provider = FixtureProvider(scenario)
    teacher_decisions = deque(scenario["teacher_decisions"])
    consumed_teacher_decisions: list[dict[str, Any]] = []
    session = build_session_input(
        scenario["request"],
        SET_ID,
        created_at="2099-01-01T00:00:00+09:00",
        model="m8-test",
        tool="codex",
    )
    session_path = repo / "session.json"
    write_json(session_path, session)
    action = flow_cli(
        repo,
        "init",
        "--set-dir",
        f"output/{SET_ID}",
        "--file",
        str(session_path),
    )
    for _event in range(200):
        if action["action"] == "generate_candidate":
            action = flow_cli(
                repo,
                "candidate",
                "--set-dir",
                f"output/{SET_ID}",
                "--file",
                str(provider.candidate(action)),
            )
            continue
        if action["action"] == "run_review":
            action = flow_cli(
                repo,
                "review",
                "--set-dir",
                f"output/{SET_ID}",
                "--file",
                str(provider.review(action)),
            )
            continue
        if action["action"] == "teacher_consult" and teacher_decisions:
            event = teacher_decisions.popleft()
            if set(event) != {"decision", "slot_question_id", "target_ref"}:
                raise AssertionError(f"教師判断イベントのフィールドが不正です: {event}")
            consultation = action["consultation"]
            if event["slot_question_id"] != consultation["slot_question_id"]:
                raise AssertionError(
                    "教師判断イベントのslotが提示中の照会と一致しません: "
                    f"event={event['slot_question_id']}, "
                    f"consultation={consultation['slot_question_id']}"
                )
            if event["decision"] not in consultation["choices"]:
                raise AssertionError(
                    f"教師判断イベントが提示済みchoicesにありません: {event['decision']}"
                )
            decision_arguments = [
                "decide",
                "--set-dir",
                f"output/{SET_ID}",
                "--decision",
                event["decision"],
            ]
            if event["decision"] == "alternative":
                if not isinstance(event["target_ref"], str) or not event["target_ref"]:
                    raise AssertionError("alternative教師判断には非空target_refが必要です")
                decision_arguments.extend(["--target-ref", event["target_ref"]])
            elif event["target_ref"] is not None:
                raise AssertionError("reduce/abort教師判断のtarget_refはnullでなければなりません")
            action = flow_cli(repo, *decision_arguments)
            consumed_teacher_decisions.append(event)
            continue
        break
    else:
        raise AssertionError(f"フローが200イベント以内に停止しません: {path.name}")

    if action["action"] not in {"completed", "aborted", "teacher_consult"}:
        raise AssertionError(f"未知の終端actionです: {action['action']}")
    if teacher_decisions:
        raise AssertionError(
            f"未消費の教師判断イベントがあります: {list(teacher_decisions)}"
        )
    set_document = load_json(set_dir / "set.json") if (set_dir / "set.json").is_file() else None
    review_dir = set_dir / "review"
    result = ReplayResult(
        attempts_total=action["attempts_total"],
        audit_files=sorted(item.name for item in review_dir.iterdir()),
        consultation=action.get("consultation"),
        generation_verdicts=action["generation_verdicts"],
        outcome=action["outcome"],
        provider_requests=provider.requests,
        regeneration_payloads=action["regeneration_payloads"],
        set_document=set_document,
        set_questions=(
            [question["question_id"] for question in set_document["questions"]]
            if set_document is not None
            else []
        ),
        teacher_decisions=consumed_teacher_decisions,
    )
    yield result, set_dir
