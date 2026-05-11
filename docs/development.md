# Development

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
npm install
```

## Checks

```bash
python -m ruff check .
python -m pytest -q
npm run pdf
npm run example
```

Or run the combined shortcut:

```bash
npm run check
```

## Source Layout

| Path | Purpose |
| --- | --- |
| `src/md2pdf/cli.py` | CLI argument parsing |
| `src/md2pdf/__main__.py` | `python -m md2pdf` entry point |
| `src/md2pdf/__init__.py` | Public package facade |
| `src/md2pdf/config.py` | Shared defaults, version, fonts and runtime flags |
| `src/md2pdf/markdown.py` | Markdown cleanup, tables and block helpers |
| `src/md2pdf/mermaid.py` | Mermaid CLI integration and built-in renderers |
| `src/md2pdf/pdf.py` | ReportLab PDF generation |
| `src/md2pdf/core.py` | Compatibility facade for older imports |
| `tests/test_md2pdf.py` | Unit and smoke tests |

Keep module boundaries simple: `config` has no package imports, `markdown` owns Markdown helpers, `mermaid` owns diagram rendering, and `pdf` assembles the document.
