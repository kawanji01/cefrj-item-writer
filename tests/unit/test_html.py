from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from tests.support import GOLDEN, OFFICIAL_FORMATS, ROOT, load_json, run_cli, stderr_json


FORMATS = OFFICIAL_FORMATS


class HtmlFacts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.choice_texts: list[str] = []
        self.accepted: list[str] = []
        self.external_resources: list[str] = []
        self._choice_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        source = values.get("src")
        if source and re.match(r"^https?://", source, re.IGNORECASE):
            self.external_resources.append(source)
        if tag == "link":
            href = values.get("href")
            if href and re.match(r"^https?://", href, re.IGNORECASE):
                self.external_resources.append(href)
        classes = (values.get("class") or "").split()
        if tag == "span" and "choice-text" in classes:
            self._choice_parts = []
        if "data-accepted" in values and values["data-accepted"] is not None:
            self.accepted.append(values["data-accepted"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self._choice_parts is not None:
            self.choice_texts.append("".join(self._choice_parts).strip())
            self._choice_parts = None

    def handle_data(self, data: str) -> None:
        if self._choice_parts is not None:
            self._choice_parts.append(data)


def html_facts(text: str) -> HtmlFacts:
    parser = HtmlFacts()
    parser.feed(text)
    return parser


def generate(fmt: str, destination: Path) -> bytes:
    completed = run_cli(
        "scripts/build_html.py",
        "--set",
        f"tests/golden/sets/{fmt}.set.json",
        "--out",
        str(destination),
    )
    assert completed.returncode == 0, completed.stderr.decode()
    return destination.read_bytes()


def test_ci_htm_01_deterministic_bytes(tmp_path: Path) -> None:
    """CI-HTM-01: 同じsetから2回生成したHTMLがバイト一致する。"""

    first = generate("grammar_cloze", tmp_path / "first.html")
    second = generate("grammar_cloze", tmp_path / "second.html")
    assert first == second


@pytest.mark.parametrize("fmt", FORMATS)
def test_ci_htm_02_nine_golden_outputs(fmt: str, tmp_path: Path) -> None:
    """CI-HTM-02: 9形式の生成HTMLがゴールデンとバイト一致する。"""

    actual = generate(fmt, tmp_path / f"{fmt}.html")
    assert actual == (GOLDEN / "html" / f"{fmt}.html").read_bytes()


@pytest.mark.parametrize("fmt", FORMATS)
def test_ci_htm_03_self_contained(fmt: str) -> None:
    """CI-HTM-03: 9形式HTMLに外部取得を伴う参照が存在しない。"""

    text = (GOLDEN / "html" / f"{fmt}.html").read_text(encoding="utf-8")
    assert html_facts(text).external_resources == []
    assert not re.search(r"url\(\s*['\"]?https?://", text, re.IGNORECASE)
    assert not re.search(r"@import\s+(?:url\()?\s*['\"]?https?://", text, re.IGNORECASE)


@pytest.mark.parametrize("fmt", ("vocab_mcq_en2ja", "vocab_mcq_ja2en", "grammar_mcq"))
def test_ci_htm_04_choice_order(fmt: str) -> None:
    """CI-HTM-04: 4択DOM順をset配列順のまま固定し並べ替え処理を持たない。"""

    document = load_json(GOLDEN / "sets" / f"{fmt}.set.json")
    text = (GOLDEN / "html" / f"{fmt}.html").read_text(encoding="utf-8")
    rendered = html_facts(text).choice_texts
    expected = [choice["text"] for choice in document["questions"][0]["body"]["choices"]]
    assert rendered == expected
    assert "Math.random" not in text and ".sort(" not in text and "shuffle" not in text.lower()


def test_ci_htm_05_schema_major_mismatch(tmp_path: Path) -> None:
    """CI-HTM-05: set schema_versionメジャー不一致を拒否しHTMLを作らない。"""

    destination = tmp_path / "must-not-exist.html"
    completed = run_cli(
        "scripts/build_html.py",
        "--set",
        "tests/fixtures/schemas/invalid/set/schema_major_mismatch.json",
        "--out",
        str(destination),
    )
    assert completed.returncode == 1
    assert stderr_json(completed)["error_code"] == "E-CONTRACT-02"
    assert not destination.exists()


def test_ci_htm_06_cloze_equivalents_embedded() -> None:
    """CI-HTM-06: 穴埋め正答と同値リスト全要素を判定データへ埋め込む。"""

    document = load_json(GOLDEN / "sets" / "grammar_cloze.set.json")
    facts = html_facts((GOLDEN / "html" / "grammar_cloze.html").read_text(encoding="utf-8"))
    accepted = json.loads(facts.accepted[0])
    body = document["questions"][0]["body"]
    assert accepted == [body["answer"], *body["answer_equivalents"]]
