from __future__ import annotations

from pathlib import Path

from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT = Path.cwd()
DEFAULT_INPUT = ROOT / "README.md"
DEFAULT_OUTPUT = ROOT / "README.pdf"
VERSION = "1.0.6"

FONT_REGULAR = ""
FONT_BOLD = ""
FONT_CANDIDATES = {
    "regular": [
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        str(Path.home() / "Library/Fonts/Times New Roman.ttf"),
        "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    ],
    "bold": [
        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
        str(Path.home() / "Library/Fonts/Times New Roman Bold.ttf"),
        "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    ],
}
MERMAID_DIR = ROOT / ".md2pdf" / "mermaid"
MERMAID_COUNTER = 0
PARAGRAPH_INDENT = 12.5 * mm
QUIET = False


def pick_font(kind: str) -> str:
    for candidate in FONT_CANDIDATES[kind]:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError(
        "Не найден шрифт Times New Roman или совместимый serif-шрифт. "
        "Установите Times New Roman либо DejaVu Serif."
    )


def register_fonts() -> tuple[str, str]:
    global FONT_REGULAR, FONT_BOLD
    FONT_REGULAR = pick_font("regular")
    FONT_BOLD = pick_font("bold")
    regular = "GostTimes"
    bold = "GostTimesBold"
    if regular not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(regular, FONT_REGULAR))
    if bold not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(bold, FONT_BOLD))
    return regular, bold


def set_mermaid_dir(path: Path) -> None:
    global MERMAID_DIR
    MERMAID_DIR = path


def set_quiet(value: bool) -> None:
    global QUIET
    QUIET = value
