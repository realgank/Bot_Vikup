#!/usr/bin/env python3
"""Кроссплатформенный обновлятор рабочей копии из GitHub."""
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import Iterable


class GitError(RuntimeError):
    """Ошибка при выполнении команды git."""


def run_git(args: Iterable[str]) -> None:
    command = ["git", *args]
    result = subprocess.run(command)
    if result.returncode != 0:
        raise GitError(f"Команда {' '.join(command)} завершилась с ошибкой")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Обновление репозитория до последней версии ветки",
    )
    parser.add_argument(
        "repo_url",
        nargs="?",
        help="URL GitHub-репозитория (требуется при первом запуске в пустой директории)",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="Ветка для обновления (по умолчанию main)",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def ensure_remote(repo_url: str | None, branch: str) -> None:
    try:
        run_git(["rev-parse", "--is-inside-work-tree"])
    except GitError:
        if not repo_url:
            raise GitError(
                "Текущая директория не является git-репозиторием. "
                "Укажите URL репозитория при запуске."
            )
        run_git(["clone", repo_url, "."])
        return

    if repo_url:
        try:
            run_git(["remote", "set-url", "origin", repo_url])
        except GitError:
            run_git(["remote", "add", "origin", repo_url])

    try:
        run_git(["remote", "get-url", "origin"])
    except GitError as exc:
        raise GitError(
            "Удалённый репозиторий origin не настроен. Передайте URL при запуске."
        ) from exc

    run_git(["fetch", "origin", branch])
    run_git(["pull", "--rebase", "origin", branch])


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parent.parent
    cwd = Path.cwd()
    if cwd != repo_root:
        os.chdir(repo_root)
    try:
        ensure_remote(args.repo_url, args.branch)
    except GitError as exc:
        print(exc)
        return 1
    finally:
        if cwd != repo_root:
            os.chdir(cwd)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
