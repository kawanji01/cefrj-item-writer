#!/usr/bin/env python3
"""M7D-12の固定一時ファイル1件だけを削除するClaude Code配線。"""

from __future__ import annotations

import argparse
import re
import stat
import sys
from pathlib import Path


STAGING_PATH_RE = re.compile(
    r"output/[0-9]{8}-[0-9]{6}-[a-z0-9]{4}/\.staging/"
    r"q(?:0[1-9]|1[0-9]|20)\.gen[123]\."
    r"(?:candidate\.raw[12]|request\.raw)\.json"
)


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="検証済みの固定ステージングファイルだけを削除します。"
    )
    parser.add_argument("--file", required=True)
    return parser.parse_args()


def checked_path(raw_path: str, repo_root: Path) -> Path:
    if STAGING_PATH_RE.fullmatch(raw_path) is None:
        fail("削除対象がM7D-12の固定一時ファイル名ではありません")

    target = repo_root / raw_path
    parents = [repo_root / "output", target.parents[1], target.parent]
    for parent in parents:
        try:
            mode = parent.lstat().st_mode
        except OSError as exc:
            fail(f"一時ファイルの親ディレクトリを確認できません: {exc}")
        if not stat.S_ISDIR(mode) or parent.is_symlink():
            fail(f"一時ファイルの親が実ディレクトリではありません: {parent}")

    try:
        mode = target.lstat().st_mode
    except OSError as exc:
        fail(f"一時ファイルを確認できません: {exc}")
    if not stat.S_ISREG(mode) or target.is_symlink():
        fail("削除対象は通常ファイルでなければなりません")
    return target


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    target = checked_path(args.file, repo_root)
    try:
        target.unlink()
        try:
            target.parent.rmdir()
        except OSError:
            pass
    except OSError as exc:
        fail(f"一時ファイルを削除できません: {exc}")


if __name__ == "__main__":
    main()
