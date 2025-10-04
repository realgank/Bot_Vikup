#!/usr/bin/env python3
"""Кроссплатформенный скрипт для подготовки виртуального окружения."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


def run(command: Iterable[str]) -> None:
    """Запустить *command* и завершиться с тем же кодом в случае ошибки."""

    completed = subprocess.run(list(command))
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def ensure_venv(python_executable: str, venv_path: Path) -> Path:
    """Создать виртуальное окружение, если оно ещё не существует."""

    if not venv_path.exists():
        run([python_executable, "-m", "venv", str(venv_path)])
    return venv_python(venv_path)


def venv_python(venv_path: Path) -> Path:
    """Вернуть путь до интерпретатора Python внутри окружения."""

    if os.name == "nt":
        candidates = [venv_path / "Scripts" / "python.exe"]
    else:
        candidates = [
            venv_path / "bin" / "python",
            venv_path / "bin" / "python3",
        ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Не удалось найти Python внутри виртуального окружения"
    )


def install_requirements(python_bin: Path, requirements_file: Path) -> None:
    """Установить зависимости проекта внутрь окружения."""

    run([str(python_bin), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(python_bin), "-m", "pip", "install", "-r", str(requirements_file)])


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Подготовка виртуального окружения для ContractBot",
    )
    parser.add_argument(
        "--venv",
        default=".venv",
        help="Путь до виртуального окружения (по умолчанию .venv)",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Исполняемый файл Python, который будет использоваться для создания окружения",
    )
    parser.add_argument(
        "--requirements",
        default="requirements.txt",
        help="Файл с зависимостями",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parent.parent
    venv_path = (repo_root / args.venv).resolve()
    requirements_path = (repo_root / args.requirements).resolve()

    python_bin = ensure_venv(args.python, venv_path)
    install_requirements(python_bin, requirements_path)

    activation_hint = (
        f"{venv_path / 'Scripts' / 'activate.bat'}"
        if os.name == "nt"
        else f"source {venv_path / 'bin' / 'activate'}"
    )

    print("\nОкружение готово.")
    print("Активируйте его командой:")
    print(f"  {activation_hint}")
    print("После активации запустите сервис через:")
    print("  python -m contractbot /путь/к/config.json")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
