from __future__ import annotations

import argparse
import math
import os
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import cast
from uuid import uuid4

from reportlab.platypus.doctemplate import LayoutError

from . import config
from .mermaid import cleanup_mermaid_dir
from .pdf import PdfOptions, build_pdf


def positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("ожидалось положительное число") from error
    if not math.isfinite(parsed):
        raise argparse.ArgumentTypeError("значение должно быть конечным числом")
    if parsed <= 0:
        raise argparse.ArgumentTypeError("значение должно быть больше нуля")
    return parsed


def parse_margins(value: str) -> tuple[float, float, float, float]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("формат полей: left,right,top,bottom")
    margins = tuple(positive_float(part) for part in parts)
    return cast(tuple[float, float, float, float], margins)


def validate_margins(margins: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    left, right, top, bottom = margins
    page_width_mm = 210
    page_height_mm = 297
    min_content_width_mm = 60
    min_content_height_mm = 60
    if page_width_mm - left - right < min_content_width_mm:
        raise argparse.ArgumentTypeError("ширина области текста должна быть не меньше 60 мм")
    if page_height_mm - top - bottom < min_content_height_mm:
        raise argparse.ArgumentTypeError("высота области текста должна быть не меньше 60 мм")
    return margins


def bounded_float(name: str, value: float, lower: float, upper: float) -> float:
    if not lower <= value <= upper:
        raise argparse.ArgumentTypeError(f"{name} должен быть от {lower:g} до {upper:g}")
    return value


def dependency_report() -> str:
    lines = []
    try:
        regular = config.pick_font("regular")
        bold = config.pick_font("bold")
        lines.append(f"fonts: ok ({Path(regular).name}, {Path(bold).name})")
    except RuntimeError as error:
        lines.append(f"fonts: missing ({error})")

    node = shutil.which("node")
    lines.append(f"node: {'ok (' + node + ')' if node else 'missing'}")

    local_mmdc = config.PROJECT_ROOT / "node_modules" / ".bin" / "mmdc"
    mmdc = local_mmdc if local_mmdc.exists() else shutil.which("mmdc")
    if mmdc:
        lines.append(f"mermaid-cli: ok ({mmdc})")
    else:
        lines.append("mermaid-cli: missing (будет использован встроенный рендерер)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="md2pdf",
        description="Конвертирует Markdown в PDF A4 portrait с Mermaid и базовыми правилами оформления по ГОСТ Р 7.32."
    )
    parser.add_argument("input", nargs="?", type=Path, default=config.DEFAULT_INPUT, help="Входной Markdown-файл.")
    parser.add_argument("output", nargs="?", type=Path, default=config.DEFAULT_OUTPUT, help="Выходной PDF-файл.")
    parser.add_argument("--font-size", type=positive_float, help="Размер основного текста в пунктах.")
    parser.add_argument("--line-height", type=positive_float, help="Множитель межстрочного интервала.")
    parser.add_argument("--diagram-max-height", type=positive_float, help="Максимальная высота диаграммы в мм.")
    parser.add_argument("--margins", type=parse_margins, help="Поля страницы в мм: left,right,top,bottom.")
    parser.add_argument("--strict-mermaid", action="store_true", help="Останавливать сборку при ошибке Mermaid CLI.")
    parser.add_argument("--temp-dir", type=Path, help="Директория для временных Mermaid-файлов.")
    parser.add_argument("--keep-temp", action="store_true", help="Не удалять временные Mermaid-файлы после сборки.")
    parser.add_argument("--quiet", action="store_true", help="Не печатать предупреждения встроенного рендеринга.")
    parser.add_argument(
        "--check-deps",
        action="store_true",
        help="Проверить шрифты, Node.js и Mermaid CLI без сборки PDF.",
    )
    parser.add_argument("--version", action="version", version=f"md2pdf {config.VERSION}")
    args = parser.parse_args(argv)
    if args.check_deps:
        if args.input != config.DEFAULT_INPUT or args.output != config.DEFAULT_OUTPUT:
            parser.exit(1, "md2pdf: --check-deps не принимает входной и выходной файлы\n")
        print(dependency_report())
        return 0

    input_path = args.input.resolve()
    output_path = args.output.resolve()
    previous_mermaid_dir = config.MERMAID_DIR
    previous_quiet = config.QUIET
    if args.temp_dir:
        config.set_mermaid_dir(args.temp_dir.resolve())
    else:
        config.set_mermaid_dir(previous_mermaid_dir / f"run-{os.getpid()}-{uuid4().hex[:8]}")
    config.set_quiet(args.quiet)

    previous_strict = os.environ.get("MD2PDF_STRICT_MERMAID")
    if args.strict_mermaid:
        os.environ["MD2PDF_STRICT_MERMAID"] = "1"

    try:
        if not input_path.exists():
            parser.exit(1, f"md2pdf: входной файл не найден: {input_path}\n")
        if not input_path.is_file():
            parser.exit(1, f"md2pdf: входной путь не является файлом: {input_path}\n")
        if input_path == output_path:
            parser.exit(1, "md2pdf: входной и выходной файлы должны быть разными\n")
        options = PdfOptions(
            font_size=bounded_float("font-size", args.font_size or PdfOptions.font_size, 6, 72),
            line_height=bounded_float("line-height", args.line_height or PdfOptions.line_height, 1, 3),
            diagram_max_height_mm=bounded_float(
                "diagram-max-height",
                args.diagram_max_height or PdfOptions.diagram_max_height_mm,
                10,
                250,
            ),
            margins_mm=validate_margins(args.margins or PdfOptions.margins_mm),
        )
        build_pdf(input_path, output_path, options)
        if not args.keep_temp:
            cleanup_mermaid_dir()
            if not args.temp_dir and config.MERMAID_DIR.exists():
                try:
                    config.MERMAID_DIR.rmdir()
                except OSError:
                    pass
    except PermissionError as error:
        parser.exit(1, f"md2pdf: нет прав на чтение или запись: {error}\n")
    except argparse.ArgumentTypeError as error:
        parser.exit(1, f"md2pdf: {error}\n")
    except UnicodeDecodeError as error:
        parser.exit(1, f"md2pdf: входной файл должен быть в UTF-8: {error}\n")
    except LayoutError as error:
        message = unicodedata.normalize("NFKD", str(error)).splitlines()[0]
        parser.exit(1, f"md2pdf: не удалось разместить содержимое на странице: {message}\n")
    except RuntimeError as error:
        parser.exit(1, f"md2pdf: {error}\n")
    except subprocess.SubprocessError as error:
        parser.exit(1, f"md2pdf: Mermaid CLI error: {error}\n")
    except OSError as error:
        parser.exit(1, f"md2pdf: ошибка файловой системы: {error}\n")
    finally:
        if args.strict_mermaid:
            if previous_strict is None:
                os.environ.pop("MD2PDF_STRICT_MERMAID", None)
            else:
                os.environ["MD2PDF_STRICT_MERMAID"] = previous_strict
        config.set_mermaid_dir(previous_mermaid_dir)
        config.set_quiet(previous_quiet)
    return 0
