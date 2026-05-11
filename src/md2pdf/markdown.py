from __future__ import annotations

import html
import re

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle


def find_unescaped(text: str, char: str, start: int) -> int:
    escaped = False
    for index in range(start, len(text)):
        current = text[index]
        if escaped:
            escaped = False
            continue
        if current == "\\":
            escaped = True
            continue
        if current == char:
            return index
    return -1


def is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def unescape_markdown_text(text: str) -> str:
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>])", r"\1", text)


def strip_markdown_targets(text: str, image: bool) -> str:
    opener = "![" if image else "["
    result = []
    index = 0
    while index < len(text):
        start = text.find(opener, index)
        if start == -1:
            result.append(text[index:])
            break
        if is_escaped(text, start):
            result.append(text[index : start + len(opener)])
            index = start + len(opener)
            continue
        if not image and start > 0 and text[start - 1] == "!":
            result.append(text[index : start + len(opener)])
            index = start + len(opener)
            continue
        label_start = start + len(opener)
        label_end = find_unescaped(text, "]", label_start)
        if label_end == -1 or label_end + 1 >= len(text) or text[label_end + 1] != "(":
            result.append(text[index : start + len(opener)])
            index = start + len(opener)
            continue

        depth = 1
        target_index = label_end + 2
        escaped = False
        while target_index < len(text) and depth:
            char = text[target_index]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            target_index += 1
        if depth:
            result.append(text[index : start + len(opener)])
            index = start + len(opener)
            continue
        result.append(text[index:start])
        result.append(unescape_markdown_text(text[label_start:label_end]))
        index = target_index
    return "".join(result)


def clean_inline(text: str) -> str:
    text = text.strip()
    text = strip_markdown_targets(text, image=True)
    text = strip_markdown_targets(text, image=False)
    text = text.replace("`", "")
    bold_parts: list[str] = []

    def keep_bold(match: re.Match[str]) -> str:
        token = f"\x00MD2PDF_BOLD_{len(bold_parts)}\x00"
        bold_parts.append(f"<b>{html.escape(match.group(1), quote=False)}</b>")
        return token

    text = re.sub(r"\*\*([^*]+)\*\*", keep_bold, text)
    text = re.sub(r"__([^_]+)__", keep_bold, text)
    safe = html.escape(text, quote=False)
    for index, bold in enumerate(bold_parts):
        safe = safe.replace(f"\x00MD2PDF_BOLD_{index}\x00", bold)
    return safe


def clean_heading(text: str) -> str:
    return clean_inline(text.strip())


def split_table_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    cells = []
    current = []
    in_code = False
    bracket_depth = 0
    escaped = False
    for char in line:
        if escaped:
            if char != "|":
                current.append("\\")
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "`":
            in_code = not in_code
            current.append(char)
            continue
        if not in_code and char == "[":
            bracket_depth += 1
        elif not in_code and char == "]" and bracket_depth:
            bracket_depth -= 1
        if char == "|" and not in_code and bracket_depth == 0:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


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
