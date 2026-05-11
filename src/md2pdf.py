from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont


ROOT = Path.cwd()
DEFAULT_INPUT = ROOT / "README.md"
DEFAULT_OUTPUT = ROOT / "README.pdf"
FONT_REGULAR = ""
FONT_BOLD = ""
FONT_CANDIDATES = {
    "regular": [
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    ],
    "bold": [
        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    ],
}
MERMAID_DIR = ROOT / ".md2pdf" / "mermaid"
MERMAID_COUNTER = 0
PARAGRAPH_INDENT = 12.5 * mm


def pick_font(kind: str) -> str:
    for candidate in FONT_CANDIDATES[kind]:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError(
        "Не найден шрифт Times New Roman или совместимый serif fallback. "
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
    table_commands = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#666666")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#333333")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    table.setStyle(TableStyle(table_commands))
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


def flush_code(story: list, code: list[str], styles: dict, language: str, available_width: float) -> None:
    if not code:
        return
    if language == "mermaid":
        image_path = render_mermaid_image(code)
        if image_path:
            with PILImage.open(image_path) as rendered:
                ratio = rendered.height / rendered.width
            max_height = 135 * mm
            target_width = available_width
            target_height = available_width * ratio
            if target_height > max_height:
                target_height = max_height
                target_width = max_height / ratio
            story.append(Image(str(image_path), width=target_width, height=target_height, kind="proportional"))
            story.append(Spacer(1, 3 * mm))
            code.clear()
            return
    block = Table(
        [["", Preformatted("\n".join(code), styles["code"])]],
        colWidths=[PARAGRAPH_INDENT, available_width - PARAGRAPH_INDENT],
        hAlign="LEFT",
    )
    block.setStyle(
        TableStyle(
            [
                ("BOX", (1, 0), (1, 0), 0.35, colors.HexColor("#666666")),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ("TOPPADDING", (0, 0), (0, 0), 0),
                ("BOTTOMPADDING", (0, 0), (0, 0), 0),
                ("LEFTPADDING", (1, 0), (1, 0), 5),
                ("RIGHTPADDING", (1, 0), (1, 0), 5),
                ("TOPPADDING", (1, 0), (1, 0), 4),
                ("BOTTOMPADDING", (1, 0), (1, 0), 4),
            ]
        )
    )
    story.append(KeepTogether([block]))
    story.append(Spacer(1, 3 * mm))
    code.clear()


def load_font(size: int, bold: bool = False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size=size)


def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if text_size(draw, test, font)[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:4]


def extract_mermaid_label(token: str) -> tuple[str, str]:
    token = token.strip()
    match = re.match(r'([A-Za-z0-9_]+)\["(.+?)"\]', token)
    if match:
        return match.group(1), match.group(2)
    match = re.match(r"([A-Za-z0-9_]+)\[(.+?)\]", token)
    if match:
        return match.group(1), match.group(2).strip('"')
    match = re.match(r"([A-Za-z0-9_]+)\{(.+?)\}", token)
    if match:
        return match.group(1), match.group(2).strip('"')
    match = re.match(r"([A-Za-z0-9_]+)", token)
    if match:
        return match.group(1), match.group(1)
    return token, token


def render_mermaid_image(code: list[str]) -> Path | None:
    global MERMAID_COUNTER
    MERMAID_COUNTER += 1
    MERMAID_DIR.mkdir(parents=True, exist_ok=True)
    kind = next((line.strip() for line in code if line.strip()), "")
    if kind.startswith("xychart"):
        path = MERMAID_DIR / f"diagram_{MERMAID_COUNTER:02d}.png"
        render_xychart(code, path)
        crop_mermaid_png(path)
        return path
    if kind.startswith("sequenceDiagram"):
        path = MERMAID_DIR / f"diagram_{MERMAID_COUNTER:02d}.png"
        render_sequence(code, path)
        crop_mermaid_png(path, bottom_padding=260)
        return path
    real_rendered = render_mermaid_with_cli(code, MERMAID_COUNTER)
    if real_rendered:
        return real_rendered
    path = MERMAID_DIR / f"diagram_{MERMAID_COUNTER:02d}.png"
    if kind.startswith("sequenceDiagram"):
        render_sequence(code, path)
    elif kind.startswith("stateDiagram"):
        render_state(code, path)
    elif kind.startswith("xychart"):
        render_xychart(code, path)
    elif kind.startswith("flowchart"):
        render_flowchart(code, path)
    else:
        return None
    return path


def render_mermaid_with_cli(code: list[str], index: int) -> Path | None:
    local_mmdc = ROOT / "node_modules" / ".bin" / "mmdc"
    mmdc = str(local_mmdc) if local_mmdc.exists() else shutil.which("mmdc")
    if not mmdc:
        return None
    first = next((line.strip() for line in code if line.strip()), "")

    source = MERMAID_DIR / f"diagram_{index:02d}.mmd"
    target = MERMAID_DIR / f"diagram_{index:02d}.png"
    puppeteer_config = MERMAID_DIR / "puppeteer-config.json"
    config = MERMAID_DIR / "mermaid-config.json"
    source.write_text("\n".join(prepare_mermaid_for_pdf(code)) + "\n", encoding="utf-8")
    puppeteer_config.write_text(
        json.dumps(
            {
                "args": [
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ]
            }
        ),
        encoding="utf-8",
    )
    config.write_text(
        json.dumps(
            {
                "theme": "base",
                "themeVariables": {
                    "fontFamily": "Times New Roman, Times, serif",
                    "fontSize": "12px",
                    "primaryColor": "#ffffff",
                    "primaryTextColor": "#000000",
                    "primaryBorderColor": "#000000",
                    "lineColor": "#000000",
                    "secondaryColor": "#ffffff",
                    "tertiaryColor": "#ffffff",
                    "background": "#ffffff",
                    "mainBkg": "#ffffff",
                    "secondBkg": "#ffffff",
                    "tertiaryBkg": "#ffffff",
                    "nodeBorder": "#000000",
                    "clusterBkg": "#ffffff",
                    "clusterBorder": "#000000",
                },
                "flowchart": {
                    "htmlLabels": True,
                    "nodeSpacing": 35,
                    "rankSpacing": 45,
                },
                "sequence": {
                    "mirrorActors": False,
                    "messageFontSize": 12,
                    "actorFontSize": 12,
                    "noteFontSize": 12,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    width, height = resolve_mermaid_viewport(code)
    command = [
        str(mmdc),
        "--quiet",
        "--theme",
        "neutral",
        "--configFile",
        str(config),
        "--backgroundColor",
        "white",
        "--width",
        str(width),
        "--height",
        str(height),
        "--scale",
        "2",
        "--puppeteerConfigFile",
        str(puppeteer_config),
        "--input",
        str(source),
        "--output",
        str(target),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=60)
    if result.returncode != 0 or not target.exists():
        message = (result.stderr or result.stdout or "unknown Mermaid CLI error").strip()
        raise RuntimeError(f"Mermaid render failed for {source.name}: {message}")
    crop_mermaid_png(target, bottom_padding=140 if first.startswith("sequenceDiagram") else 36)
    return target


def resolve_mermaid_viewport(code: list[str]) -> tuple[int, int]:
    first = next((line.strip() for line in code if line.strip()), "")
    if first.startswith("sequenceDiagram"):
        participants = sum(1 for line in code if line.strip().startswith("participant "))
        messages = sum(1 for line in code if "->>" in line)
        return max(2600, participants * 950), max(1500, messages * 190 + 650)
    if first.startswith("flowchart"):
        edge_count = sum(1 for line in code if "-->" in line)
        return (2200, max(1500, edge_count * 260)) if edge_count >= 5 else (2000, 1300)
    if first.startswith("stateDiagram"):
        return 2200, 1600
    return 2000, 1400


def prepare_mermaid_for_pdf(code: list[str]) -> list[str]:
    prepared = list(code)
    if not prepared:
        return prepared
    first = prepared[0].strip()
    edge_count = sum(1 for line in prepared if "-->" in line)
    if first == "flowchart LR" and edge_count >= 5:
        prepared[0] = "flowchart TB"
    return prepared


def make_two_row_flowchart(code: list[str]) -> list[str]:
    _, labels, edges = parse_edges(code)
    if len(labels) < 6:
        return code

    ordered: list[str] = []
    for source, target, _ in edges:
        if source not in ordered:
            ordered.append(source)
        if target not in ordered:
            ordered.append(target)

    split_at = max(3, (len(ordered) + 1) // 2)
    row1 = ordered[:split_at]
    row2 = ordered[split_at:]
    if not row2:
        return code

    def node(node_id: str) -> str:
        return f'{node_id}["{labels.get(node_id, node_id)}"]'

    lines = ["flowchart TB", '  subgraph row1[" "]', "    direction LR"]
    lines.append("    " + " --> ".join(node(item) for item in row1))
    lines.extend(['  end', '  subgraph row2[" "]', "    direction LR"])
    lines.append("    " + " --> ".join(node(item) for item in row2))
    lines.append("  end")
    lines.append(f"  {row1[-1]} --> {row2[0]}")
    for source, target, _ in edges:
        if ordered.index(target) <= ordered.index(source):
            lines.append(f"  {source} --> {target}")
    return lines


def crop_mermaid_png(path: Path, bottom_padding: int = 36) -> None:
    with PILImage.open(path) as image:
        rgb = image.convert("RGB")
        background = PILImage.new("RGB", rgb.size, "white")
        diff = PILImage.new("RGB", rgb.size, "black")
        pixels = []
        for current, white in zip(rgb.getdata(), background.getdata()):
            pixels.append(tuple(abs(a - b) for a, b in zip(current, white)))
        diff.putdata(pixels)
        bbox = diff.getbbox()
        if not bbox:
            return
        pad = 36
        left = max(0, bbox[0] - pad)
        top = max(0, bbox[1] - pad)
        right = min(rgb.width, bbox[2] + pad)
        bottom = min(rgb.height, bbox[3] + pad)
        cropped = rgb.crop((left, top, right, bottom))
        if bottom_padding > pad:
            expanded = PILImage.new("RGB", (cropped.width, cropped.height + bottom_padding - pad), "white")
            expanded.paste(cropped, (0, 0))
            cropped = expanded
        cropped.save(path)


def base_canvas(width=1500, height=720):
    image = PILImage.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    return image, draw


def draw_box(draw, rect, label, fill="#F7F9FC", outline="#273452"):
    x1, y1, x2, y2 = rect
    draw.rounded_rectangle(rect, radius=16, fill=fill, outline=outline, width=3)
    font = load_font(24, bold=True)
    lines = wrap_text(draw, label, font, max(80, x2 - x1 - 28))
    line_height = 30
    total_height = len(lines) * line_height
    y = y1 + ((y2 - y1) - total_height) / 2
    for line in lines:
        w, _ = text_size(draw, line, font)
        draw.text((x1 + (x2 - x1 - w) / 2, y), line, font=font, fill="#111827")
        y += line_height


def draw_arrow(draw, start, end, color="#475569"):
    draw.line([start, end], fill=color, width=4)
    sx, sy = start
    ex, ey = end
    angle = 0 if ex >= sx else 3.14159
    if abs(ex - sx) < abs(ey - sy):
        angle = 1.5708 if ey >= sy else -1.5708
    size = 13
    import math
    points = [
        (ex, ey),
        (ex - size * math.cos(angle - 0.45), ey - size * math.sin(angle - 0.45)),
        (ex - size * math.cos(angle + 0.45), ey - size * math.sin(angle + 0.45)),
    ]
    draw.polygon(points, fill=color)


def parse_edges(code: list[str]) -> tuple[str, dict[str, str], list[tuple[str, str, str]]]:
    header = code[0].strip()
    direction = "LR" if " LR" in header else "TB"
    labels: dict[str, str] = {}
    edges: list[tuple[str, str, str]] = []
    for raw in code[1:]:
        line = raw.strip()
        if not line or line.startswith("%%"):
            continue
        line = re.sub(r"\|([^|]+)\|", r" ", line)
        if "-->" not in line:
            continue
        left, right = line.split("-->", 1)
        source_id, source_label = extract_mermaid_label(left)
        target_id, target_label = extract_mermaid_label(right)
        if source_id not in labels or source_label != source_id:
            labels[source_id] = source_label
        if target_id not in labels or target_label != target_id:
            labels[target_id] = target_label
        edges.append((source_id, target_id, ""))
    return direction, labels, edges


def render_flowchart(code: list[str], path: Path) -> None:
    direction, labels, edges = parse_edges(code)
    image, draw = base_canvas()
    if not labels:
        image.save(path)
        return
    ids = list(labels)
    if direction == "LR" and len(ids) <= 5:
        y = 300
        gap = max(230, min(300, 1180 // max(1, len(ids) - 1)))
        x0 = 80
        positions = {node_id: (x0 + index * gap, y) for index, node_id in enumerate(ids)}
        box_w, box_h = 230, 92
    elif direction == "LR":
        cols = 4
        positions = {}
        for index, node_id in enumerate(ids):
            row = index // cols
            col = index % cols
            positions[node_id] = (80 + col * 350, 120 + row * 180)
        box_w, box_h = 275, 96
    else:
        cols = 3
        positions = {}
        for index, node_id in enumerate(ids):
            row = index // cols
            col = index % cols
            positions[node_id] = (110 + col * 450, 95 + row * 145)
        box_w, box_h = 330, 82
    for source, target, _ in edges:
        if source not in positions or target not in positions:
            continue
        sx, sy = positions[source]
        tx, ty = positions[target]
        draw_arrow(draw, (sx + box_w, sy + box_h / 2), (tx, ty + box_h / 2))
    for node_id, (x, y) in positions.items():
        draw_box(draw, (x, y, x + box_w, y + box_h), labels[node_id])
    image.save(path)


def render_state(code: list[str], path: Path) -> None:
    image, draw = base_canvas()
    rows = []
    for raw in code[1:]:
        line = raw.strip()
        if "-->" in line:
            left, right = line.split("-->", 1)
            rows.append((left.strip(), right.split(":", 1)[0].strip(), right.split(":", 1)[1].strip() if ":" in right else ""))
    nodes = []
    for source, target, _ in rows:
        for node in (source, target):
            if node not in nodes:
                nodes.append(node)
    labels = {node: ("Старт/конец" if node == "[*]" else node) for node in nodes}
    positions = {node: (110 + (i % 4) * 340, 110 + (i // 4) * 160) for i, node in enumerate(nodes)}
    for source, target, label in rows:
        if source in positions and target in positions:
            sx, sy = positions[source]
            tx, ty = positions[target]
            draw_arrow(draw, (sx + 250, sy + 40), (tx, ty + 40))
            if label:
                font = load_font(18)
                draw.text(((sx + tx) / 2 + 20, (sy + ty) / 2 + 16), label, font=font, fill="#475569")
    for node, (x, y) in positions.items():
        draw_box(draw, (x, y, x + 250, y + 80), labels[node], fill="#EEF6FF")
    image.save(path)


def render_sequence(code: list[str], path: Path) -> None:
    participants: list[tuple[str, str]] = []
    messages: list[tuple[str, str, str, bool]] = []
    for raw in code[1:]:
        line = raw.strip()
        if line.startswith("participant "):
            match = re.match(r"participant\s+(\w+)\s+as\s+(.+)", line)
            if match:
                participants.append((match.group(1), match.group(2)))
        elif "->>" in line:
            match = re.match(r"(.+?)(--|-)>>(.+?):(.+)", line)
            if match:
                messages.append((match.group(1).strip(), match.group(3).strip(), match.group(4).strip(), match.group(2) == "--"))
    if not participants:
        ids = []
        for source, target, _, _ in messages:
            for item in (source, target):
                if item not in ids:
                    ids.append(item)
        participants = [(item, item) for item in ids]

    width = max(1500, 360 + max(0, len(participants) - 1) * 520)
    top = 80
    actor_h = 120
    first_message_y = top + actor_h + 110
    message_gap = 95
    last_message_y = first_message_y + max(0, len(messages) - 1) * message_gap
    lifeline_bottom = last_message_y + 340
    height = lifeline_bottom + 260
    image, draw = base_canvas(width, height)
    x_positions = {
        pid: 180 + i * ((width - 360) // max(1, len(participants) - 1 or 1))
        for i, (pid, _) in enumerate(participants)
    }
    actor_font = load_font(30, bold=True)
    message_font = load_font(24)

    for pid, label in participants:
        x = x_positions[pid]
        box_w = 300
        draw.rounded_rectangle((x - box_w / 2, top, x + box_w / 2, top + actor_h), radius=10, fill="white", outline="black", width=3)
        label_lines = wrap_text(draw, label, actor_font, box_w - 30)
        label_y = top + (actor_h - len(label_lines) * 34) / 2
        for line in label_lines:
            line_w, _ = text_size(draw, line, actor_font)
            draw.text((x - line_w / 2, label_y), line, font=actor_font, fill="black")
            label_y += 34
        draw_dashed_vertical(draw, x, top + actor_h, lifeline_bottom)

    for i, (source, target, message, dashed) in enumerate(messages):
        y = first_message_y + i * message_gap
        sx, tx = x_positions[source], x_positions[target]
        draw_sequence_arrow(draw, sx, tx, y, dashed=dashed)
        label = message[:90]
        w, h = text_size(draw, label, message_font)
        label_x = min(sx, tx) + abs(tx - sx) / 2 - w / 2
        draw.rectangle((label_x - 10, y - 42, label_x + w + 10, y - 8), fill="white")
        draw.text((label_x, y - 42), label, font=message_font, fill="black")
    image.save(path)


def draw_dashed_vertical(draw, x: int, y1: int, y2: int) -> None:
    dash = 18
    gap = 12
    y = y1
    while y < y2:
        next_y = min(y + dash, y2)
        draw.line([(x, y), (x, next_y)], fill="black", width=3)
        y = next_y + gap
    radius = 4
    draw.ellipse((x - radius, y2 - radius, x + radius, y2 + radius), fill="black")


def draw_sequence_arrow(draw, sx: int, tx: int, y: int, dashed: bool = False) -> None:
    import math

    direction = 1 if tx >= sx else -1
    start = (sx, y)
    end = (tx - direction * 14, y)
    if dashed:
        dash = 18
        gap = 12
        x = start[0]
        while (direction > 0 and x < end[0]) or (direction < 0 and x > end[0]):
            next_x = x + direction * dash
            if direction > 0:
                next_x = min(next_x, end[0])
            else:
                next_x = max(next_x, end[0])
            draw.line([(x, y), (next_x, y)], fill="black", width=3)
            x = next_x + direction * gap
    else:
        draw.line([start, end], fill="black", width=3)

    angle = 0 if direction > 0 else math.pi
    size = 18
    ex, ey = tx, y
    points = [
        (ex, ey),
        (ex - direction * size, ey - 10),
        (ex - direction * size, ey + 10),
    ]
    draw.polygon(points, fill="black")


def render_xychart(code: list[str], path: Path) -> None:
    image, draw = base_canvas(1500, 720)
    title = "Диаграмма"
    labels: list[str] = []
    values: list[float] = []
    for raw in code:
        line = raw.strip()
        if line.startswith("title "):
            title = line[6:].strip().strip('"')
        elif line.startswith("x-axis "):
            labels = re.findall(r'"([^"]+)"', line)
        elif line.startswith("bar "):
            values = [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", line)]
    title_font = load_font(26, bold=True)
    title_width, _ = text_size(draw, title, title_font)
    draw.text(((1500 - title_width) / 2, 36), title, font=title_font, fill="black")
    chart = (170, 120, 1430, 610)
    draw.line([(chart[0], chart[3]), (chart[2], chart[3])], fill="black", width=2)
    draw.line([(chart[0], chart[1]), (chart[0], chart[3])], fill="black", width=2)
    if not values:
        image.save(path)
        return
    min_value = min(0, min(values))
    max_value = max(0, max(values))
    span = max(1, max_value - min_value)
    zero_y = chart[3] - ((0 - min_value) / span) * (chart[3] - chart[1])
    draw.line([(chart[0], zero_y), (chart[2], zero_y)], fill="black", width=1)
    font = load_font(18)
    tick_count = 5
    for tick_index in range(tick_count + 1):
        value = min_value + span * tick_index / tick_count
        y = chart[3] - ((value - min_value) / span) * (chart[3] - chart[1])
        draw.line([(chart[0] - 9, y), (chart[0], y)], fill="black", width=2)
        if tick_index not in (0, tick_count):
            draw.line([(chart[0], y), (chart[2], y)], fill="#dddddd", width=1)
        label = str(round(value, 1)).rstrip("0").rstrip(".")
        label_width, label_height = text_size(draw, label, font)
        draw.text((chart[0] - 18 - label_width, y - label_height / 2), label, font=font, fill="black")
    bar_gap = 28
    bar_width = (chart[2] - chart[0] - bar_gap * (len(values) + 1)) / len(values)
    for i, value in enumerate(values):
        x1 = chart[0] + bar_gap + i * (bar_width + bar_gap)
        x2 = x1 + bar_width
        y = chart[3] - ((value - min_value) / span) * (chart[3] - chart[1])
        y1, y2 = sorted([zero_y, y])
        draw.rectangle((x1, y1, x2, y2), fill="#eeeeee", outline="black", width=1)
        label = labels[i] if i < len(labels) else str(i + 1)
        for j, part in enumerate(wrap_text(draw, label, font, int(bar_width) + 18)):
            w, _ = text_size(draw, part, font)
            draw.text((x1 + (bar_width - w) / 2, chart[3] + 16 + j * 22), part, font=font, fill="black")
        value_label = str(value).rstrip("0").rstrip(".")
        value_width, _ = text_size(draw, value_label, font)
        draw.text((x1 + (bar_width - value_width) / 2, y1 - 30), value_label, font=font, fill="black")
    image.save(path)


def build_pdf(input_path: Path, output_path: Path) -> None:
    regular, bold = register_fonts()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    page_width, page_height = A4
    left_margin = 30 * mm
    right_margin = 10 * mm
    top_margin = 20 * mm
    bottom_margin = 20 * mm
    available_width = page_width - left_margin - right_margin

    base = getSampleStyleSheet()
    styles = {
        "font": regular,
        "title": ParagraphStyle(
            "TitleRu",
            parent=base["Title"],
            fontName=bold,
            fontSize=16,
            leading=21,
            textColor=colors.HexColor("#111827"),
            alignment=TA_CENTER,
            spaceAfter=8 * mm,
        ),
        "h1": ParagraphStyle("H1Ru", parent=base["Heading1"], fontName=bold, fontSize=14, leading=21, leftIndent=PARAGRAPH_INDENT, firstLineIndent=0, spaceBefore=6 * mm, spaceAfter=2.5 * mm, textColor=colors.black, borderColor=colors.HexColor("#CBD5E1"), borderWidth=0, borderPadding=0, keepWithNext=True),
        "h2": ParagraphStyle("H2Ru", parent=base["Heading2"], fontName=bold, fontSize=14, leading=21, leftIndent=PARAGRAPH_INDENT, firstLineIndent=0, spaceBefore=4 * mm, spaceAfter=2 * mm, textColor=colors.black, keepWithNext=True),
        "h3": ParagraphStyle("H3Ru", parent=base["Heading3"], fontName=bold, fontSize=14, leading=21, leftIndent=PARAGRAPH_INDENT, firstLineIndent=0, spaceBefore=3 * mm, spaceAfter=1.5 * mm, textColor=colors.black, keepWithNext=True),
        "body": ParagraphStyle("BodyRu", parent=base["BodyText"], fontName=regular, fontSize=14, leading=21, alignment=TA_JUSTIFY, firstLineIndent=PARAGRAPH_INDENT, spaceAfter=0),
        "list_body": ParagraphStyle("ListBodyRu", parent=base["BodyText"], fontName=regular, fontSize=14, leading=21, alignment=TA_JUSTIFY, leftIndent=PARAGRAPH_INDENT, firstLineIndent=0, spaceAfter=0),
        "table_header": ParagraphStyle("TableHeaderRu", parent=base["BodyText"], fontName=bold, fontSize=11, leading=13.2, textColor=colors.black),
        "table_cell": ParagraphStyle("TableCellRu", parent=base["BodyText"], fontName=regular, fontSize=11, leading=13.2, textColor=colors.black),
        "code": ParagraphStyle("CodeRu", parent=base["Code"], fontName=regular, fontSize=11, leading=14, leftIndent=0, rightIndent=0, firstLineIndent=0, textColor=colors.black, backColor=colors.white),
    }

    story: list = []
    paragraph: list[str] = []
    bullets: list[str] = []
    code: list[str] = []
    table: list[list[str]] = []
    in_code = False
    code_lang = ""
    first_heading = True

    for raw_line in input_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()

        if line.startswith("```"):
            if in_code:
                flush_code(story, code, styles, code_lang, available_width)
                in_code = False
                code_lang = ""
            else:
                flush_paragraph(story, paragraph, styles["body"])
                flush_bullets(story, bullets, styles, available_width)
                if table:
                    add_table(story, table, styles, available_width)
                    table.clear()
                in_code = True
                code_lang = line.strip("`").strip()
            continue

        if in_code:
            code.append(line)
            continue

        if not line.strip():
            flush_paragraph(story, paragraph, styles["body"])
            flush_bullets(story, bullets, styles, available_width)
            if table:
                add_table(story, table, styles, available_width)
                table.clear()
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph(story, paragraph, styles["body"])
            flush_bullets(story, bullets, styles, available_width)
            if table:
                add_table(story, table, styles, available_width)
                table.clear()
            level = len(heading.group(1))
            text = clean_heading(heading.group(2))
            if level == 1 and first_heading:
                story.append(Paragraph(text, styles["title"]))
                first_heading = False
            elif level == 1:
                story.append(PageBreak())
                story.append(Paragraph(text, styles["h1"]))
            elif level == 2:
                story.append(Paragraph(text, styles["h2"]))
            else:
                story.append(Paragraph(text, styles["h3"]))
            continue

        if line.lstrip().startswith("- "):
            flush_paragraph(story, paragraph, styles["body"])
            if table:
                add_table(story, table, styles, available_width)
                table.clear()
            bullets.append(line.lstrip()[2:])
            continue

        if line.strip().startswith("|") and "|" in line.strip()[1:]:
            flush_paragraph(story, paragraph, styles["body"])
            flush_bullets(story, bullets, styles, available_width)
            if is_table_divider(line):
                continue
            table.append(split_table_row(line))
            continue

        if table:
            add_table(story, table, styles, available_width)
            table.clear()
        flush_bullets(story, bullets, styles, available_width)
        paragraph.append(line)

    flush_paragraph(story, paragraph, styles["body"])
    flush_bullets(story, bullets, styles, available_width)
    if table:
        add_table(story, table, styles, available_width)
    if code:
        flush_code(story, code, styles, code_lang, available_width)

    def draw_footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.white)
        canvas.rect(0, 0, page_width, page_height, stroke=0, fill=1)
        canvas.setFont(regular, 12)
        canvas.setFillColor(colors.black)
        canvas.drawCentredString(page_width / 2, 10 * mm, str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=right_margin,
        leftMargin=left_margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
        title=input_path.stem,
        author="",
    )
    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Конвертирует Markdown в PDF A4 portrait с Mermaid и базовыми правилами оформления по ГОСТ Р 7.32."
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT, help="Входной Markdown-файл.")
    parser.add_argument("output", nargs="?", type=Path, default=DEFAULT_OUTPUT, help="Выходной PDF-файл.")
    args = parser.parse_args()
    build_pdf(args.input.resolve(), args.output.resolve())
