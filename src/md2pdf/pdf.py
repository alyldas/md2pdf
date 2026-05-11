from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image as PILImage
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
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

from .config import PARAGRAPH_INDENT, register_fonts
from .markdown import (
    add_table,
    clean_heading,
    flush_bullets,
    flush_paragraph,
    is_table_divider,
    split_table_row,
)
from .mermaid import render_mermaid_image


@dataclass(frozen=True)
class PdfOptions:
    font_size: float = 14
    line_height: float = 1.5
    diagram_max_height_mm: float = 135
    margins_mm: tuple[float, float, float, float] = (30, 10, 20, 20)

    @property
    def leading(self) -> float:
        return self.font_size * self.line_height


def flush_code(
    story: list,
    code: list[str],
    styles: dict,
    language: str,
    available_width: float,
    options: PdfOptions | None = None,
) -> None:
    if not code:
        return
    options = options or PdfOptions()
    if language == "mermaid":
        image_path = render_mermaid_image(code)
        if image_path:
            with PILImage.open(image_path) as rendered:
                ratio = rendered.height / rendered.width
            max_height = options.diagram_max_height_mm * mm
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


def build_pdf(input_path: Path, output_path: Path, options: PdfOptions | None = None) -> None:
    rl_config.invariant = 1
    options = options or PdfOptions()
    regular, bold = register_fonts()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    page_width, page_height = A4
    left_margin, right_margin, top_margin, bottom_margin = [value * mm for value in options.margins_mm]
    available_width = page_width - left_margin - right_margin
    leading = options.leading
    heading_leading = max(leading, options.font_size * 1.5)
    code_size = max(8, options.font_size - 3)
    table_size = max(8, options.font_size - 3)

    base = getSampleStyleSheet()
    styles = {
        "font": regular,
        "title": ParagraphStyle(
            "TitleRu",
            parent=base["Title"],
            fontName=bold,
            fontSize=options.font_size + 2,
            leading=heading_leading + 2,
            textColor=colors.HexColor("#111827"),
            alignment=TA_CENTER,
            spaceAfter=8 * mm,
        ),
        "h1": ParagraphStyle(
            "H1Ru",
            parent=base["Heading1"],
            fontName=bold,
            fontSize=options.font_size,
            leading=heading_leading,
            leftIndent=PARAGRAPH_INDENT,
            firstLineIndent=0,
            spaceBefore=6 * mm,
            spaceAfter=2.5 * mm,
            textColor=colors.black,
            borderColor=colors.HexColor("#CBD5E1"),
            borderWidth=0,
            borderPadding=0,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "H2Ru",
            parent=base["Heading2"],
            fontName=bold,
            fontSize=options.font_size,
            leading=heading_leading,
            leftIndent=PARAGRAPH_INDENT,
            firstLineIndent=0,
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
            textColor=colors.black,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "H3Ru",
            parent=base["Heading3"],
            fontName=bold,
            fontSize=options.font_size,
            leading=heading_leading,
            leftIndent=PARAGRAPH_INDENT,
            firstLineIndent=0,
            spaceBefore=3 * mm,
            spaceAfter=1.5 * mm,
            textColor=colors.black,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "BodyRu",
            parent=base["BodyText"],
            fontName=regular,
            fontSize=options.font_size,
            leading=leading,
            alignment=TA_LEFT,
            firstLineIndent=PARAGRAPH_INDENT,
            spaceAfter=0,
        ),
        "list_body": ParagraphStyle(
            "ListBodyRu",
            parent=base["BodyText"],
            fontName=regular,
            fontSize=options.font_size,
            leading=leading,
            alignment=TA_LEFT,
            leftIndent=PARAGRAPH_INDENT,
            firstLineIndent=0,
            spaceAfter=0,
        ),
        "table_header": ParagraphStyle(
            "TableHeaderRu",
            parent=base["BodyText"],
            fontName=bold,
            fontSize=table_size,
            leading=table_size * 1.2,
            textColor=colors.black,
        ),
        "table_cell": ParagraphStyle(
            "TableCellRu",
            parent=base["BodyText"],
            fontName=regular,
            fontSize=table_size,
            leading=table_size * 1.2,
            textColor=colors.black,
        ),
        "code": ParagraphStyle(
            "CodeRu",
            parent=base["Code"],
            fontName=regular,
            fontSize=code_size,
            leading=code_size * 1.27,
            leftIndent=0,
            rightIndent=0,
            firstLineIndent=0,
            textColor=colors.black,
            backColor=colors.white,
        ),
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
                flush_code(story, code, styles, code_lang, available_width, options)
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
        flush_code(story, code, styles, code_lang, available_width, options)
    if not story:
        story.append(Spacer(1, 1))

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
