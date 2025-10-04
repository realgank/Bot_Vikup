"""Parsing helpers for extracting structured information."""
from __future__ import annotations

import logging
import platform
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence

LINE_REGEX = re.compile(r"^\d+\s+.+?\s+[\d\.,]+\s+[\d\.,]+$")
SANITIZE_REGEX = re.compile(
    "[^0-9A-Za-zА-Яа-яЁё\\-_'\"()\\[\\]{}.,:;!? ]+"
)
MULTISPACE_REGEX = re.compile(r"\s{2,}")


@dataclass
class ContractItem:
    item_name: str
    quantity: float
    est_value: float


def sanitize_item_name(name: str) -> str:
    cleaned = SANITIZE_REGEX.sub(" ", name)
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_nick(raw: str) -> str:
    if "--->" in raw:
        return raw.split("--->", 1)[0].strip()
    return raw.strip()


def extract_system(raw: str) -> str:
    text = raw.strip()
    pos = text.find("-")
    if pos >= 0 and pos > 5:
        return text[:pos].strip()
    return text


class CompositionParser:
    """Parse contract composition either from clipboards or OCR."""

    def parse_lines(self, text: str) -> List[ContractItem]:
        items: List[ContractItem] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if not LINE_REGEX.match(line):
                parts = [part for part in MULTISPACE_REGEX.split(line) if part]
            else:
                parts = line.split()
            if len(parts) < 4:
                continue
            qty_raw = parts[-2]
            est_raw = parts[-1]
            name_parts = parts[1:-2]
            name = sanitize_item_name(" ".join(name_parts))
            try:
                quantity = float(qty_raw.replace(",", "."))
                est_value = float(est_raw.replace(",", "."))
            except ValueError:
                logging.debug("Failed to parse numeric values in line: %s", line)
                continue
            if not name:
                continue
            items.append(
                ContractItem(item_name=name, quantity=quantity, est_value=est_value)
            )
        return items

    def read_host_clipboard(self) -> Optional[str]:
        system = platform.system().lower()
        commands: List[Sequence[str]] = []
        if system == "windows":
            commands.append(["powershell", "-NoProfile", "-Command", "Get-Clipboard"])
        elif system == "darwin":
            commands.append(["pbpaste"])
        else:  # Linux/BSD
            commands.append(["xclip", "-selection", "clipboard", "-o"])
            commands.append(["xsel", "--clipboard", "--output"])
        for cmd in commands:
            try:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                    encoding="utf-8",
                )
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
            text = result.stdout.strip()
            if text:
                logging.debug("Obtained host clipboard text (%d chars)", len(text))
                return text
        return None

    def parse_clipboards(
        self,
        adb_clipboard: Optional[str],
        host_clipboard: Optional[str],
    ) -> Optional[List[ContractItem]]:
        for label, data in (("host", host_clipboard), ("android", adb_clipboard)):
            if data:
                items = self.parse_lines(data)
                if items:
                    logging.info("Parsed composition from %s clipboard", label)
                    return items
                logging.debug("Clipboard %s data not parseable", label)
        return None

    def parse_from_ocr(self, ocr_text: str) -> Optional[List[ContractItem]]:
        if not ocr_text.strip():
            return None
        items = self.parse_lines(ocr_text)
        if items:
            logging.info("Parsed composition from OCR fallback")
        return items or None
