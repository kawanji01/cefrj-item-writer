#!/usr/bin/env python3
"""M8の初回テスト資産を正本文書と決定的CLIから生成する。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
PYTHON = ROOT / ".venv" / "bin" / "python"
SET_ID = "20990101-000000-rpl1"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
FORMATS = (
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


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(name: str, value: Any) -> None:
    schema = load_json(ROOT / "schemas" / f"{name}.schema.json")
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda error: list(error.path))
    if errors:
        raise RuntimeError(f"{name} fixture is invalid: {errors[0].message}")


def official_candidates() -> dict[str, dict[str, Any]]:
    text = (ROOT / "docs" / "question-generation-spec.md").read_text(encoding="utf-8")
    found: dict[str, dict[str, Any]] = {}
    for block in re.findall(r"```json\n(\{.*?\})\n```", text, re.DOTALL):
        value = json.loads(block)
        fmt = value.get("format")
        if fmt in FORMATS:
            found[fmt] = value
    if tuple(fmt for fmt in FORMATS if fmt not in found):
        raise RuntimeError("公式9形式候補を抽出できません")
    for candidate in found.values():
        validate("candidate", candidate)
    replacements = {
        "lex:borrow:verb": {
            "anchor": {
                "entry_id": "lex:achieve:verb",
                "headword": "achieve",
                "level": "A2",
                "pos": "verb",
            },
            "gloss": "〜を達成する",
            "is_correct": False,
            "text": "〜を達成する",
        },
        "lex:collect:verb": {
            "anchor": {
                "entry_id": "lex:advise:verb",
                "headword": "advise",
                "level": "A2",
                "pos": "verb",
            },
            "gloss": "〜に助言する",
            "is_correct": False,
            "text": "〜に助言する",
        },
        "lex:culture:noun": {
            "anchor": {
                "entry_id": "lex:experience:noun",
                "headword": "experience",
                "level": "A2",
                "pos": "noun",
            },
            "gloss": "経験",
            "is_correct": False,
            "text": "experience",
        },
    }
    for fmt in ("vocab_mcq_en2ja", "vocab_mcq_ja2en"):
        for index, choice in enumerate(found[fmt]["body"]["choices"]):
            replacement = replacements.get(choice["anchor"]["entry_id"])
            if replacement is not None:
                found[fmt]["body"]["choices"][index] = replacement
        validate("candidate", found[fmt])
    return found


def flash_candidate(
    question_id: str,
    headword: str,
    pos: str,
    gloss: str,
    english: str,
    japanese: str,
    *,
    level: str = "A2",
    fmt: str = "vocab_flashcard_en2ja",
    surface: str | None = None,
) -> dict[str, Any]:
    slug = "modal-auxiliary" if pos == "modal auxiliary" else pos.replace(" ", "-")
    value = {
        "body": {
            "example": {"en": english, "ja": japanese},
            "gloss": gloss,
            "headword": headword,
            "pos": pos,
            "target_surface": surface or headword,
        },
        "format": fmt,
        "level": {"scale": "cefr", "value": level},
        "question_id": question_id,
        "target": {
            "display_name": headword,
            "ref": f"lex:{headword}:{slug}",
            "type": "lexical",
        },
    }
    validate("candidate", value)
    return value


def run_machine(
    candidate_path: Path,
    *,
    expected_format: str,
    expected_level: str,
    requested_count: int = 1,
    set_id: str = SET_ID,
    generation: str = "gen1",
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            str(PYTHON),
            "scripts/machine_check.py",
            "--candidate",
            str(candidate_path.relative_to(ROOT)),
            "--set-id",
            set_id,
            "--generation",
            generation,
            "--expected-format",
            expected_format,
            "--expected-level",
            expected_level,
            "--requested-count",
            str(requested_count),
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    value = json.loads(completed.stdout)
    validate("machine_report", value)
    return value


def pass_review(
    question_id: str = "q01",
    generation: str = "gen1",
    *,
    set_id: str = SET_ID,
) -> dict[str, Any]:
    value = {
        "checks": [
            {"check_id": f"CHK-{index:02d}", "note": "テスト用記録で適用項目を確認しました。", "result": "pass"}
            for index in range(1, 20)
        ],
        "generation": generation,
        "machine_check_disputes": [],
        "question_id": question_id,
        "schema_version": "1.0.0",
        "sentence_grammar_inventory": [],
        "set_id": set_id,
        "verdict": "pass",
        "violations": [],
    }
    validate("review_result", value)
    return value


def fail_review(
    question_id: str = "q01",
    generation: str = "gen1",
    *,
    set_id: str = SET_ID,
) -> dict[str, Any]:
    value = pass_review(question_id, generation, set_id=set_id)
    value["verdict"] = "fail"
    value["checks"][2] = {
        "check_id": "CHK-03",
        "note": "指定レベルを超える文法構造を検出しました。",
        "result": "fail",
    }
    value["violations"] = [
        {
            "actual_level": "A2.1",
            "code": "CHK-03",
            "evidence": "テスト用の構造化レビュー指摘です。",
            "expected_level": "A1.3",
            "location": "body.example.en のテスト対象構造",
            "suggestion": "指定レベル内の文へ置き換えてください。",
        }
    ]
    validate("review_result", value)
    return value


def review_request(
    candidate: dict[str, Any],
    machine: dict[str, Any],
    *,
    set_id: str = SET_ID,
    generation: str = "gen1",
) -> dict[str, Any]:
    limits = load_json(ROOT / "data" / "config" / "limits.json")
    proper = load_json(ROOT / "data" / "config" / "proper_nouns.json")["words"]
    band = candidate["level"]["value"].split(".")[0]
    grammar_max = (
        {"A1": "A1.3", "A2": "A2.2", "B1": "B1.2", "B2": "B2.2"}[band]
        if candidate["format"].startswith("vocab_")
        else candidate["level"]["value"]
    )
    value = {
        "candidate": candidate,
        "constraints_snapshot": {
            "limits": {
                "explanation_char_limit": None if candidate["format"].startswith("vocab_") else limits["explanation_char_limits"][candidate["explanation"]["type"]],
                "sentence_word_limit": limits["sentence_word_limits"][band],
            },
            "proper_nouns": proper,
            "topic": None,
        },
        "format": candidate["format"],
        "generation": generation,
        "level": candidate["level"],
        "level_limits": {"grammar_intro_level_max": grammar_max, "vocabulary_level_max": band},
        "machine_report": machine,
        "question_id": candidate["question_id"],
        "readable_resources": [
            "data/normalized/lexicon.json",
            "data/normalized/grammar.json",
            "data/normalized/meta.json",
            "data/config/limits.json",
            "data/config/proper_nouns.json",
            "docs/cefrj-validation-spec.md",
            "docs/subagent-review-spec.md",
            "agent/reviewer-core.md",
        ],
        "schema_version": "1.0.0",
        "set_id": set_id,
        "target_ref": candidate["target"]["ref"],
    }
    validate("review_request", value)
    return value


def run_cli(
    arguments: list[str],
    *,
    stdin: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [str(PYTHON), *arguments],
        cwd=ROOT,
        check=True,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def build_golden_set(candidate: dict[str, Any], index: int) -> Path:
    """正式な決定的CLI列を通して1問セットを確定し、そのset.jsonを返す。"""

    set_id = f"20260819-1200{index:02d}-g{index:03d}"
    set_dir = ROOT / "output" / set_id
    if set_dir.exists() or set_dir.is_symlink():
        raise RuntimeError(f"golden生成用パスが既に存在します: {set_dir}")
    review_dir = set_dir / "review"
    created = False
    try:
        review_dir.mkdir(parents=True)
        created = True
        candidate_path = review_dir / "q01.gen1.candidate.json"
        write_json(candidate_path, candidate)
        run_cli(
            [
                "scripts/validate.py",
                "--schema",
                "candidate",
                "--file",
                str(candidate_path.relative_to(ROOT)),
            ]
        )

        machine = run_machine(
            candidate_path,
            expected_format=candidate["format"],
            expected_level=candidate["level"]["value"],
            set_id=set_id,
        )
        if machine["verdict"] != "pass":
            raise RuntimeError(f"公式候補のmachine_checkがfailです: {candidate['format']}")
        write_json(review_dir / "q01.gen1.machine.json", machine)
        request = review_request(candidate, machine, set_id=set_id)
        write_json(review_dir / "q01.gen1.request.json", request)
        write_json(review_dir / "q01.gen1.review.json", pass_review(set_id=set_id))

        incremental = run_cli(
            [
                "scripts/set_check.py",
                "--set-dir",
                str(set_dir.relative_to(ROOT)),
                "--target",
                "q01",
            ]
        )
        incremental_value = json.loads(incremental.stdout)
        validate("machine_report", incremental_value)
        if incremental_value["verdict"] != "pass":
            raise RuntimeError(f"公式候補の増分set_checkがfailです: {candidate['format']}")
        (review_dir / "set_check.q01.gen1.json").write_bytes(incremental.stdout)
        write_json(
            review_dir / "slot.q01.outcome.json",
            {
                "accepted_question_id": "q01",
                "attempted_question_ids": ["q01"],
                "set_id": set_id,
                "slot_question_id": "q01",
                "status": "accepted",
                "teacher_decision": None,
            },
        )

        final_check = run_cli(
            [
                "scripts/set_check.py",
                "--set-dir",
                str(set_dir.relative_to(ROOT)),
            ]
        )
        final_value = json.loads(final_check.stdout)
        validate("machine_report", final_value)
        if final_value["verdict"] != "pass":
            raise RuntimeError(f"公式候補の最終set_checkがfailです: {candidate['format']}")
        (review_dir / "set_check.final.json").write_bytes(final_check.stdout)

        metadata = {
            "config_snapshot": {
                "limits": load_json(ROOT / "data" / "config" / "limits.json"),
                "proper_nouns": load_json(ROOT / "data" / "config" / "proper_nouns.json")["words"],
            },
            "created_at": f"2026-08-19T12:00:{index:02d}+09:00",
            "final_question_ids": ["q01"],
            "format": candidate["format"],
            "level": candidate["level"],
            "mode": "proposal",
            "model": "m8-fixture",
            "preferred_proper_nouns": [],
            "requested_count": 1,
            "set_id": set_id,
            "tool": "codex",
            "topic": None,
        }
        run_cli(
            ["scripts/finalize_set.py", "--set-dir", str(set_dir.relative_to(ROOT))],
            stdin=canonical_bytes(metadata),
        )
        set_path = set_dir / "set.json"
        run_cli(
            [
                "scripts/validate.py",
                "--schema",
                "set",
                "--file",
                str(set_path.relative_to(ROOT)),
            ]
        )
        run_cli(
            ["scripts/validate.py", "--set-dir", str(set_dir.relative_to(ROOT))]
        )
        target = TESTS / "golden" / "sets" / f"{candidate['format']}.set.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(set_path, target)
        return target
    finally:
        if created:
            shutil.rmtree(set_dir)


def add_candidate(
    cases: list[dict[str, Any]],
    name: str,
    candidate: dict[str, Any],
    purpose: str,
    expected: str,
    test_ids: list[str],
) -> None:
    validate("candidate", candidate)
    write_json(TESTS / "fixtures" / "candidates" / name, candidate)
    cases.append({"expected": expected, "file": name, "purpose": purpose, "test_ids": test_ids})


def write_huge_integer_candidate(path: Path, candidate: dict[str, Any], digits: int) -> None:
    base = canonical_bytes(candidate).decode("utf-8")
    if not base.endswith("}\n"):
        raise RuntimeError("candidateの正準JSON終端が不正です")
    integer = "1" + ("0" * (digits - 1))
    write_text(path, f'{base[:-2]},\n  "unexpected_m8_integer": {integer}\n}}\n')


def make_machine_candidates(official: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for fmt in FORMATS:
        add_candidate(cases, f"official_{fmt}.json", official[fmt], f"正本文書の{fmt}妥当例", "candidateスキーマ合格", ["CI-SCH-02", "CI-SCH-04"])

    exact10 = flash_candidate("q01", "book", "noun", "本", "I have one book for my English class at school.", "私は学校の英語の授業用に本を1冊持っています。", level="A1")
    over11 = copy.deepcopy(exact10)
    over11["body"]["example"]["en"] = "I have one new book for my English class at school."
    add_candidate(cases, "mch_01_word_limit_11.json", over11, "A1の11トークン例文", "V-LEN-01", ["CI-MCH-01"])
    add_candidate(cases, "mch_02_word_limit_10.json", exact10, "A1の10トークン境界", "V-LEN-01なし", ["CI-MCH-02"])

    unknown = flash_candidate("q01", "book", "noun", "本", "This book is from Helsinki.", "この本はヘルシンキから来ました。", level="A1")
    add_candidate(cases, "mch_03_unknown_helsinki.json", unknown, "allowlist外Helsinki", "V-LEX-01", ["CI-MCH-03"])
    allowed = flash_candidate("q01", "book", "noun", "本", "This book is from Kyoto.", "この本は京都から来ました。", level="A1")
    add_candidate(cases, "mch_04_allowlist_kyoto.json", allowed, "allowlist内Kyoto", "V-LEX-01なし", ["CI-MCH-04"])
    exempt = flash_candidate("q01", "book", "noun", "本", "I can't buy 2 books.", "私は本を2冊買えません。", level="A1", surface="books")
    add_candidate(cases, "mch_05_exemptions.json", exempt, "数字・記号・句読点・縮約", "免除由来違反なし", ["CI-MCH-05"])
    high = flash_candidate("q01", "book", "noun", "本", "I abandon this book.", "私はこの本を捨てます。", level="A1")
    add_candidate(cases, "mch_06_high_level_abandon.json", high, "A1例文中のB1 abandon", "V-LEX-02", ["CI-MCH-06"])
    zero = flash_candidate("q01", "book", "noun", "本", "I like this pen.", "私はこのペンが好きです。", level="A1", surface="book")
    twice = flash_candidate("q01", "book", "noun", "本", "This book is a good book.", "これはよい本です。", level="A1")
    inflected = flash_candidate("q01", "book", "noun", "本", "I have two books.", "私は本を2冊持っています。", level="A1", surface="books")
    add_candidate(cases, "mch_07_target_zero.json", zero, "対象語0回", "V-TGT-02", ["CI-MCH-07"])
    add_candidate(cases, "mch_07_target_twice.json", twice, "対象語2回", "V-TGT-02", ["CI-MCH-07"])
    add_candidate(cases, "mch_07_target_inflected.json", inflected, "対象語活用形1回", "V-TGT-02なし", ["CI-MCH-07"])
    multiword = flash_candidate("q01", "CD player", "noun", "CDプレーヤー", "This CD player is new.", "このCDプレーヤーは新しいです。", level="A1")
    add_candidate(cases, "mch_08_multiword_cd_player.json", multiword, "複数語見出しCD player", "単体由来違反なし", ["CI-MCH-08"])

    bad_anchor = copy.deepcopy(official["vocab_mcq_en2ja"])
    bad_anchor["body"]["choices"][0]["anchor"]["headword"] = "abandon"
    add_candidate(cases, "mch_10_bad_anchor.json", bad_anchor, "誤答由来の記録矛盾", "V-DIS-01", ["CI-MCH-10"])
    relaxed = copy.deepcopy(official["vocab_mcq_ja2en"])
    relaxed["body"]["pos_pool_relaxed"] = True
    relaxed["body"]["choices"][0] = {
        "anchor": {"entry_id": "lex:hundred:number", "headword": "hundred", "level": "A2", "pos": "number"},
        "gloss": "100",
        "is_correct": False,
        "text": "hundred",
    }
    no_flag = copy.deepcopy(relaxed)
    no_flag["body"]["pos_pool_relaxed"] = False
    add_candidate(cases, "mch_11_same_pos.json", official["vocab_mcq_ja2en"], "同レベル同品詞誤答", "V-DIS-02なし", ["CI-MCH-11"])
    add_candidate(cases, "mch_11_relaxed_number.json", relaxed, "noun-number互換品詞緩和", "V-DIS-02なし", ["CI-MCH-11"])
    add_candidate(cases, "mch_11_missing_relax_flag.json", no_flag, "異品詞なのに緩和記録なし", "V-DIS-02", ["CI-MCH-11"])

    context_ok = copy.deepcopy(official["grammar_mcq"])
    context_ok["body"]["context_sentence"] = "My brother is at school."
    context_ok["body"]["context_required_by"] = "前文が肯定平叙"
    context_bad = copy.deepcopy(context_ok)
    context_bad["body"]["context_required_by"] = None
    add_candidate(cases, "mch_13_context_recorded.json", context_ok, "先行文脈記録あり", "V-SENT-01なし", ["CI-MCH-13"])
    add_candidate(cases, "mch_13_context_missing_record.json", context_bad, "先行文脈要求元記録なし", "V-SENT-01", ["CI-MCH-13"])
    reorder_same = copy.deepcopy(official["grammar_reorder"])
    reorder_same["body"]["tokens_shuffled"] = ["look", "at", "that", "big", "tree"]
    add_candidate(cases, "mch_14_reorder_same.json", reorder_same, "整序提示順が正解順と同一", "V-ORD-02", ["CI-MCH-14"])

    cond_base = copy.deepcopy(official["grammar_cloze"])
    cond_q04 = copy.deepcopy(cond_base)
    cond_q04["question_id"] = "q04"
    cond_q07 = copy.deepcopy(cond_base)
    cond_q07["question_id"] = "q07"
    cond_q20 = copy.deepcopy(cond_base)
    cond_q20["question_id"] = "q20"
    add_candidate(cases, "mch_16_condition_match.json", cond_base, "確定条件一致", "V-COND-01なし", ["CI-MCH-16"])
    add_candidate(cases, "mch_16_supplement_q04.json", cond_q04, "N=3の補充ID q04", "V-COND-01なし", ["CI-MCH-16"])
    add_candidate(cases, "mch_16_over_limit_q07.json", cond_q07, "N=3の上限超過ID q07", "V-COND-01", ["CI-MCH-16"])
    add_candidate(cases, "mch_16_upper_bound_q20.json", cond_q20, "N=20の上限q20", "V-COND-01なし", ["CI-MCH-16"])

    abandon = copy.deepcopy(official["vocab_flashcard_en2ja"])
    abandon["body"]["example"]["en"] = "They had to abandon their old car in the heavy snow today."
    grammar_high = copy.deepcopy(official["grammar_example_selfcheck"])
    distractor_high = copy.deepcopy(official["vocab_mcq_ja2en"])
    add_candidate(cases, "mch_17_expected_a1_abandon.json", abandon, "候補B1・期待A1の全件列挙", "V-COND-01/V-LEN-01/V-LEX-02/V-TGT-03", ["CI-MCH-17"])
    add_candidate(cases, "mch_17_expected_a11_grammar.json", grammar_high, "候補B2.2・期待A1.1の文法対象", "V-COND-01/V-TGT-01", ["CI-MCH-17"])
    add_candidate(cases, "mch_17_expected_a1_distractors.json", distractor_high, "候補A2・期待A1の誤答アンカー", "V-COND-01/V-DIS-02", ["CI-MCH-17"])

    for digits in (4300, 4301, 5000):
        name = f"mch_18_integer_{digits}.json"
        write_huge_integer_candidate(
            TESTS / "fixtures" / "candidates" / name,
            official["grammar_cloze"],
            digits,
        )
        cases.append(
            {
                "expected": "スキーマ検証へ進む" if digits == 4300 else "E-INPUT-03",
                "file": name,
                "purpose": f"意図したトップレベル余分フィールドの{digits}桁整数",
                "test_ids": ["CI-MCH-18"],
            }
        )

    inconsistent = copy.deepcopy(official["grammar_cloze"])
    inconsistent["format"] = "grammar_mcq"
    write_json(TESTS / "fixtures" / "candidates" / "sch_04_inconsistent_format.json", inconsistent)
    cases.append(
        {
            "expected": "E-CONTRACT-01",
            "file": "sch_04_inconsistent_format.json",
            "purpose": "意図したformatとbodyの共用体不整合",
            "test_ids": ["CI-SCH-04"],
        }
    )
    for name, invalid in (
        ("rpl_06_missing_question_id.json", {key: value for key, value in official["grammar_cloze"].items() if key != "question_id"}),
        ("rpl_06_question_id_type.json", {**official["grammar_cloze"], "question_id": 1}),
    ):
        write_json(TESTS / "fixtures" / "candidates" / name, invalid)
        cases.append(
            {
                "expected": "candidateスキーマ不通過",
                "file": name,
                "purpose": "RPL-06で意図した生成候補スキーマ不通過",
                "test_ids": ["RPL-06"],
            }
        )

    compat = copy.deepcopy(official["grammar_cloze"])
    write_json(TESTS / "fixtures" / "candidates" / "compat" / "grammar_cloze.json", compat)
    cases.append({"expected": "machineゴールデン一致", "file": "compat/grammar_cloze.json", "purpose": "ホスト・OS互換用候補", "test_ids": ["CI-CLI-02"]})

    replay_values = [
        ("q01", "accept", "verb", "〜を受け入れる", "I will accept your plan today.", "私は今日あなたの計画を受け入れます。"),
        ("q02", "ability", "noun", "能力", "She has the ability to help us.", "彼女には私たちを助ける能力があります。"),
        ("q03", "abroad", "adverb", "外国で、外国へ", "My sister will study abroad next year.", "姉は来年外国で勉強します。"),
        ("q04", "collect", "verb", "〜を集める", "We collect old books at school.", "私たちは学校で古い本を集めます。"),
        ("q05", "invite", "verb", "〜を招待する", "I will invite my friend to dinner.", "私は友達を夕食に招待します。"),
        ("q06", "borrow", "verb", "〜を借りる", "Can I borrow your pen today?", "今日あなたのペンを借りてもよいですか。"),
    ]
    for qid, headword, pos, gloss, en, ja in replay_values:
        value = flash_candidate(qid, headword, pos, gloss, en, ja)
        add_candidate(cases, f"replay_{qid}_pass.json", value, f"リプレイ用{qid}合格候補", "machine pass", ["RPL-01", "RPL-02", "RPL-03", "RPL-04", "RPL-07", "RPL-09", "RPL-10"])
    conflict_q01 = flash_candidate("q01", "accept", "verb", "〜を受け入れる", "I accept your ability.", "私はあなたの能力を受け入れます。")
    conflict_q02 = flash_candidate("q02", "ability", "noun", "能力", "I accept your ability.", "私はあなたの能力を受け入れます。")
    add_candidate(cases, "replay_q01_conflict.json", conflict_q01, "例文使い回しの先行候補", "machine pass", ["RPL-08"])
    add_candidate(cases, "replay_q02_conflict.json", conflict_q02, "例文使い回しの後続候補", "set_check V-SET-02", ["RPL-08"])

    duplicate_q02 = flash_candidate(
        "q02",
        "accept",
        "verb",
        "〜を受け入れる",
        "We accept the new plan at school.",
        "私たちは学校で新しい計画を受け入れます。",
    )
    add_candidate(cases, "set_duplicate_q02.json", duplicate_q02, "同一lex対象の後続候補", "set_check V-SET-01", ["CI-SET-01"])

    reuse_candidates = []
    for qid, target_id, display, stem, stem_ja in (
        ("q01", "lex:accept:verb", "accept", "She decided to accept the new job.", "彼女は新しい仕事を受け入れることに決めました。"),
        ("q02", "lex:advise:verb", "advise", "She decided to advise the new student.", "彼女は新しい生徒に助言することに決めました。"),
        ("q03", "lex:achieve:verb", "achieve", "They will achieve their goal this year.", "彼らは今年その目標を達成するでしょう。"),
    ):
        value = copy.deepcopy(official["vocab_mcq_en2ja"])
        value["question_id"] = qid
        value["target"] = {"display_name": display, "ref": target_id, "type": "lexical"}
        value["body"]["stem"] = stem
        value["body"]["stem_ja"] = stem_ja
        value["body"]["target_surface"] = display
        for choice in value["body"]["choices"]:
            choice["is_correct"] = choice["anchor"]["entry_id"] == target_id
        reuse_candidates.append((qid, value))
    for qid, value in reuse_candidates:
        add_candidate(cases, f"set_reuse_{qid}.json", value, "同一誤答inviteを3問で再利用", "3問目set_check V-SET-03", ["CI-SET-03"])

    write_json(TESTS / "fixtures" / "candidates" / "index.json", {"cases": sorted(cases, key=lambda item: item["file"])})
    return cases


def make_golden_cases() -> None:
    these = {
        "body": {
            "choices": [
                {"anchor": {"entry_id": "lex:he:pronoun", "headword": "he", "level": "A1", "pos": "pronoun"}, "gloss": "彼は", "is_correct": False, "text": "彼は"},
                {"anchor": {"entry_id": "lex:these:pronoun", "headword": "these", "level": "A1", "pos": "pronoun"}, "gloss": "これらは", "is_correct": True, "text": "これらは"},
                {"anchor": {"entry_id": "lex:she:pronoun", "headword": "she", "level": "A1", "pos": "pronoun"}, "gloss": "彼女は", "is_correct": False, "text": "彼女は"},
                {"anchor": {"entry_id": "lex:they:pronoun", "headword": "they", "level": "A1", "pos": "pronoun"}, "gloss": "彼らは", "is_correct": False, "text": "彼らは"},
            ],
            "pos_pool_relaxed": False,
            "stem": "These are the books that I bought yesterday.",
            "stem_ja": "これらは私が昨日買った本です。",
            "target_surface": "These",
        },
        "format": "vocab_mcq_en2ja",
        "level": {"scale": "cefr", "value": "A1"},
        "question_id": "q01",
        "target": {"display_name": "these", "ref": "lex:these:pronoun", "type": "lexical"},
    }
    estimate = {
        "body": {
            "context_required_by": None,
            "context_sentence": None,
            "example": {
                "en": "The window must have been closed so as not to let the cold air in.",
                "ja": "冷たい空気を入れないために、その窓は閉められていたに違いありません。",
            },
        },
        "explanation": {
            "text": "この問題の文法項目は「受動態(助動詞+完了形)」です。①機能: 助動詞+have been+過去分詞は、過去の出来事を受動態で推量します。②この例文での使われ方: must have been closed が窓についての推量を表します。③注意点・よくある誤り: 否定の目的は so as not to+動詞の原形の語順にします。",
            "type": "detailed",
        },
        "format": "grammar_example_selfcheck",
        "level": {"scale": "cefrj", "value": "B2.2"},
        "question_id": "q01",
        "target": {"display_name": "受動態(助動詞+完了形)", "ref": "gp:84", "type": "grammar"},
    }
    for name, value in (("these_relative_clause.candidate.json", these), ("estimate_label.candidate.json", estimate)):
        validate("candidate", value)
        write_json(TESTS / "golden" / "cases" / name, value)


def make_reviews() -> None:
    cases: list[dict[str, Any]] = []
    for qnum in range(1, 7):
        for gen in range(1, 4):
            qid = f"q{qnum:02d}"
            generation = f"gen{gen}"
            for verdict, factory in (("pass", pass_review), ("fail", fail_review)):
                name = f"{verdict}_{qid}_{generation}.json"
                write_json(TESTS / "fixtures" / "reviews" / name, factory(qid, generation))
                cases.append({"expected": verdict, "file": name, "purpose": f"{qid} {generation}の{verdict}レビュー", "test_ids": ["RPL-01", "RPL-02", "RPL-03", "RPL-04", "RPL-07", "RPL-08", "RPL-10"]})
    invalid_values = {
        "invalid_json.json": "{\n",
        "invalid_schema.json": "{}\n",
        "invalid_surrogate.json": "{\"value\": \"\\ud800\"}\n",
    }
    for name, text in invalid_values.items():
        write_text(TESTS / "fixtures" / "reviews" / name, text)
        cases.append({"expected": "review_result受理失敗", "file": name, "purpose": "意図したレビュー不正入力", "test_ids": ["RPL-05"]})
    write_json(TESTS / "fixtures" / "reviews" / "index.json", {"cases": sorted(cases, key=lambda item: item["file"])})


def scenario_step(
    question_id: str,
    generation: str,
    candidate: str,
    review: str,
    *,
    candidate_retries: list[str] | None = None,
    review_retries: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "candidate": candidate,
        "candidate_retries": candidate_retries or [],
        "gen": generation,
        "question_id": question_id,
        "review": review,
        "review_retries": review_retries or [],
    }


def expected_audits(
    steps: list[dict[str, Any]],
    terminals: list[str],
    slots: list[str],
    completed: bool,
) -> list[str]:
    names: list[str] = []
    for step, terminal in zip(steps, terminals, strict=True):
        prefix = f"{step['question_id']}.{step['gen']}"
        if terminal == "candidate_invalid":
            names.extend([f"{prefix}.candidate.invalid1.txt", f"{prefix}.candidate.invalid2.txt"])
            continue
        names.extend([f"{prefix}.candidate.json", f"{prefix}.machine.json", f"{prefix}.request.json"])
        if terminal == "review_invalid":
            names.extend(f"{prefix}.review.invalid{index}.txt" for index in range(1, 4))
            continue
        names.append(f"{prefix}.review.json")
        if terminal in {"accepted", "set_fail"}:
            names.append(f"set_check.{step['question_id']}.{step['gen']}.json")
    names.extend(f"slot.{slot}.outcome.json" for slot in slots)
    if completed:
        names.append("set_check.final.json")
    return sorted(names)


def make_scenarios() -> None:
    base_request = {
        "format": "vocab_flashcard_en2ja",
        "level": "A2",
        "level_scale": "cefr",
        "mode": "proposal",
        "question_count": 1,
        "targets": ["lex:accept:verb"],
    }
    scenarios: list[dict[str, Any]] = []

    def add(
        scenario_id: str,
        description: str,
        request: dict[str, Any],
        steps: list[dict[str, Any]],
        terminals: list[str],
        outcome: str,
        set_questions: list[str],
        slots: list[str],
        regeneration_codes: list[str],
    ) -> None:
        scenarios.append(
            {
                "description": description,
                "expected": {
                    "attempts_total": len(steps),
                    "audit_files": expected_audits(steps, terminals, slots, outcome == "completed"),
                    "outcome": outcome,
                    "regeneration_payload_checks": regeneration_codes,
                    "set_questions": set_questions,
                },
                "request": request,
                "scenario_id": scenario_id,
                "steps": steps,
            }
        )

    rpl01_steps = [
        scenario_step(f"q{number:02d}", "gen1", f"replay_q{number:02d}_pass.json", f"pass_q{number:02d}_gen1.json")
        for number in range(1, 4)
    ]
    request3 = {**base_request, "question_count": 3, "targets": ["lex:accept:verb", "lex:ability:noun", "lex:abroad:adverb"]}
    add("rpl_01_all_gen1_pass", "3問がすべてgen1で合格する", request3, rpl01_steps, ["accepted"] * 3, "completed", ["q01", "q02", "q03"], ["q01", "q02", "q03"], [])

    rpl02_steps = [
        scenario_step("q01", "gen1", "replay_q01_pass.json", "fail_q01_gen1.json"),
        scenario_step("q01", "gen2", "replay_q01_pass.json", "pass_q01_gen2.json"),
    ]
    add("rpl_02_regenerate_then_pass", "レビューfail後に同じ問題のgen2が合格する", base_request, rpl02_steps, ["review_fail", "accepted"], "completed", ["q01"], ["q01"], ["CHK-03"])

    rpl03_steps = [
        scenario_step("q01", f"gen{generation}", "replay_q01_pass.json", f"fail_q01_gen{generation}.json")
        for generation in range(1, 4)
    ] + [scenario_step("q02", "gen1", "replay_q02_pass.json", "pass_q02_gen1.json")]
    add("rpl_03_proposal_replacement", "提案モードで3世代fail後にq02を自動補充する", base_request, rpl03_steps, ["review_fail"] * 3 + ["accepted"], "completed", ["q02"], ["q01"], ["CHK-03"])

    rpl04_steps = [
        scenario_step("q01", f"gen{generation}", "replay_q01_pass.json", f"fail_q01_gen{generation}.json")
        for generation in range(1, 4)
    ]
    explicit = {**base_request, "mode": "explicit"}
    add("rpl_04_explicit_consult", "明示モードで3世代fail後に教師照会する", explicit, rpl04_steps, ["review_fail"] * 3, "teacher_consult", [], [], ["CHK-03"])

    for kind, fixture in (
        ("json", "invalid_json.json"),
        ("schema", "invalid_schema.json"),
        ("surrogate", "invalid_surrogate.json"),
    ):
        steps = [scenario_step("q01", "gen1", "replay_q01_pass.json", fixture, review_retries=[fixture, fixture])]
        add(f"rpl_05_review_invalid_{kind}", f"レビュー{kind}受理失敗を3回で中止する", base_request, steps, ["review_invalid"], "aborted", [], [], [])

    rpl06_steps = [
        scenario_step(
            "q01",
            "gen1",
            "rpl_06_missing_question_id.json",
            "pass_q01_gen1.json",
            candidate_retries=["rpl_06_question_id_type.json"],
        ),
        scenario_step("q01", "gen2", "replay_q01_pass.json", "pass_q01_gen2.json"),
    ]
    add("rpl_06_candidate_invalid", "候補受理を同一世代で1回再指示してから世代消費する", base_request, rpl06_steps, ["candidate_invalid", "accepted"], "completed", ["q01"], ["q01"], [])

    machine_fail_request = {**base_request, "level": "A1", "targets": ["lex:book:noun"]}
    rpl07_steps = [scenario_step("q01", "gen1", "mch_06_high_level_abandon.json", "pass_q01_gen1.json")]
    add("rpl_07_machine_fail_review_pass", "machine failをreview passが上書きしない", machine_fail_request, rpl07_steps, ["machine_fail"], "teacher_consult", [], [], [])

    rpl08_steps = [
        scenario_step("q01", "gen1", "replay_q01_conflict.json", "pass_q01_gen1.json"),
        scenario_step("q02", "gen1", "replay_q02_conflict.json", "pass_q02_gen1.json"),
        scenario_step("q02", "gen2", "replay_q02_pass.json", "pass_q02_gen2.json"),
    ]
    request2 = {**base_request, "question_count": 2, "targets": ["lex:accept:verb", "lex:ability:noun"]}
    add("rpl_08_set_conflict", "例文使い回しをset_checkで検出してgen2で解消する", request2, rpl08_steps, ["accepted", "set_fail", "accepted"], "completed", ["q01", "q02"], ["q01", "q02"], ["V-SET-02"])

    add("rpl_09_audit_integrity", "完成セットの監査参照と正本自立性を確認する", request3, rpl01_steps, ["accepted"] * 3, "completed", ["q01", "q02", "q03"], ["q01", "q02", "q03"], [])

    rpl10_steps = [
        scenario_step(f"q{number:02d}", f"gen{generation}", f"replay_q{number:02d}_pass.json", f"fail_q{number:02d}_gen{generation}.json")
        for number in range(1, 7)
        for generation in range(1, 4)
    ]
    request_worst = {**base_request, "question_count": 3, "targets": [f"lex:test-{number}" for number in range(1, 7)]}
    add("rpl_10_worst_case_bound", "N=3の提案モードで2N対象×3世代で停止する", request_worst, rpl10_steps, ["review_fail"] * 18, "teacher_consult", [], [], ["CHK-03", "V-TGT-03"])

    for scenario in scenarios:
        write_json(TESTS / "fixtures" / "scenarios" / f"{scenario['scenario_id']}.json", scenario)


def make_golden_and_schema_assets(official: dict[str, dict[str, Any]]) -> None:
    meta = load_json(ROOT / "data" / "normalized" / "meta.json")
    checksums = {
        name: hashlib.sha256((ROOT / "data" / "normalized" / name).read_bytes()).hexdigest()
        for name in ("lexicon.json", "grammar.json", "meta.json")
    }
    write_json(TESTS / "golden" / "normalized" / "checksums.json", {"data_version": meta["data_version"], "files": checksums})

    for index, fmt in enumerate(FORMATS, start=1):
        set_path = build_golden_set(official[fmt], index)
        html_path = TESTS / "golden" / "html" / f"{fmt}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        run_cli(
            [
                "scripts/build_html.py",
                "--set",
                str(set_path.relative_to(ROOT)),
                "--out",
                str(html_path.relative_to(ROOT)),
            ]
        )

    compat_path = TESTS / "fixtures" / "candidates" / "compat" / "grammar_cloze.json"
    machine = run_machine(compat_path, expected_format="grammar_cloze", expected_level="A1.2")
    write_json(TESTS / "golden" / "machine" / "grammar_cloze.machine.json", machine)
    write_json(TESTS / "fixtures" / "machine" / "valid_question.json", machine)
    write_json(TESTS / "fixtures" / "machine" / "index.json", {"cases": [{"expected": "machine_reportスキーマ合格", "file": "valid_question.json", "purpose": "妥当なquestion scopeレポート", "test_ids": ["CI-MCH-12", "CI-SCH-02"]}]})

    request = review_request(official["grammar_cloze"], machine)
    valid_docs = {
        "candidate": official["grammar_cloze"],
        "config_limits": load_json(ROOT / "data" / "config" / "limits.json"),
        "config_proper_nouns": load_json(ROOT / "data" / "config" / "proper_nouns.json"),
        "machine_report": machine,
        "normalized_grammar": load_json(ROOT / "data" / "normalized" / "grammar.json"),
        "normalized_lexicon": load_json(ROOT / "data" / "normalized" / "lexicon.json"),
        "review_request": request,
        "review_result": pass_review(),
        "set": load_json(TESTS / "golden" / "sets" / "grammar_cloze.set.json"),
    }
    invalid_index: list[dict[str, Any]] = []
    representative_fields = {
        "candidate": "question_id",
        "machine_report": "scope",
    }
    for schema_name, value in valid_docs.items():
        validate(schema_name, value)
        valid_path = TESTS / "fixtures" / "schemas" / "valid" / schema_name / "valid.json"
        write_json(valid_path, value)
        schema = load_json(ROOT / "schemas" / f"{schema_name}.schema.json")
        required = schema.get("required", [])
        representative = required[0] if required else representative_fields[schema_name]
        missing = copy.deepcopy(value)
        missing.pop(representative)
        type_bad = copy.deepcopy(value)
        type_field = representative
        type_bad[type_field] = 123 if not isinstance(type_bad.get(type_field), int) else "bad"
        extra = copy.deepcopy(value)
        extra["unexpected_m8_field"] = True
        for kind, invalid in (("missing", missing), ("type", type_bad), ("additional", extra)):
            relative = f"{schema_name}/{kind}.json"
            write_json(TESTS / "fixtures" / "schemas" / "invalid" / relative, invalid)
            invalid_index.append({"expected": "E-CONTRACT-01", "file": relative, "purpose": f"意図した{schema_name}の{kind}不当例", "test_ids": ["CI-SCH-03"]})

    id_cases = [
        (
            "set/set_id_pattern.json",
            {**valid_docs["set"], "set_id": "bad-set-id"},
            "意図したset_id書式不正",
        ),
        (
            "candidate/question_id_q21.json",
            {**valid_docs["candidate"], "question_id": "q21"},
            "意図したquestion_id範囲外",
        ),
        (
            "candidate/entry_id_pattern.json",
            {
                **valid_docs["candidate"],
                "target": {**valid_docs["candidate"]["target"], "ref": "bad-entry-id"},
            },
            "意図した語彙・文法エントリID書式不正",
        ),
        (
            "review_result/generation_gen4.json",
            {**valid_docs["review_result"], "generation": "gen4"},
            "意図した世代gen4範囲外",
        ),
    ]
    for relative, value, purpose in id_cases:
        write_json(TESTS / "fixtures" / "schemas" / "invalid" / relative, value)
        invalid_index.append(
            {
                "expected": "E-CONTRACT-01",
                "file": relative,
                "purpose": purpose,
                "test_ids": ["CI-SCH-05"],
            }
        )

    major_mismatch = copy.deepcopy(valid_docs["set"])
    major_mismatch["schema_version"] = "2.0.0"
    relative = "set/schema_major_mismatch.json"
    write_json(TESTS / "fixtures" / "schemas" / "invalid" / relative, major_mismatch)
    invalid_index.append(
        {
            "expected": "E-CONTRACT-02",
            "file": relative,
            "purpose": "build_htmlで意図したset schema_versionメジャー不一致",
            "test_ids": ["CI-HTM-05"],
        }
    )
    write_json(TESTS / "fixtures" / "schemas" / "invalid" / "index.json", {"cases": sorted(invalid_index, key=lambda item: item["file"])})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="tests配下の資産を生成する")
    args = parser.parse_args()
    if not args.write:
        parser.error("--write が必要です")
    if not PYTHON.is_file():
        raise RuntimeError(".venvがありません")
    official = official_candidates()
    make_machine_candidates(official)
    make_golden_cases()
    make_reviews()
    make_scenarios()
    make_golden_and_schema_assets(official)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
