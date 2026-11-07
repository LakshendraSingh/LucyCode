"""
Screen automation and computer vision service for LucyCode workstation automation.

Provides screen geometry detection, multi-monitor inspection, OCR text detection,
visual template matching, and screenshot comparison with zero mandatory third-party deps.
"""

from __future__ import annotations

import base64
import difflib
import io
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    import mss
    _HAS_MSS = True
except ImportError:
    _HAS_MSS = False

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    import pytesseract
    _HAS_TESSERACT = True
except ImportError:
    _HAS_TESSERACT = False

try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False


@dataclass
class ScreenRegion:
    """Bounding box region on screen."""
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScreenRegion:
        return cls(
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
        )


@dataclass
class ScreenInfo:
    """Display environment metadata."""
    width: int
    height: int
    scale_factor: float = 1.0
    monitors: list[ScreenRegion] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "scale_factor": self.scale_factor,
            "monitors": [m.to_dict() for m in self.monitors],
        }


@dataclass
class OcrResult:
    """Detected text token and location."""
    text: str
    confidence: float
    region: ScreenRegion


@dataclass
class FindResult:
    """Search result for visual or textual screen targets."""
    found: bool
    x: int = 0
    y: int = 0
    confidence: float = 0.0
    region: ScreenRegion | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "x": self.x,
            "y": self.y,
            "confidence": round(self.confidence, 3),
            "region": self.region.to_dict() if self.region else None,
            "note": self.note,
        }


class ScreenAutomationService:
    """High-level desktop screen inspection and visual search."""

    def __init__(self) -> None:
        self._cached_info: ScreenInfo | None = None
        self._last_info_time: float = 0.0

    def get_screen_info(self, force_refresh: bool = False) -> ScreenInfo:
        """Inspect and return monitor geometry and scale factors."""
        now = time.time()
        if not force_refresh and self._cached_info and (now - self._last_info_time < 30.0):
            return self._cached_info

        monitors: list[ScreenRegion] = []
        primary_w, primary_h = 1920, 1080
        scale = 1.0

        if _HAS_MSS:
            try:
                with mss.mss() as sct:
                    for i, m in enumerate(sct.monitors[1:], start=1):
                        monitors.append(ScreenRegion(x=m["left"], y=m["top"], width=m["width"], height=m["height"]))
                    if monitors:
                        primary_w = monitors[0].width
                        primary_h = monitors[0].height
            except Exception as e:
                logger.debug("mss get_screen_info failed: %s", e)

        if not monitors:
            # Fallback to macOS system_profiler
            try:
                proc = subprocess.run(
                    ["system_profiler", "SPDisplaysDataType"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if proc.returncode == 0:
                    for line in proc.stdout.splitlines():
                        if "Resolution" in line:
                            match = re.search(r"(\d+)\s*x\s*(\d+)", line)
                            if match:
                                w, h = int(match.group(1)), int(match.group(2))
                                monitors.append(ScreenRegion(x=0, y=0, width=w, height=h))
                                primary_w, primary_h = w, h
                                if "Retina" in line or "@ 2x" in line or "UI Looks like" in line:
                                    scale = 2.0
                                break
            except Exception as e:
                logger.debug("system_profiler displays check failed: %s", e)

        if not monitors:
            monitors.append(ScreenRegion(x=0, y=0, width=primary_w, height=primary_h))

        info = ScreenInfo(
            width=primary_w,
            height=primary_h,
            scale_factor=scale,
            monitors=monitors,
        )
        self._cached_info = info
        self._last_info_time = now
        return info

    def screenshot(self, monitor: int = 0, region: ScreenRegion | None = None) -> str:
        """
        Capture desktop screenshot and return base64 encoded PNG.
        Uses mss if available, otherwise native screencapture on macOS.
        """
        if _HAS_MSS and _HAS_PIL:
            try:
                with mss.mss() as sct:
                    target_monitor = sct.monitors[monitor] if monitor < len(sct.monitors) else sct.monitors[0]
                    if region:
                        bbox = {
                            "left": region.x,
                            "top": region.y,
                            "width": region.width,
                            "height": region.height,
                        }
                    else:
                        bbox = target_monitor
                    raw = sct.grab(bbox)
                    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    return base64.b64encode(buf.getvalue()).decode("utf-8")
            except Exception as e:
                logger.debug("mss capture failed, falling back to subprocess: %s", e)

        # Subprocess fallback for macOS
        tmp_file = f"/tmp/lucy_scr_{int(time.time()*1000)}.png"
        cmd = ["screencapture", "-x"]
        if region:
            cmd.extend(["-R", f"{region.x},{region.y},{region.width},{region.height}"])
        cmd.append(tmp_file)

        proc = subprocess.run(cmd, capture_output=True, timeout=10)
        if proc.returncode != 0 or not os.path.exists(tmp_file):
            raise RuntimeError(f"screencapture failed: {proc.stderr.decode(errors='ignore')}")

        try:
            with open(tmp_file, "rb") as f:
                data = f.read()
            return base64.b64encode(data).decode("utf-8")
        finally:
            if os.path.exists(tmp_file):
                try:
                    os.unlink(tmp_file)
                except OSError:
                    pass

    def find_text_on_screen(self, text: str, case_sensitive: bool = False) -> FindResult:
        """
        Locate textual element coordinates on screen via OCR.
        """
        clean_target = text if case_sensitive else text.lower()
        if not _HAS_TESSERACT or not _HAS_PIL:
            return FindResult(
                found=False,
                note="pytesseract or PIL is not installed. Run `pip install pytesseract pillow` to enable OCR screen search."
            )

        try:
            b64 = self.screenshot()
            img_bytes = base64.b64decode(b64)
            img = Image.open(io.BytesIO(img_bytes))

            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            n_boxes = len(data["text"])
            for i in range(n_boxes):
                word = data["text"][i].strip()
                if not word:
                    continue
                match_word = word if case_sensitive else word.lower()
                if clean_target in match_word or match_word in clean_target:
                    x = data["left"][i]
                    y = data["top"][i]
                    w = data["width"][i]
                    h = data["height"][i]
                    conf = float(data["conf"][i]) / 100.0 if data["conf"][i] != "-1" else 0.5
                    center_x = x + (w // 2)
                    center_y = y + (h // 2)
                    return FindResult(
                        found=True,
                        x=center_x,
                        y=center_y,
                        confidence=conf,
                        region=ScreenRegion(x=x, y=y, width=w, height=h),
                        note=f"Matched text '{word}' with confidence {conf:.2f}",
                    )
        except Exception as e:
            logger.error("OCR execution failed: %s", e)
            return FindResult(found=False, note=f"OCR error: {e}")

        return FindResult(found=False, note=f"Text '{text}' not found on screen.")

    def find_image_on_screen(self, template_path: str, threshold: float = 0.8) -> FindResult:
        """
        Locate template image coordinates on screen using OpenCV template matching.
        """
        if not os.path.exists(template_path):
            return FindResult(found=False, note=f"Template file '{template_path}' does not exist.")

        if not _HAS_CV2 or not _HAS_PIL:
            return FindResult(
                found=False,
                note="opencv-python is not installed. Run `pip install opencv-python pillow` to enable visual template matching."
            )

        try:
            b64 = self.screenshot()
            img_bytes = base64.b64decode(b64)
            screen_img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
            template = cv2.imread(template_path, cv2.IMREAD_COLOR)

            if template is None or screen_img is None:
                return FindResult(found=False, note="Failed to load image frames for comparison.")

            th, tw = template.shape[:2]
            res = cv2.matchTemplate(screen_img, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if max_val >= threshold:
                center_x = max_loc[0] + (tw // 2)
                center_y = max_loc[1] + (th // 2)
                return FindResult(
                    found=True,
                    x=center_x,
                    y=center_y,
                    confidence=float(max_val),
                    region=ScreenRegion(x=max_loc[0], y=max_loc[1], width=tw, height=th),
                    note=f"Template matched with score {max_val:.3f}",
                )
            return FindResult(found=False, confidence=float(max_val), note=f"Best match score {max_val:.3f} below threshold {threshold}")
        except Exception as e:
            return FindResult(found=False, note=f"Template match error: {e}")

    def wait_for_text(self, text: str, timeout: float = 30.0, interval: float = 1.0) -> bool:
        """Block until expected text appears on screen or timeout expires."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            res = self.find_text_on_screen(text)
            if res.found:
                return True
            time.sleep(interval)
        return False

    def get_pixel_color(self, x: int, y: int) -> tuple[int, int, int]:
        """Sample pixel RGB color at given coordinates."""
        from lucy.services.computer_use import get_computer_use_service
        return get_computer_use_service().get_pixel_color(x, y)

    def compare_screenshots(self, b64_a: str, b64_b: str) -> float:
        """
        Compare two base64 PNG images and return a similarity score between 0.0 and 1.0.
        """
        if b64_a == b64_b:
            return 1.0

        if _HAS_PIL:
            try:
                img_a = Image.open(io.BytesIO(base64.b64decode(b64_a))).convert("RGB")
                img_b = Image.open(io.BytesIO(base64.b64decode(b64_b))).convert("RGB")
                if img_a.size != img_b.size:
                    img_b = img_b.resize(img_a.size)

                # Subsampled difference
                step = 4
                diff = 0
                total = 0
                w, h = img_a.size
                pix_a = img_a.load()
                pix_b = img_b.load()
                for px in range(0, w, step):
                    for py in range(0, h, step):
                        ca = pix_a[px, py]
                        cb = pix_b[px, py]
                        pixel_diff = abs(ca[0]-cb[0]) + abs(ca[1]-cb[1]) + abs(ca[2]-cb[2])
                        diff += pixel_diff / (255 * 3)
                        total += 1
                return max(0.0, 1.0 - (diff / max(1, total)))
            except Exception as e:
                logger.debug("PIL screenshot compare failed: %s", e)

        # Fallback to string similarity on truncated data chunks
        sm = difflib.SequenceMatcher(None, b64_a[:2000], b64_b[:2000])
        return sm.ratio()


_screen_service: ScreenAutomationService | None = None


def get_screen_automation() -> ScreenAutomationService:
    global _screen_service
    if _screen_service is None:
        _screen_service = ScreenAutomationService()
    return _screen_service
