"""OCR helpers backed by ``pytesseract``."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence

try:  # pragma: no cover - optional dependency guards
    import pytesseract
    from PIL import Image
except ImportError:  # pragma: no cover - runtime guard
    pytesseract = None  # type: ignore[assignment]
    Image = None  # type: ignore[assignment]


class OcrEngine:
    """Wrapper around :mod:`pytesseract` with safe cropping helpers."""

    def __init__(self, lang: str, tesseract_cmd: Optional[str]) -> None:
        self.lang = lang
        self.training_dir = Path("training")
        self.user_words_file = self.training_dir / f"{self.lang}.user-words"
        if pytesseract is not None:
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            if not self.user_words_file.exists():
                self.training_dir.mkdir(parents=True, exist_ok=True)
                self.user_words_file.touch()
        else:
            logging.warning("pytesseract is not available – OCR will fail")

    def extract_text(
        self,
        image: "Image.Image",
        box_name: str,
        ocr_boxes: Dict[str, Sequence[int]],
        psm: int = 6,
    ) -> str:
        box = ocr_boxes.get(box_name)
        if not box:
            logging.warning("OCR box '%s' not configured", box_name)
            return ""
        cropped = self._safe_crop(image, box)
        if cropped is None:
            return ""
        if pytesseract is None:
            raise RuntimeError("pytesseract not installed")
        custom = f"--psm {psm}"
        if self.user_words_file.exists():
            custom += f" --user-words {self.user_words_file}"
        text = pytesseract.image_to_string(cropped, lang=self.lang, config=custom)
        logging.debug("OCR result for box %s: %s", box_name, text.strip())
        return text.strip()

    def extract_any_text(
        self,
        image: "Image.Image",
        box_name: str,
        ocr_boxes: Dict[str, Sequence[int]],
        psm: int = 6,
    ) -> bool:
        text = self.extract_text(image, box_name, ocr_boxes, psm=psm)
        return bool(text.strip())

    def extract_table(
        self,
        image: "Image.Image",
        box_name: str,
        ocr_boxes: Dict[str, Sequence[int]],
        psm: int = 6,
    ) -> str:
        return self.extract_text(image, box_name, ocr_boxes, psm=psm)

    def crop_box(
        self, image: "Image.Image", box_name: str, ocr_boxes: Dict[str, Sequence[int]]
    ) -> Optional["Image.Image"]:
        box = ocr_boxes.get(box_name)
        if not box:
            logging.warning("OCR box '%s' not configured", box_name)
            return None
        return self._safe_crop(image, box)

    def add_training_words(self, words: Iterable[str]) -> None:
        """Persist ``words`` to the user words file for incremental training."""

        unique_words = []
        seen = set()
        for word in words:
            word = word.strip()
            if not word:
                continue
            if word in seen:
                continue
            seen.add(word)
            unique_words.append(word)

        if not unique_words:
            return

        try:
            existing = set()
            if self.user_words_file.exists():
                with self.user_words_file.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            existing.add(line)
            new_words = [word for word in unique_words if word not in existing]
            if not new_words:
                return
            self.training_dir.mkdir(parents=True, exist_ok=True)
            with self.user_words_file.open("a", encoding="utf-8") as fh:
                for word in new_words:
                    fh.write(f"{word}\n")
            logging.info("Added %s new OCR training words", len(new_words))
        except Exception:
            logging.exception("Failed to append OCR training words")

    def _safe_crop(
        self, image: "Image.Image", box: Sequence[int]
    ) -> Optional["Image.Image"]:
        if len(box) != 4:
            logging.warning("Invalid OCR box coordinates: %s", box)
            return None
        left, top, right, bottom = box
        width, height = image.size
        left, right = sorted((int(left), int(right)))
        top, bottom = sorted((int(top), int(bottom)))
        left = max(0, min(width, left))
        right = max(0, min(width, right))
        top = max(0, min(height, top))
        bottom = max(0, min(height, bottom))
        if left >= right or top >= bottom:
            logging.warning(
                "Safe crop rejected invalid box (%s, %s, %s, %s) for image %s x %s",
                left,
                top,
                right,
                bottom,
                width,
                height,
            )
            return None
        return image.crop((left, top, right, bottom))
