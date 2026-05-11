from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path

import pytest
from PIL import ImageFont
from pypdf import PdfReader

import md2pdf as package
import md2pdf.cli as cli
from md2pdf import config, markdown, mermaid, pdf
from md2pdf.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_versions_are_in_sync() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == config.VERSION == "1.0.0"
    assert package["version"] == config.VERSION
    assert lock["version"] == config.VERSION
    assert lock["packages"][""]["version"] == config.VERSION


def test_public_package_facade_exports_core_helpers() -> None:
    assert package.clean_inline("**ok**") == "<b>ok</b>"
    assert package.main is main


def test_cli_main_builds_pdf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "cli.md"
    target = tmp_path / "cli.pdf"
    source.write_text("# CLI\n\nBody text.\n", encoding="utf-8")

    assert main([str(source), str(target)]) == 0
    assert target.exists()


def test_cli_reports_missing_input(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    target = tmp_path / "missing.pdf"

    with pytest.raises(SystemExit) as error:
        main([str(tmp_path / "missing.md"), str(target)])

    assert error.value.code == 1
    assert "входной файл не найден" in capsys.readouterr().err
    assert not target.exists()


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--version"])

    assert error.value.code == 0
    assert config.VERSION in capsys.readouterr().out


def test_parse_margins() -> None:
    assert cli.parse_margins("30,10,20,20") == (30, 10, 20, 20)
    with pytest.raises(Exception, match="формат полей"):
        cli.parse_margins("30,10,20")
    with pytest.raises(Exception, match="больше нуля"):
        cli.parse_margins("30,0,20,20")


def test_cli_passes_layout_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "layout.md"
    target = tmp_path / "layout.pdf"
    source.write_text("# Layout\n\nText.\n", encoding="utf-8")
    calls = []

    def fake_build_pdf(input_path: Path, output_path: Path, options: pdf.PdfOptions) -> None:
        calls.append((input_path, output_path, options))
        output_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(cli, "build_pdf", fake_build_pdf)

    assert (
        main(
            [
                str(source),
                str(target),
                "--font-size",
                "16",
                "--line-height",
                "1.4",
                "--diagram-max-height",
                "90",
                "--margins",
                "25,12,18,22",
            ]
        )
        == 0
    )
    assert calls[0][2] == pdf.PdfOptions(
        font_size=16,
        line_height=1.4,
        diagram_max_height_mm=90,
        margins_mm=(25, 12, 18, 22),
    )


def test_cli_check_deps(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--check-deps"]) == 0
    output = capsys.readouterr().out
    assert "fonts:" in output
    assert "node:" in output
    assert "mermaid-cli:" in output


def test_clean_inline_escapes_html_and_keeps_bold() -> None:
    assert markdown.clean_inline("**A < B** and `code`") == "<b>A &lt; B</b> and code"


def test_clean_inline_removes_link_target() -> None:
    assert markdown.clean_inline("Read [docs](docs/usage.md)") == "Read docs"


def test_table_helpers() -> None:
    assert markdown.split_table_row("| A | B |") == ["A", "B"]
    assert markdown.is_table_divider("| --- | :---: | ---: |")
    assert not markdown.is_table_divider("| A | B |")


def test_extract_mermaid_labels() -> None:
    assert mermaid.extract_mermaid_label('A["Начало"]') == ("A", "Начало")
    assert mermaid.extract_mermaid_label("Finish") == ("Finish", "Finish")


def test_parse_edges_flowchart() -> None:
    direction, labels, edges = mermaid.parse_edges(
        [
            "flowchart LR",
            '  A["Markdown"] --> B["PDF"]',
            "  B --> C",
        ]
    )
    assert direction == "LR"
    assert labels == {"A": "Markdown", "B": "PDF", "C": "C"}
    assert edges == [("A", "B", ""), ("B", "C", "")]


def test_mermaid_cli_failure_uses_builtin_renderer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "MERMAID_DIR", tmp_path / ".md2pdf" / "mermaid")
    monkeypatch.setattr(config, "MERMAID_COUNTER", 0)
    monkeypatch.setattr(config, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(config, "FONT_BOLD", "Helvetica-Bold")
    monkeypatch.setattr(mermaid, "load_font", lambda size, bold=False: ImageFont.load_default())

    local_mmdc = tmp_path / "node_modules" / ".bin" / "mmdc"
    local_mmdc.parent.mkdir(parents=True)
    local_mmdc.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")

    def fail_run(*args, **kwargs):  # noqa: ANN002, ANN003
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout="", stderr="browser failed")

    monkeypatch.setattr(subprocess, "run", fail_run)

    path = mermaid.render_mermaid_image(["flowchart LR", '  A["Markdown"] --> B["PDF"]'])

    assert path is not None
    assert path.exists()


def test_cli_quiet_suppresses_mermaid_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(config, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(config, "FONT_BOLD", "Helvetica-Bold")
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))
    monkeypatch.setattr(mermaid, "load_font", lambda size, bold=False: ImageFont.load_default())

    source = tmp_path / "quiet.md"
    target = tmp_path / "quiet.pdf"
    temp_dir = tmp_path / "tmp"
    source.write_text("# Quiet\n\n```mermaid\nflowchart LR\n  A --> B\n```\n", encoding="utf-8")

    def fail_run(*args, **kwargs):  # noqa: ANN002, ANN003
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout="", stderr="browser failed")

    monkeypatch.setattr(subprocess, "run", fail_run)
    local_mmdc = tmp_path / "node_modules" / ".bin" / "mmdc"
    local_mmdc.parent.mkdir(parents=True)
    local_mmdc.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    monkeypatch.setattr(config, "ROOT", tmp_path)

    assert main([str(source), str(target), "--temp-dir", str(temp_dir), "--quiet"]) == 0
    assert target.exists()
    assert temp_dir.exists()
    assert not list(temp_dir.iterdir())
    assert "Mermaid CLI" not in capsys.readouterr().err


def test_cli_strict_mermaid_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(config, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(config, "FONT_BOLD", "Helvetica-Bold")
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "strict.md"
    target = tmp_path / "strict.pdf"
    source.write_text("# Strict\n\n```mermaid\nflowchart LR\n  A --> B\n```\n", encoding="utf-8")

    local_mmdc = tmp_path / "node_modules" / ".bin" / "mmdc"
    local_mmdc.parent.mkdir(parents=True)
    local_mmdc.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    monkeypatch.setattr(config, "ROOT", tmp_path)

    def fail_run(*args, **kwargs):  # noqa: ANN002, ANN003
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout="", stderr="browser failed")

    monkeypatch.setattr(subprocess, "run", fail_run)

    with pytest.raises(SystemExit) as error:
        main([str(source), str(target), "--strict-mermaid"])

    assert error.value.code == 1
    assert "Mermaid render failed" in capsys.readouterr().err


def test_build_pdf_without_mermaid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "input.md"
    target = tmp_path / "output.pdf"
    source.write_text("# Title\n\nBody text.\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n", encoding="utf-8")

    pdf.build_pdf(source, target)

    assert target.exists()
    assert target.stat().st_size > 0


def test_unknown_mermaid_block_renders_as_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "unknown.md"
    target = tmp_path / "unknown.pdf"
    source.write_text("# Unknown\n\n```mermaid\nunknownDiagram\n  A -> B\n```\n", encoding="utf-8")

    pdf.build_pdf(source, target)

    reader = PdfReader(target)
    assert "unknownDiagram" in (reader.pages[0].extract_text() or "")


def test_empty_document_builds_pdf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "empty.md"
    target = tmp_path / "empty.pdf"
    source.write_text("", encoding="utf-8")

    pdf.build_pdf(source, target)

    assert len(PdfReader(target).pages) >= 1


def test_generated_pdf_is_readable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "readable.md"
    target = tmp_path / "readable.pdf"
    source.write_text("# Readable\n\nExpected text.\n", encoding="utf-8")

    pdf.build_pdf(source, target)

    reader = PdfReader(target)
    assert len(reader.pages) >= 1
    assert reader.metadata.title == "readable"
    assert "Expected text" in (reader.pages[0].extract_text() or "")
