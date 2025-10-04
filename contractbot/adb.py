"""ADB helper utilities used by ContractBot."""
from __future__ import annotations

import logging
import subprocess
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple


class AdbError(RuntimeError):
    """Raised when an ADB command fails."""


class ADBClient:
    """Thin wrapper around the ``adb`` binary."""

    def __init__(self, serial: str) -> None:
        self.serial = serial

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

    @staticmethod
    def list_devices() -> List[Tuple[str, str]]:
        """Return a list of connected ``adb`` devices."""

        try:
            result = subprocess.run(
                ["adb", "devices", "-l"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
            )
        except FileNotFoundError as exc:  # pragma: no cover - runtime guard
            raise AdbError("adb binary not found in PATH") from exc

        devices: List[Tuple[str, str]] = []
        for line in result.stdout.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 1:
                serial, desc = parts[0], ""
            else:
                serial, desc = parts[0], parts[1]
            if "device" in desc:
                devices.append((serial, desc))
        return devices

    @staticmethod
    def prompt_for_device(devices: Sequence[Tuple[str, str]]) -> str:
        """Prompt the operator to select one device from ``devices``."""

        if not devices:
            raise AdbError("No ADB devices detected")
        print("Available ADB devices:")
        for idx, (serial, desc) in enumerate(devices, start=1):
            print(f"  {idx}. {serial} {desc}")
        while True:
            raw = input("Select device number: ")
            try:
                idx = int(raw)
            except ValueError:
                continue
            if 1 <= idx <= len(devices):
                return devices[idx - 1][0]

    # ------------------------------------------------------------------
    # Command execution helpers
    # ------------------------------------------------------------------

    def _adb_base_command(self) -> List[str]:
        if not self.serial or self.serial == "auto":
            return ["adb"]
        return ["adb", "-s", self.serial]

    def run(self, *args: str, timeout: Optional[float] = None) -> subprocess.CompletedProcess:
        command = self._adb_base_command() + list(args)
        logging.debug("Running ADB command: %s", command)
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                encoding="utf-8",
                timeout=timeout,
            )
        except subprocess.CalledProcessError as exc:
            logging.error("ADB command failed: %s", exc.stderr.strip())
            raise AdbError(exc.stderr.strip()) from exc
        return result

    def exec_out(
        self, *args: str, timeout: Optional[float] = None, binary: bool = True
    ) -> bytes:
        command = self._adb_base_command() + ["exec-out"] + list(args)
        logging.debug("Running ADB exec-out: %s", command)
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=timeout,
            )
        except subprocess.CalledProcessError as exc:
            logging.error(
                "ADB exec-out failed: %s", exc.stderr.decode("utf-8", "ignore")
            )
            raise AdbError(exc.stderr.decode("utf-8", "ignore")) from exc
        return (
            result.stdout
            if binary
            else result.stdout.decode("utf-8", "ignore").encode("utf-8")
        )

    # ------------------------------------------------------------------
    # High level helpers
    # ------------------------------------------------------------------

    def screencap(self) -> Optional["Image.Image"]:
        """Capture a screenshot from the device."""

        try:
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - runtime guard
            raise RuntimeError(
                "Pillow is required for screenshot decoding but is not installed"
            ) from exc

        attempts = 0
        while attempts < 3:
            attempts += 1
            try:
                raw = self.exec_out("screencap", "-p")
            except AdbError:
                logging.warning("ADB screencap attempt %s failed", attempts)
                time.sleep(1)
                continue
            try:
                from io import BytesIO

                image = Image.open(BytesIO(raw))
                image.load()
                return image
            except Exception as exc:  # pragma: no cover - runtime guard
                logging.warning(
                    "Failed to decode screenshot (attempt %s): %s", attempts, exc
                )
                time.sleep(1)
        logging.error("Unable to capture valid screenshot after retries")
        return None

    def perform_tap(self, x: int, y: int) -> None:
        logging.info("ADB tap at (%s, %s)", x, y)
        self.run("shell", "input", "tap", str(x), str(y))

    def perform_swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> None:
        logging.info("ADB swipe (%s,%s) -> (%s,%s)", x1, y1, x2, y2)
        self.run(
            "shell",
            "input",
            "swipe",
            str(x1),
            str(y1),
            str(x2),
            str(y2),
            str(duration_ms),
        )

    def perform_sleep(self, seconds: float) -> None:
        logging.info("Sleep for %.2fs", seconds)
        time.sleep(seconds)

    def execute_steps(
        self, steps: Sequence[Dict[str, Any]], default_delay: float = 4.0
    ) -> None:
        for idx, step in enumerate(steps):
            action = step.get("action") or step.get("type")
            if not action:
                logging.warning("Skipping malformed UI step: %s", step)
                continue
            action = action.lower()
            if action == "tap":
                x, y = int(step["x"]), int(step["y"])
                self.perform_tap(x, y)
                time.sleep(step.get("delay", default_delay))
            elif action == "swipe":
                self.perform_swipe(
                    int(step["x1"]),
                    int(step["y1"]),
                    int(step["x2"]),
                    int(step["y2"]),
                    int(step.get("duration_ms", 300)),
                )
                time.sleep(step.get("delay", default_delay))
            elif action == "sleep":
                self.perform_sleep(
                    float(step.get("seconds", step.get("duration", 0)))
                )
            elif action == "shell":
                command = step.get("command")
                if isinstance(command, str):
                    args = command.split()
                else:
                    args = list(command or [])
                self.run("shell", *args)
                time.sleep(step.get("delay", default_delay))
            else:
                logging.warning(
                    "Unknown UI step action '%s' (step %s)", action, idx
                )

    def read_android_clipboard(self) -> Optional[str]:
        try:
            result = self.run("shell", "cmd", "clipboard", "get")
        except AdbError:
            return None
        text = result.stdout.strip()
        return text or None
