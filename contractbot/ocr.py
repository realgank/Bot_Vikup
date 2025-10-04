"""OCR helpers backed by ``pytesseract``."""
from __future__ import annotations

import logging
from typing import Dict, Optional, Sequence

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
        if pytesseract is not None:
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
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
