from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

from . import config


def load_font(size: int, bold: bool = False):
    return ImageFont.truetype(config.FONT_BOLD if bold else config.FONT_REGULAR, size=size)


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
    config.MERMAID_COUNTER += 1
    config.MERMAID_DIR.mkdir(parents=True, exist_ok=True)
    kind = next((line.strip() for line in code if line.strip()), "")
    real_rendered = try_render_mermaid_with_cli(code, config.MERMAID_COUNTER)
    if real_rendered:
        return real_rendered
    path = config.MERMAID_DIR / f"diagram_{config.MERMAID_COUNTER:02d}.png"
    if kind.startswith("xychart"):
        render_xychart(code, path)
        crop_mermaid_png(path)
        return path
    if kind.startswith("sequenceDiagram"):
        render_sequence(code, path)
        crop_mermaid_png(path, bottom_padding=260)
        return path
    if kind.startswith("stateDiagram"):
        render_state(code, path)
    elif kind.startswith("flowchart"):
        render_flowchart(code, path)
    else:
        return None
    return path


def try_render_mermaid_with_cli(code: list[str], index: int) -> Path | None:
    try:
        return render_mermaid_with_cli(code, index)
    except RuntimeError as error:
        if os.environ.get("MD2PDF_STRICT_MERMAID"):
            raise
        if not config.QUIET:
            message = str(error).splitlines()[0]
            print(f"md2pdf: Mermaid CLI не сработал, используется встроенный рендерер: {message}", file=sys.stderr)
        return None


def render_mermaid_with_cli(code: list[str], index: int) -> Path | None:
    local_mmdc = config.ROOT / "node_modules" / ".bin" / "mmdc"
    mmdc = str(local_mmdc) if local_mmdc.exists() else shutil.which("mmdc")
    if not mmdc:
        return None
    first = next((line.strip() for line in code if line.strip()), "")

    source = config.MERMAID_DIR / f"diagram_{index:02d}.mmd"
    target = config.MERMAID_DIR / f"diagram_{index:02d}.png"
    puppeteer_config = config.MERMAID_DIR / "puppeteer-config.json"
    mermaid_config = config.MERMAID_DIR / "mermaid-config.json"
    source.write_text("\n".join(prepare_mermaid_for_pdf(code)) + "\n", encoding="utf-8")
    puppeteer_config.write_text(
        json.dumps({"args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]}),
        encoding="utf-8",
    )
    mermaid_config.write_text(
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
                "flowchart": {"htmlLabels": True, "nodeSpacing": 35, "rankSpacing": 45},
                "sequence": {"mirrorActors": False, "messageFontSize": 12, "actorFontSize": 12, "noteFontSize": 12},
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
        str(mermaid_config),
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
    result = subprocess.run(command, cwd=config.ROOT, text=True, capture_output=True, timeout=60)
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


def crop_mermaid_png(path: Path, bottom_padding: int = 36) -> None:
    with PILImage.open(path) as image:
        rgb = image.convert("RGB")
        background = PILImage.new("RGB", rgb.size, "white")
        diff = PILImage.new("RGB", rgb.size, "black")
        pixels = []
        for current, white in zip(rgb.getdata(), background.getdata(), strict=True):
            pixels.append(tuple(abs(a - b) for a, b in zip(current, white, strict=True)))
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
    import math

    draw.line([start, end], fill=color, width=4)
    sx, sy = start
    ex, ey = end
    angle = 0 if ex >= sx else 3.14159
    if abs(ex - sx) < abs(ey - sy):
        angle = 1.5708 if ey >= sy else -1.5708
    size = 13
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
            target, label = right.split(":", 1) if ":" in right else (right, "")
            rows.append((left.strip(), target.strip(), label.strip()))
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
                messages.append(
                    (
                        match.group(1).strip(),
                        match.group(3).strip(),
                        match.group(4).strip(),
                        match.group(2) == "--",
                    )
                )
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
        draw.rounded_rectangle(
            (x - box_w / 2, top, x + box_w / 2, top + actor_h),
            radius=10,
            fill="white",
            outline="black",
            width=3,
        )
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
        w, _ = text_size(draw, label, message_font)
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
    direction = 1 if tx >= sx else -1
    start = (sx, y)
    end = (tx - direction * 14, y)
    if dashed:
        dash = 18
        gap = 12
        x = start[0]
        while (direction > 0 and x < end[0]) or (direction < 0 and x > end[0]):
            next_x = x + direction * dash
            next_x = min(next_x, end[0]) if direction > 0 else max(next_x, end[0])
            draw.line([(x, y), (next_x, y)], fill="black", width=3)
            x = next_x + direction * gap
    else:
        draw.line([start, end], fill="black", width=3)

    size = 18
    ex, ey = tx, y
    points = [(ex, ey), (ex - direction * size, ey - 10), (ex - direction * size, ey + 10)]
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


def cleanup_mermaid_dir() -> None:
    if not config.MERMAID_DIR.exists():
        return
    names = {"puppeteer-config.json", "mermaid-config.json"}
    for path in config.MERMAID_DIR.iterdir():
        if path.name in names or path.name.startswith("diagram_"):
            if path.is_file():
                path.unlink()
