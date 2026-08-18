#!/usr/bin/env python3
"""合格済みset.jsonから単一自己完結HTMLを決定的に生成する。"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tempfile
import traceback
from copy import deepcopy
from pathlib import Path
from typing import Any

from build_normalized import CliFailure, emit_json, require_basic_environment
from validate import (
    contract_failure,
    load_schema,
    read_json_document,
    validation_result,
)


TEMPLATE_RELATIVE_PATH = Path("templates/index.html.j2")
SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
FORMAT_NAMES = {
    "vocab_mcq_en2ja": "語彙4択（英語→日本語）",
    "vocab_mcq_ja2en": "語彙4択（日本語→英語）",
    "vocab_flashcard_en2ja": "例文フラッシュカード（英語→日本語）",
    "vocab_flashcard_ja2en": "例文フラッシュカード（日本語→英語）",
    "grammar_mcq": "文法選択問題",
    "grammar_cloze": "文法穴埋め問題",
    "grammar_reorder": "語句整序問題",
    "grammar_rewrite": "書き換え問題",
    "grammar_example_selfcheck": "文法例文問題（自己採点）",
}
INSTRUCTIONS = {
    "vocab_mcq_en2ja": "英単語の正しい意味を選びましょう。",
    "vocab_mcq_ja2en": "意味に合う英単語を選びましょう。",
    "vocab_flashcard_en2ja": "英文の意味を思い浮かべてから、カードをめくりましょう。",
    "vocab_flashcard_ja2en": "日本語に合う英文を思い浮かべてから、カードをめくりましょう。",
    "grammar_mcq": "空欄に入る最も適切なものを選びましょう。",
    "grammar_cloze": "空欄に入る語句を入力しましょう。",
    "grammar_reorder": "意味が通る英文になるように、語句を順にタップしましょう。",
    "grammar_rewrite": "指示に従って、書き換えた文の空欄を埋めましょう。",
    "grammar_example_selfcheck": "英文の意味を思い浮かべてから、答えを見て自己採点しましょう。",
}
POS_LABELS = {
    "noun": "[名詞]",
    "verb": "[動詞]",
    "adjective": "[形容詞]",
    "adverb": "[副詞]",
    "pronoun": "[代名詞]",
    "preposition": "[前置詞]",
    "determiner": "[限定詞]",
    "conjunction": "[接続詞]",
    "number": "[数詞]",
    "modal auxiliary": "[助動詞]",
    "be-verb": "[be動詞]",
    "do-verb": "[do動詞]",
    "have-verb": "[have動詞]",
    "interjection": "[間投詞]",
    "infinitive-to": "[不定詞to]",
}
POS_BY_REF_SUFFIX = {
    "noun": "noun",
    "verb": "verb",
    "adjective": "adjective",
    "adverb": "adverb",
    "pronoun": "pronoun",
    "preposition": "preposition",
    "determiner": "determiner",
    "conjunction": "conjunction",
    "number": "number",
    "modal-auxiliary": "modal auxiliary",
    "be-verb": "be-verb",
    "interjection": "interjection",
    "do-verb": "do-verb",
    "have-verb": "have-verb",
    "infinitive-to": "infinitive-to",
}
CHOICE_LABELS = ("A", "B", "C", "D")

REMEDIES = {
    "E-ENV-04": (
        "リポジトリルートに移動してください。テンプレートまたはスキーマの欠落・破損は"
        "git statusで確認し、git checkoutで復元してください。"
    ),
    "E-ENV-05": "出力先ディレクトリの権限と空き容量を確認してください。",
    "E-INPUT-01": (
        "python scripts/build_html.py --help の日本語ヘルプを参照して引数と入出力パスを"
        "修正してください。"
    ),
    "E-CONTRACT-02": (
        "git pullで最新化し python scripts/doctor.py を実行してください。旧版の文書を"
        "使い続ける場合は当該セットを新版で再作成してください。"
    ),
}


class HtmlArgumentParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        return (
            super()
            .format_help()
            .replace("usage:", "使用法:", 1)
            .replace("options:", "オプション:", 1)
            .replace("show this help message and exit", "このヘルプを表示して終了します", 1)
        )

    def error(self, message: str) -> None:
        translated = message
        unknown_prefix = "unrecognized arguments:"
        if message.startswith(unknown_prefix):
            translated = f"未知の引数です:{message[len(unknown_prefix):]}"
        else:
            missing = re.fullmatch(r"the following arguments are required: (.+)", message)
            if missing:
                translated = f"必須引数がありません: {missing.group(1)}"
            missing_value = re.fullmatch(r"argument (.+): expected one argument", message)
            if missing_value:
                translated = f"引数 {missing_value.group(1)} に値が必要です"
        raise CliFailure(
            "E-INPUT-01",
            f"E-INPUT-01 build_html.pyの引数が不正です: {translated}",
            detail={"parser_message": message},
            remedy=REMEDIES["E-INPUT-01"],
        )


def make_parser() -> HtmlArgumentParser:
    parser = HtmlArgumentParser(
        description="合格済みset.jsonから自己完結HTMLを決定的に生成します。",
        allow_abbrev=False,
    )
    parser.add_argument("--set", required=True, help="入力set.jsonのパス（必須）。")
    parser.add_argument(
        "--out",
        help="出力HTMLのパス。既定は入力と同じディレクトリのindex.html。",
    )
    return parser


def one_line(value: Any) -> str:
    return str(value).replace("\r", "\\r").replace("\n", "\\n")


def load_template_environment(repo_root: Path) -> tuple[Any, Any]:
    template_path = repo_root / TEMPLATE_RELATIVE_PATH
    try:
        file_status = template_path.stat()
        if not stat.S_ISREG(file_status.st_mode):
            raise OSError("通常ファイルではありません")
        jinja2 = __import__("jinja2")
        environment = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(template_path.parent)),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
        install_template_helpers(environment)
        template = environment.get_template(template_path.name)
    except Exception as exc:
        raise CliFailure(
            "E-ENV-04",
            f"E-ENV-04 Jinja2テンプレートが欠落・読取不能・構文不正です: "
            f"{TEMPLATE_RELATIVE_PATH.as_posix()} ({one_line(exc)})",
            detail={"error": str(exc), "path": TEMPLATE_RELATIVE_PATH.as_posix()},
            remedy=REMEDIES["E-ENV-04"],
        ) from exc
    return environment, template


def input_schema_version(document: Any) -> str | None:
    if not isinstance(document, dict):
        return None
    value = document.get("schema_version")
    return value if isinstance(value, str) and SEMVER_PATTERN.fullmatch(value) else None


def reject_major_mismatch(
    document: Any,
    current_schema_version: str,
    set_path: Path,
) -> None:
    document_version = input_schema_version(document)
    if document_version is None:
        return
    supported_major = current_schema_version.split(".", 1)[0]
    document_major = document_version.split(".", 1)[0]
    if document_major == supported_major:
        return
    raise CliFailure(
        "E-CONTRACT-02",
        "E-CONTRACT-02 schema_versionのメジャーが不一致です: "
        f"文書{document_version}、ツール対応メジャー{supported_major}、対象{one_line(set_path)}。",
        detail={
            "document_schema_version": document_version,
            "path": str(set_path),
            "supported_major": int(supported_major),
        },
        remedy=REMEDIES["E-CONTRACT-02"],
    )


def paths_alias(input_path: Path, output_path: Path) -> bool:
    try:
        if input_path.resolve(strict=True) == output_path.resolve(strict=False):
            return True
    except OSError:
        pass
    try:
        return output_path.exists() and os.path.samefile(input_path, output_path)
    except OSError:
        return False


def reject_input_output_alias(input_path: Path, output_path: Path) -> None:
    if not paths_alias(input_path, output_path):
        return
    raise CliFailure(
        "E-INPUT-01",
        "E-INPUT-01 --outに入力set.jsonと同じパスまたはファイル実体を指定できません: "
        f"--set {one_line(input_path)}、--out {one_line(output_path)}。",
        detail={"out": str(output_path), "set": str(input_path)},
        remedy=REMEDIES["E-INPUT-01"],
    )


def pos_from_ref(reference: str) -> str:
    return POS_BY_REF_SUFFIX[reference.rsplit(":", 1)[-1]]


def completed_sentence(sentence_with_blank: str, answer: str) -> str:
    return sentence_with_blank.replace("____", answer, 1)


def prepare_questions(document: dict[str, Any]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for source in document["questions"]:
        question = deepcopy(source)
        question["number"] = int(question["question_id"][1:])
        body = question["body"]
        current_format = question["format"]
        if current_format in {"vocab_mcq_en2ja", "vocab_mcq_ja2en", "grammar_mcq"}:
            answer_index = next(
                index for index, choice in enumerate(body["choices"]) if choice["is_correct"]
            )
            question["answer_index"] = answer_index
            question["answer_label"] = CHOICE_LABELS[answer_index]
            question["answer_text"] = body["choices"][answer_index]["text"]
        if current_format == "vocab_mcq_en2ja":
            question["pos_label"] = POS_LABELS[pos_from_ref(question["target"]["ref"])]
        elif current_format in {"vocab_flashcard_en2ja", "vocab_flashcard_ja2en"}:
            question["pos_label"] = POS_LABELS[body["pos"]]
        elif current_format in {"grammar_cloze", "grammar_rewrite"}:
            question["accepted"] = [body["answer"], *body["answer_equivalents"]]
        if current_format == "grammar_rewrite":
            question["completed_target"] = completed_sentence(
                body["target_sentence_with_blank"], body["answer"]
            )
        prepared.append(question)
    return prepared


def install_template_helpers(environment: Any) -> None:
    markupsafe = __import__("markupsafe")
    Markup = markupsafe.Markup
    escape = markupsafe.escape

    def json_attribute(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def highlighted(text: str, surface: str) -> Any:
        before, match, after = text.partition(surface)
        if not match:
            return escape(text)
        return Markup("{}<strong class=\"target\">{}</strong>{}").format(
            escape(before), escape(match), escape(after)
        )

    def blank_display(text: str) -> Any:
        before, marker, after = text.partition("____")
        if not marker:
            return escape(text)
        return Markup(
            "{}<span class=\"blank\" role=\"img\" aria-label=\"空欄\" lang=\"ja\">_______</span>{}"
        ).format(escape(before), escape(after))

    def blank_input(text: str, question_id: str, cue: str | None = None) -> Any:
        before, marker, after = text.partition("____")
        if not marker:
            return escape(text)
        input_markup = Markup(
            '<span class="cloze-slot"><label class="visually-hidden" for="{}-input" lang="ja">'
            '空欄に入る語句</label><input id="{}-input" type="text" autocomplete="off" '
            'autocapitalize="off" spellcheck="false" lang="en"></span>'
        ).format(escape(question_id), escape(question_id))
        cue_markup = Markup("")
        if cue is not None:
            cue_markup = Markup('<span class="cue">（<span lang="en">{}</span>）</span>').format(
                escape(cue)
            )
        return Markup("{}{}{}{}").format(
            escape(before), input_markup, cue_markup, escape(after)
        )

    environment.filters["json_attr"] = json_attribute
    environment.filters["highlight"] = highlighted
    environment.filters["blank_display"] = blank_display
    environment.globals["blank_input"] = blank_input


def render_html(
    environment: Any,
    template: Any,
    document: dict[str, Any],
) -> bytes:
    current_format = document["format"]
    rendered = template.render(
        choice_labels=CHOICE_LABELS,
        format_name=FORMAT_NAMES[current_format],
        instruction=INSTRUCTIONS[current_format],
        questions=prepare_questions(document),
        set_data=document,
    )
    normalized = rendered.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
    return normalized.encode("utf-8")


def write_html(path: Path, payload: bytes) -> None:
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.tmp.",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError as exc:
        raise CliFailure(
            "E-ENV-05",
            f"E-ENV-05 HTML出力先へ書き込めません: {one_line(path)} ({one_line(exc)})",
            detail={"error": str(exc), "path": str(path)},
            remedy=REMEDIES["E-ENV-05"],
        ) from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def run(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    if args.set == "-":
        raise CliFailure(
            "E-INPUT-01",
            "E-INPUT-01 build_html.pyはstdin入力を受理しません。--setにset.jsonのパスを指定してください。",
            detail={"set": "-"},
            remedy=REMEDIES["E-INPUT-01"],
        )
    repo_root = Path.cwd()
    require_basic_environment(repo_root)
    environment, template = load_template_environment(repo_root)

    set_path = Path(args.set)
    document = read_json_document(args.set)
    schema, current_schema_version = load_schema(repo_root, "set")
    reject_major_mismatch(document, current_schema_version, set_path)
    result, errors = validation_result(document, "set", schema, current_schema_version)
    if errors:
        raise contract_failure("set", current_schema_version, errors)

    output_path = Path(args.out) if args.out is not None else set_path.parent / "index.html"
    reject_input_output_alias(set_path, output_path)
    payload = render_html(environment, template, document)
    write_html(output_path, payload)
    emit_json(
        {
            "bytes": len(payload),
            "html_path": output_path.as_posix(),
            "schema_version": document["schema_version"],
            "set_id": document["set_id"],
        }
    )
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
