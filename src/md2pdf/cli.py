from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
from typing import cast

from . import config
from .mermaid import cleanup_mermaid_dir
from .pdf import PdfOptions, build_pdf


def positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("ожидалось положительное число") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("значение должно быть больше нуля")
    return parsed


def parse_margins(value: str) -> tuple[float, float, float, float]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("формат полей: left,right,top,bottom")
    margins = tuple(positive_float(part) for part in parts)
    return cast(tuple[float, float, float, float], margins)


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

    local_mmdc = config.ROOT / "node_modules" / ".bin" / "mmdc"
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
        print(dependency_report())
        return 0

    input_path = args.input.resolve()
    output_path = args.output.resolve()
    previous_mermaid_dir = config.MERMAID_DIR
    previous_quiet = config.QUIET
    if args.temp_dir:
        config.set_mermaid_dir(args.temp_dir.resolve())
    config.set_quiet(args.quiet)

    previous_strict = os.environ.get("MD2PDF_STRICT_MERMAID")
    if args.strict_mermaid:
        os.environ["MD2PDF_STRICT_MERMAID"] = "1"

    try:
        if not input_path.exists():
            parser.exit(1, f"md2pdf: входной файл не найден: {input_path}\n")
        if not input_path.is_file():
            parser.exit(1, f"md2pdf: входной путь не является файлом: {input_path}\n")
        options = PdfOptions(
            font_size=args.font_size or PdfOptions.font_size,
            line_height=args.line_height or PdfOptions.line_height,
            diagram_max_height_mm=args.diagram_max_height or PdfOptions.diagram_max_height_mm,
            margins_mm=args.margins or PdfOptions.margins_mm,
        )
        build_pdf(input_path, output_path, options)
        if not args.keep_temp:
            cleanup_mermaid_dir()
    except PermissionError as error:
        parser.exit(1, f"md2pdf: нет прав на чтение или запись: {error}\n")
    except RuntimeError as error:
        parser.exit(1, f"md2pdf: {error}\n")
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
