from __future__ import annotations

import html
import re

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle


def clean_inline(text: str) -> str:
    text = text.strip()
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = text.replace("`", "")
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__([^_]+)__", r"<b>\1</b>", text)
    safe = html.escape(text, quote=False)
    safe = safe.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    return safe


def clean_heading(text: str) -> str:
    return clean_inline(text.strip())


def split_table_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def is_table_divider(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def make_cell(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(clean_inline(text), style)


def column_widths(count: int, available_width: float) -> list[float]:
    if count <= 1:
        return [available_width]
    if count == 2:
        return [available_width * 0.34, available_width * 0.66]
    if count == 3:
        return [available_width * 0.28, available_width * 0.36, available_width * 0.36]
    return [available_width / count] * count


def add_table(story: list, rows: list[list[str]], styles: dict, available_width: float) -> None:
    if not rows:
        return
    max_cols = max(len(row) for row in rows)
    normalized = [row + [""] * (max_cols - len(row)) for row in rows]
    data = []
    for row_index, row in enumerate(normalized):
        style = styles["table_header"] if row_index == 0 else styles["table_cell"]
        data.append([make_cell(cell, style) for cell in row])

    table = Table(
        data,
        colWidths=column_widths(max_cols, available_width),
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=True,
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#666666")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#333333")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 4 * mm))


def flush_paragraph(story: list, buffer: list[str], style: ParagraphStyle) -> None:
    if not buffer:
        return
    text = " ".join(part.strip() for part in buffer if part.strip())
    if text:
        story.append(Paragraph(clean_inline(text), style))
        story.append(Spacer(1, 0.5 * mm))
    buffer.clear()


def flush_bullets(story: list, bullets: list[str], styles: dict, available_width: float) -> None:
    if not bullets:
        return
    for item in bullets:
        story.append(Paragraph(f"–&nbsp;&nbsp;{clean_inline(item)}", styles["list_body"]))
    story.append(Spacer(1, 0.5 * mm))
    bullets.clear()

