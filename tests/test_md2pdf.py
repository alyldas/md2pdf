from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path

import pytest
from PIL import ImageFont
from pypdf import PdfReader
from reportlab.lib.enums import TA_LEFT

import md2pdf as package
import md2pdf.cli as cli
from md2pdf import config, markdown, mermaid, pdf
from md2pdf.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_versions_are_in_sync() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == config.VERSION == "1.0.6"
    assert package["version"] == config.VERSION
    assert lock["version"] == config.VERSION
    assert lock["packages"][""]["version"] == config.VERSION


def test_linux_liberation_serif_is_preferred_before_dejavu() -> None:
    regular = config.FONT_CANDIDATES["regular"]
    bold = config.FONT_CANDIDATES["bold"]

    assert "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf" in regular
    assert "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf" in regular
    assert regular.index("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf") < regular.index(
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    )
    assert bold.index("/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf") < bold.index(
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
    )


def test_pick_font_uses_first_existing_candidate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    first = tmp_path / "LiberationSerif-Regular.ttf"
    second = tmp_path / "DejaVuSerif.ttf"
    first.touch()
    second.touch()
    monkeypatch.setitem(config.FONT_CANDIDATES, "regular", [str(first), str(second)])

    assert config.pick_font("regular") == str(first)


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


def test_cli_uses_unique_default_mermaid_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "cli.md"
    source.write_text("# CLI\n\nBody text.\n", encoding="utf-8")
    first_target = tmp_path / "first.pdf"
    second_target = tmp_path / "second.pdf"
    base_mermaid_dir = tmp_path / ".md2pdf" / "mermaid"
    seen: list[Path] = []

    monkeypatch.setattr(config, "MERMAID_DIR", base_mermaid_dir)

    def fake_build_pdf(input_path: Path, output_path: Path, options: pdf.PdfOptions) -> None:
        seen.append(config.MERMAID_DIR)
        config.MERMAID_DIR.mkdir(parents=True)
        output_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(cli, "build_pdf", fake_build_pdf)

    assert main([str(source), str(first_target)]) == 0
    assert main([str(source), str(second_target)]) == 0
    assert len(seen) == 2
    assert seen[0] != seen[1]
    assert seen[0].parent == base_mermaid_dir
    assert seen[1].parent == base_mermaid_dir
    assert not seen[0].exists()
    assert not seen[1].exists()
    assert config.MERMAID_DIR == base_mermaid_dir


def test_cli_ignores_nonempty_default_temp_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "cli.md"
    target = tmp_path / "cli.pdf"
    source.write_text("# CLI\n\nBody text.\n", encoding="utf-8")
    base_mermaid_dir = tmp_path / ".md2pdf" / "mermaid"
    seen: list[Path] = []

    monkeypatch.setattr(config, "MERMAID_DIR", base_mermaid_dir)

    def fake_build_pdf(input_path: Path, output_path: Path, options: pdf.PdfOptions) -> None:
        seen.append(config.MERMAID_DIR)
        config.MERMAID_DIR.mkdir(parents=True)
        (config.MERMAID_DIR / "extra.log").write_text("debug", encoding="utf-8")
        output_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(cli, "build_pdf", fake_build_pdf)

    assert main([str(source), str(target)]) == 0
    assert target.exists()
    assert seen[0].exists()
    assert config.MERMAID_DIR == base_mermaid_dir


def test_cli_reports_missing_input(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    target = tmp_path / "missing.pdf"

    with pytest.raises(SystemExit) as error:
        main([str(tmp_path / "missing.md"), str(target)])

    assert error.value.code == 1
    assert "входной файл не найден" in capsys.readouterr().err
    assert not target.exists()


def test_cli_rejects_same_input_and_output(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    source = tmp_path / "same.md"
    source.write_text("# Same\n\nText.\n", encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        main([str(source), str(source)])

    assert error.value.code == 1
    assert "должны быть разными" in capsys.readouterr().err
    assert source.read_text(encoding="utf-8").startswith("# Same")


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
    with pytest.raises(Exception, match="конечным числом"):
        cli.positive_float("nan")
    with pytest.raises(Exception, match="конечным числом"):
        cli.positive_float("inf")


def test_cli_rejects_page_margins_larger_than_a4(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    source = tmp_path / "wide.md"
    target = tmp_path / "wide.pdf"
    source.write_text("# Wide\n\nText.\n", encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        main([str(source), str(target), "--margins", "200,200,20,20"])

    assert error.value.code == 1
    assert "ширина области текста" in capsys.readouterr().err
    assert not target.exists()


def test_cli_rejects_too_large_layout_values(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    source = tmp_path / "large.md"
    target = tmp_path / "large.pdf"
    source.write_text("# Large\n\nText.\n", encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        main([str(source), str(target), "--font-size", "500"])

    assert error.value.code == 1
    assert "font-size" in capsys.readouterr().err


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


def test_body_text_is_not_force_justified(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))
    captured = {}

    class FakeDoc:
        page = 1

        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            pass

        def build(self, story, *args, **kwargs):  # noqa: ANN002, ANN003
            captured["story"] = story

    monkeypatch.setattr(pdf, "SimpleDocTemplate", FakeDoc)

    source = tmp_path / "text.md"
    target = tmp_path / "text.pdf"
    source.write_text("# Title\n\nOne two three four five six.\n\n- Item one.\n", encoding="utf-8")

    pdf.build_pdf(source, target)

    paragraphs = [item for item in captured["story"] if item.__class__.__name__ == "Paragraph"]
    body = next(item for item in paragraphs if "One two three" in item.getPlainText())
    bullet = next(item for item in paragraphs if "Item one" in item.getPlainText())
    assert body.style.alignment == TA_LEFT
    assert bullet.style.alignment == TA_LEFT


def test_cli_check_deps(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--check-deps"]) == 0
    output = capsys.readouterr().out
    assert "fonts:" in output
    assert "node:" in output
    assert "mermaid-cli:" in output


def test_cli_check_deps_rejects_positional_paths(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--check-deps", "input.md", "output.pdf"])

    assert error.value.code == 1
    assert "не принимает" in capsys.readouterr().err


def test_dependency_report_uses_project_root_for_local_mmdc(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    local_mmdc = tmp_path / "node_modules" / ".bin" / "mmdc"
    local_mmdc.parent.mkdir(parents=True)
    local_mmdc.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "pick_font", lambda kind: f"/fonts/{kind}.ttf")
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/bin/node" if name == "node" else None)

    assert f"mermaid-cli: ok ({local_mmdc})" in cli.dependency_report()


def test_clean_inline_escapes_html_and_keeps_bold() -> None:
    assert markdown.clean_inline("**A < B** and `code`") == "<b>A &lt; B</b> and code"


def test_clean_inline_escapes_raw_reportlab_markup() -> None:
    assert markdown.clean_inline("Raw <b>not markdown</b> and **markdown**") == (
        "Raw &lt;b&gt;not markdown&lt;/b&gt; and <b>markdown</b>"
    )


def test_clean_inline_removes_link_target() -> None:
    assert markdown.clean_inline("Read [docs](docs/usage.md)") == "Read docs"
    assert markdown.clean_inline("Read [docs](docs/foo(bar).md)") == "Read docs"
    assert markdown.clean_inline("Image ![Alt](img/foo(bar).png)") == "Image Alt"


def test_clean_inline_removes_link_target_with_escaped_label_bracket() -> None:
    assert markdown.clean_inline(r"Read [a\]b](docs/usage.md)") == "Read a]b"
    assert markdown.clean_inline(r"Image ![a\]b](img.png)") == "Image a]b"


def test_clean_inline_keeps_escaped_link_opener_as_text() -> None:
    assert markdown.clean_inline(r"\[not link](url)") == r"\[not link](url)"
    assert markdown.clean_inline(r"\![not image](img.png)") == r"\![not image](img.png)"


def test_table_helpers() -> None:
    assert markdown.split_table_row("| A | B |") == ["A", "B"]
    assert markdown.split_table_row("| A \\| B | C |") == ["A | B", "C"]
    assert markdown.split_table_row("| C:\\temp | ok |") == ["C:\\temp", "ok"]
    assert markdown.split_table_row("| a\\*b | ok |") == ["a\\*b", "ok"]
    assert markdown.split_table_row("| `A | B` | C |") == ["`A | B`", "C"]
    assert markdown.split_table_row("| [A|B](x) | C |") == ["[A|B](x)", "C"]
    assert markdown.is_table_divider("| --- | :---: | ---: |")
    assert not markdown.is_table_divider("| A | B |")


def test_extract_mermaid_labels() -> None:
    assert mermaid.extract_mermaid_label('A["Начало"]') == ("A", "Начало")
    assert mermaid.extract_mermaid_label("A((Start))") == ("A", "Start")
    assert mermaid.extract_mermaid_label("A([Start])") == ("A", "Start")
    assert mermaid.extract_mermaid_label("A[(Database)]") == ("A", "Database")
    assert mermaid.extract_mermaid_label("A>Asym]") == ("A", "Asym")
    assert mermaid.extract_mermaid_label("A{{Hex}}") == ("A", "Hex")
    assert mermaid.extract_mermaid_label("A[/Input/]") == ("A", "Input")
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


def test_parse_edges_keeps_standalone_flowchart_nodes() -> None:
    direction, labels, edges = mermaid.parse_edges(["flowchart LR", "A[Only node]"])

    assert direction == "LR"
    assert labels == {"A": "Only node"}
    assert edges == []


def test_parse_edges_ignores_flowchart_style_directives() -> None:
    _, labels, edges = mermaid.parse_edges(
        [
            "flowchart LR",
            "A --> B",
            "classDef warn fill:#f00",
            "class A warn",
            "style B fill:#fff",
            "linkStyle 0 stroke:#f00",
        ]
    )

    assert labels == {"A": "A", "B": "B"}
    assert edges == [("A", "B", "")]


def test_parse_edges_ignores_flowchart_container_and_interaction_directives() -> None:
    _, labels, edges = mermaid.parse_edges(
        [
            "flowchart LR",
            "subgraph G",
            "direction TB",
            "A --> B",
            "click A href \"https://example.com\"",
            "end",
        ]
    )

    assert labels == {"A": "A", "B": "B"}
    assert edges == [("A", "B", "")]


def test_parse_edges_supports_common_flowchart_link_markers() -> None:
    for marker in ("---", "-.->", "==>"):
        _, labels, edges = mermaid.parse_edges(["flowchart LR", f"A {marker} B"])

        assert labels == {"A": "A", "B": "B"}
        assert edges == [("A", "B", "")]


def test_parse_edges_supports_labeled_dotted_and_endpoint_markers() -> None:
    for edge in ("A -. maybe .-> B", "A o--o B", "A x--x B"):
        _, labels, edges = mermaid.parse_edges(["flowchart LR", edge])

        assert labels == {"A": "A", "B": "B"}
        assert edges == [("A", "B", "")]


def test_parse_edges_supports_single_sided_endpoint_markers() -> None:
    for edge in ("A --o B", "A --x B", "A o-- B", "A x-- B"):
        _, labels, edges = mermaid.parse_edges(["flowchart LR", edge])

        assert labels == {"A": "A", "B": "B"}
        assert edges == [("A", "B", "")]


def test_parse_edges_supports_grouped_flowchart_links() -> None:
    _, labels, edges = mermaid.parse_edges(["flowchart LR", "A & B --> C & D"])

    assert labels == {"A": "A", "B": "B", "C": "C", "D": "D"}
    assert edges == [("A", "C", ""), ("A", "D", ""), ("B", "C", ""), ("B", "D", "")]


def test_parse_edges_supports_chained_flowchart_links() -> None:
    _, labels, edges = mermaid.parse_edges(["flowchart LR", "A --> B --> C"])

    assert labels == {"A": "A", "B": "B", "C": "C"}
    assert edges == [("A", "B", ""), ("B", "C", "")]


def test_parse_edges_supports_semicolon_separated_flowchart_links() -> None:
    _, labels, edges = mermaid.parse_edges(["flowchart LR", "A --> B; B --> C"])

    assert labels == {"A": "A", "B": "B", "C": "C"}
    assert edges == [("A", "B", ""), ("B", "C", "")]


def test_parse_edges_ignores_link_markers_inside_node_labels() -> None:
    _, labels, edges = mermaid.parse_edges(["flowchart LR", 'A["hello --> world"] --> B'])

    assert labels == {"A": "hello --> world", "B": "B"}
    assert edges == [("A", "B", "")]


def test_resolve_mermaid_viewport_counts_actor_and_single_arrow_messages() -> None:
    assert mermaid.resolve_mermaid_viewport(["sequenceDiagram", "actor A", "actor B", "actor C"])[0] == 2850
    assert (
        mermaid.resolve_mermaid_viewport(
            [
                "sequenceDiagram",
                "A->B: 1",
                "A->B: 2",
                "A->B: 3",
                "A->B: 4",
                "A->B: 5",
                "A->B: 6",
            ]
        )[1]
        == 1790
    )


def test_resolve_mermaid_viewport_counts_async_and_destroy_messages() -> None:
    assert (
        mermaid.resolve_mermaid_viewport(
            [
                "sequenceDiagram",
                "A-)B: 1",
                "A-xB: 2",
                "A-)B: 3",
                "A-xB: 4",
                "A-)B: 5",
                "A-xB: 6",
            ]
        )[1]
        == 1790
    )


def test_prepare_mermaid_for_pdf_counts_supported_flowchart_edges() -> None:
    assert (
        mermaid.prepare_mermaid_for_pdf(
            [
                "graph LR",
                "A --- B",
                "B --- C",
                "C --- D",
                "D --- E",
                "E --- F",
            ]
        )[0]
        == "flowchart TB"
    )
    assert (
        mermaid.prepare_mermaid_for_pdf(
            [
                "flowchart LR",
                "A ==> B",
                "B ==> C",
                "C ==> D",
                "D ==> E",
                "E ==> F",
            ]
        )[0]
        == "flowchart TB"
    )


def test_mermaid_cli_failure_uses_builtin_renderer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
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


def test_mermaid_cli_subprocess_error_uses_builtin_renderer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "MERMAID_DIR", tmp_path / ".md2pdf" / "mermaid")
    monkeypatch.setattr(config, "MERMAID_COUNTER", 0)
    monkeypatch.setattr(config, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(config, "FONT_BOLD", "Helvetica-Bold")
    monkeypatch.setattr(mermaid, "load_font", lambda size, bold=False: ImageFont.load_default())

    local_mmdc = tmp_path / "node_modules" / ".bin" / "mmdc"
    local_mmdc.parent.mkdir(parents=True)
    local_mmdc.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")

    def fail_run(*args, **kwargs):  # noqa: ANN002, ANN003
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(subprocess, "run", fail_run)

    path = mermaid.render_mermaid_image(["flowchart LR", '  A["Markdown"] --> B["PDF"]'])

    assert path is not None
    assert path.exists()


def test_mermaid_cli_timeout_uses_builtin_renderer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "MERMAID_DIR", tmp_path / ".md2pdf" / "mermaid")
    monkeypatch.setattr(config, "MERMAID_COUNTER", 0)
    monkeypatch.setattr(config, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(config, "FONT_BOLD", "Helvetica-Bold")
    monkeypatch.setattr(mermaid, "load_font", lambda size, bold=False: ImageFont.load_default())

    local_mmdc = tmp_path / "node_modules" / ".bin" / "mmdc"
    local_mmdc.parent.mkdir(parents=True)
    local_mmdc.write_text("#!/bin/sh\nsleep 120\n", encoding="utf-8")

    def timeout_run(*args, **kwargs):  # noqa: ANN002, ANN003
        raise subprocess.TimeoutExpired(args[0], 60)

    monkeypatch.setattr(subprocess, "run", timeout_run)

    path = mermaid.render_mermaid_image(["flowchart LR", '  A["Markdown"] --> B["PDF"]'])

    assert path is not None
    assert path.exists()


def test_mermaid_cli_is_primary_for_sequence_diagrams(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "MERMAID_DIR", tmp_path / ".md2pdf" / "mermaid")
    monkeypatch.setattr(config, "MERMAID_COUNTER", 0)

    def fake_cli_render(code: list[str], index: int) -> Path:
        path = config.MERMAID_DIR / f"diagram_{index:02d}.png"
        path.write_bytes(b"png")
        return path

    def fail_builtin(*args, **kwargs):  # noqa: ANN002, ANN003
        pytest.fail("built-in sequence renderer should not run when Mermaid CLI succeeds")

    monkeypatch.setattr(mermaid, "try_render_mermaid_with_cli", fake_cli_render)
    monkeypatch.setattr(mermaid, "render_sequence", fail_builtin)

    path = mermaid.render_mermaid_image(["sequenceDiagram", "  A->>B: ok"])

    assert path == config.MERMAID_DIR / "diagram_01.png"
    assert path.exists()


def test_graph_keyword_uses_flowchart_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "MERMAID_DIR", tmp_path / ".md2pdf" / "mermaid")
    monkeypatch.setattr(config, "MERMAID_COUNTER", 0)
    monkeypatch.setattr(config, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(config, "FONT_BOLD", "Helvetica-Bold")
    monkeypatch.setattr(mermaid, "load_font", lambda size, bold=False: ImageFont.load_default())
    monkeypatch.setattr(mermaid, "render_mermaid_with_cli", lambda code, index: None)

    path = mermaid.render_mermaid_image(["graph LR", "A --> B"])

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
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)

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
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)

    def fail_run(*args, **kwargs):  # noqa: ANN002, ANN003
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout="", stderr="browser failed")

    monkeypatch.setattr(subprocess, "run", fail_run)

    with pytest.raises(SystemExit) as error:
        main([str(source), str(target), "--strict-mermaid"])

    assert error.value.code == 1
    assert "Mermaid render failed" in capsys.readouterr().err


def test_cli_strict_mermaid_subprocess_error_is_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(config, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(config, "FONT_BOLD", "Helvetica-Bold")
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "strict-subprocess.md"
    target = tmp_path / "strict-subprocess.pdf"
    source.write_text("# Strict\n\n```mermaid\nflowchart LR\n  A --> B\n```\n", encoding="utf-8")

    def fail_cli(*args, **kwargs):  # noqa: ANN002, ANN003
        raise subprocess.CalledProcessError(1, "mmdc")

    monkeypatch.setattr(mermaid, "render_mermaid_with_cli", fail_cli)

    with pytest.raises(SystemExit) as error:
        main([str(source), str(target), "--strict-mermaid"])

    assert error.value.code == 1
    stderr = capsys.readouterr().err
    assert "Mermaid CLI error" in stderr
    assert "Traceback" not in stderr


def test_build_pdf_without_mermaid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "input.md"
    target = tmp_path / "output.pdf"
    source.write_text("# Title\n\nBody text.\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n", encoding="utf-8")

    pdf.build_pdf(source, target)

    assert target.exists()
    assert target.stat().st_size > 0


def test_indented_fenced_code_is_not_parsed_as_markdown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "indented-code.md"
    target = tmp_path / "indented-code.pdf"
    source.write_text("# Title\n\n  ```\n# not heading\n  ```\n", encoding="utf-8")

    pdf.build_pdf(source, target)

    reader = PdfReader(target)
    text = reader.pages[0].extract_text() or ""
    assert len(reader.pages) == 1
    assert "not heading" in text


def test_tilde_fenced_code_renders_as_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "tilde-code.md"
    target = tmp_path / "tilde-code.pdf"
    source.write_text("# Title\n\n~~~python\nprint(1)\n~~~\n", encoding="utf-8")

    pdf.build_pdf(source, target)

    text = PdfReader(target).pages[0].extract_text() or ""
    assert "print(1)" in text
    assert "~~~" not in text


def test_code_fence_requires_matching_marker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "mismatched-fence.md"
    target = tmp_path / "mismatched-fence.pdf"
    source.write_text("# Title\n\n```\ninside\n~~~\nafter\n```\n", encoding="utf-8")

    pdf.build_pdf(source, target)

    text = PdfReader(target).pages[0].extract_text() or ""
    assert "inside" in text
    assert "~~~" in text
    assert "after" in text


def test_code_fence_requires_closing_marker_at_least_opening_length(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "long-fence.md"
    target = tmp_path / "long-fence.pdf"
    source.write_text("# Title\n\n````\ninside\n```\nstill code\n````\n", encoding="utf-8")

    pdf.build_pdf(source, target)

    text = PdfReader(target).pages[0].extract_text() or ""
    assert "inside" in text
    assert "```" in text
    assert "still code" in text


def test_code_fence_with_trailing_text_does_not_close(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "trailing-fence.md"
    target = tmp_path / "trailing-fence.pdf"
    source.write_text("# Title\n\n```\ninside\n``` not close\nstill code\n```\n", encoding="utf-8")

    pdf.build_pdf(source, target)

    text = PdfReader(target).pages[0].extract_text() or ""
    assert "inside" in text
    assert "not close" in text
    assert "still code" in text


def test_backtick_fence_info_string_cannot_contain_backtick(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "invalid-info.md"
    target = tmp_path / "invalid-info.pdf"
    source.write_text("# Title\n\n```python`\n# should be heading\n```\n", encoding="utf-8")

    pdf.build_pdf(source, target)

    reader = PdfReader(target)
    assert len(reader.pages) == 2
    assert "should be heading" in (reader.pages[1].extract_text() or "")


def test_standalone_table_divider_is_preserved_as_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "divider.md"
    target = tmp_path / "divider.pdf"
    source.write_text("# Title\n\nBefore\n\n| --- |\n\nAfter\n", encoding="utf-8")

    pdf.build_pdf(source, target)

    text = PdfReader(target).pages[0].extract_text() or ""
    assert "Before" in text
    assert "---" in text
    assert "After" in text


def test_unknown_mermaid_block_renders_as_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "unknown.md"
    target = tmp_path / "unknown.pdf"
    source.write_text("# Unknown\n\n```mermaid\nunknownDiagram\n  A -> B\n```\n", encoding="utf-8")

    pdf.build_pdf(source, target)

    reader = PdfReader(target)
    assert "unknownDiagram" in (reader.pages[0].extract_text() or "")


def test_mermaid_info_string_renders_as_diagram(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))
    monkeypatch.setattr(config, "MERMAID_DIR", tmp_path / ".md2pdf" / "mermaid")
    monkeypatch.setattr(config, "MERMAID_COUNTER", 0)
    monkeypatch.setattr(mermaid, "render_mermaid_with_cli", lambda code, index: None)
    monkeypatch.setattr(mermaid, "load_font", lambda size, bold=False: ImageFont.load_default())

    source = tmp_path / "mermaid-info.md"
    target = tmp_path / "mermaid-info.pdf"
    source.write_text("# Diagram\n\n```Mermaid title=\"x\"\nflowchart LR\nA --> B\n```\n", encoding="utf-8")

    pdf.build_pdf(source, target)

    text = PdfReader(target).pages[0].extract_text() or ""
    assert "flowchart LR" not in text
    assert "A --> B" not in text


def test_raw_html_is_rendered_as_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf, "register_fonts", lambda: ("Helvetica", "Helvetica-Bold"))

    source = tmp_path / "raw-html.md"
    target = tmp_path / "raw-html.pdf"
    source.write_text("# Raw HTML\n\nRaw <b>open tag\n", encoding="utf-8")

    pdf.build_pdf(source, target)

    assert "Raw <b>open tag" in (PdfReader(target).pages[0].extract_text() or "")


def test_sequence_renderer_adds_implicit_participants(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(config, "FONT_BOLD", "Helvetica-Bold")
    monkeypatch.setattr(mermaid, "load_font", lambda size, bold=False: ImageFont.load_default())

    target = tmp_path / "sequence.png"

    mermaid.render_sequence(["sequenceDiagram", "participant A as Alice", "A->>B: Hi"], target)

    assert target.exists()


def test_sequence_renderer_supports_actor_alias(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(config, "FONT_BOLD", "Helvetica-Bold")
    monkeypatch.setattr(mermaid, "load_font", lambda size, bold=False: ImageFont.load_default())

    target = tmp_path / "sequence-actor.png"

    mermaid.render_sequence(["sequenceDiagram", "actor U as User", "U->>S: login"], target)

    assert target.exists()


def test_sequence_renderer_supports_single_arrow_messages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(config, "FONT_BOLD", "Helvetica-Bold")
    monkeypatch.setattr(mermaid, "load_font", lambda size, bold=False: ImageFont.load_default())

    target = tmp_path / "sequence-single-arrow.png"

    mermaid.render_sequence(["sequenceDiagram", "A->B: sync"], target)

    assert target.exists()


def test_sequence_renderer_strips_activation_markers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(config, "FONT_BOLD", "Helvetica-Bold")
    monkeypatch.setattr(mermaid, "load_font", lambda size, bold=False: ImageFont.load_default())

    target = tmp_path / "sequence-activation.png"

    mermaid.render_sequence(["sequenceDiagram", "A->>+B: start", "B-->>-A: done"], target)

    assert target.exists()


def test_sequence_renderer_supports_async_and_destroy_arrows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(config, "FONT_BOLD", "Helvetica-Bold")
    monkeypatch.setattr(mermaid, "load_font", lambda size, bold=False: ImageFont.load_default())

    target = tmp_path / "sequence-extra-arrows.png"

    mermaid.render_sequence(["sequenceDiagram", "A-)B: async", "B-xC: destroy"], target)

    assert target.exists()


def test_state_renderer_supports_state_alias(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(config, "FONT_BOLD", "Helvetica-Bold")
    monkeypatch.setattr(mermaid, "load_font", lambda size, bold=False: ImageFont.load_default())
    captured: list[str] = []
    original_draw_box = mermaid.draw_box

    def capture_label(draw, rect, label, fill="#F7F9FC", outline="#273452"):  # noqa: ANN001
        captured.append(label)
        return original_draw_box(draw, rect, label, fill, outline)

    monkeypatch.setattr(mermaid, "draw_box", capture_label)

    mermaid.render_state(["stateDiagram-v2", 'state "Long label" as A', "[*] --> A"], tmp_path / "state.png")

    assert "Long label" in captured


def test_xychart_renderer_handles_many_bars(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(config, "FONT_BOLD", "Helvetica-Bold")
    monkeypatch.setattr(mermaid, "load_font", lambda size, bold=False: ImageFont.load_default())

    target = tmp_path / "xychart-many-bars.png"
    values = ", ".join(str(index) for index in range(50))

    mermaid.render_xychart(["xychart-beta", 'title "Many"', f"bar [{values}]"], target)

    assert target.exists()


def test_xychart_parser_handles_unquoted_labels_and_short_decimals() -> None:
    assert mermaid.parse_xychart_labels("x-axis [A, B, C]") == ["A", "B", "C"]
    assert mermaid.parse_xychart_labels('x-axis [Jan, "Feb, Mar"]') == ["Jan", "Feb, Mar"]
    assert mermaid.parse_xychart_values("bar [.5, -.5, 1e3]") == [0.5, -0.5, 1000.0]


def test_xychart_renderer_uses_line_series(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(config, "FONT_BOLD", "Helvetica-Bold")
    monkeypatch.setattr(mermaid, "load_font", lambda size, bold=False: ImageFont.load_default())

    target = tmp_path / "xychart-line.png"

    assert mermaid.parse_xychart_series(["xychart-beta", "line [1, 2]"]) == ([], [1.0, 2.0])

    mermaid.render_xychart(["xychart-beta", "x-axis [A, B]", "line [1, 2]"], target)

    assert target.exists()


def test_cleanup_mermaid_dir_keeps_unrelated_diagram_prefixed_files(tmp_path: Path) -> None:
    generated = tmp_path / "diagram_01.png"
    generated_after_99 = tmp_path / "diagram_100.png"
    generated_config = tmp_path / "diagram_01_mermaid-config.json"
    unrelated_json = tmp_path / "diagram_01.json"
    unrelated = tmp_path / "diagram_keep.txt"
    config_file = tmp_path / "mermaid-config.json"
    generated.write_bytes(b"png")
    generated_after_99.write_bytes(b"png")
    generated_config.write_text("generated", encoding="utf-8")
    unrelated_json.write_text("user metadata", encoding="utf-8")
    unrelated.write_text("user data", encoding="utf-8")
    config_file.write_text("{}", encoding="utf-8")

    original_dir = config.MERMAID_DIR
    try:
        config.set_mermaid_dir(tmp_path)
        mermaid.cleanup_mermaid_dir()
    finally:
        config.set_mermaid_dir(original_dir)

    assert not generated.exists()
    assert not generated_after_99.exists()
    assert not generated_config.exists()
    assert unrelated_json.exists()
    assert config_file.exists()
    assert unrelated.exists()


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


def test_cli_reports_non_utf8_input_without_traceback(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    source = tmp_path / "invalid.md"
    target = tmp_path / "invalid.pdf"
    source.write_bytes(b"\xff")

    with pytest.raises(SystemExit) as error:
        main([str(source), str(target)])

    assert error.value.code == 1
    stderr = capsys.readouterr().err
    assert "UTF-8" in stderr
    assert "Traceback" not in stderr
