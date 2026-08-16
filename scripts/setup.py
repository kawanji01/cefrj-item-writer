#!/usr/bin/env python3
"""CEFR-J作問環境を固定版依存で構築する。"""

from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = REPO_ROOT / ".venv"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
MODEL_URL = (
    "https://github.com/explosion/spacy-models/releases/download/"
    "en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
)


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def main() -> int:
    if sys.version_info < (3, 11):
        print(
            f"Python 3.11以上が必要です（検出: {sys.version.split()[0]}）。",
            file=sys.stderr,
        )
        return 1

    if not REQUIREMENTS.is_file():
        print(f"依存定義がありません: {REQUIREMENTS}", file=sys.stderr)
        return 1

    print(f"venvを準備します: {VENV_DIR}")
    venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    python = venv_python()

    print("固定版依存を導入します。")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(REQUIREMENTS)],
        cwd=REPO_ROOT,
        check=True,
    )

    print("spaCyモデル en_core_web_sm 3.8.0を導入します。")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--disable-pip-version-check", MODEL_URL],
        cwd=REPO_ROOT,
        check=True,
    )

    print("セットアップが完了しました。")
    print(f"次を実行してください: {python} scripts/doctor.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
