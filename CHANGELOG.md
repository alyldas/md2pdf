# Changelog

Формат основан на Keep a Changelog, версии следуют Semantic Versioning.

## [Unreleased]

### Changed

- Nothing yet.

## [1.0.5] - 2026-05-11

### Fixed

- Linux font discovery now checks both Liberation Serif install locations used by Ubuntu packages.
- CI and release runners install both Liberation font packages before building public PDF artifacts.

## [1.0.4] - 2026-05-11

### Fixed

- Public PDF artifacts no longer force-justify body and list text, avoiding excessive word spacing.
- CI and release runners install Liberation Serif so Linux-built PDFs use a narrower serif font before falling back to DejaVu Serif.

## [1.0.3] - 2026-05-11

### Changed

- README badges now use live GitHub Actions and Shields URLs.
- Release workflow now publishes Python distributions to PyPI through Trusted Publishing.
- Release documentation now records the PyPI Trusted Publisher settings.

## [1.0.2] - 2026-05-11

### Fixed

- Mermaid CLI is now the primary renderer for every Mermaid block type.
- Release builds now run Mermaid rendering in strict mode so broken primary rendering cannot publish degraded PDF artifacts.

## [1.0.1] - 2026-05-11

### Changed

- CI and release workflows opt into Node.js 24 for JavaScript actions.
- Release workflow now runs Mermaid tooling on Node.js 24.
- README now uses local status badges with relative links.

## [1.0.0] - 2026-05-11

### Added

- Python package metadata and `md2pdf` console entry point.
- Package layout with `md2pdf.cli`, `md2pdf.__main__` and a public facade.
- Split implementation modules for configuration, Markdown helpers, Mermaid rendering and PDF generation.
- CLI flags for version output, strict Mermaid mode, quiet built-in renderer warnings and custom temp directories.
- CLI layout flags for font size, line height, diagram height and page margins.
- Dependency check command and temporary Mermaid file cleanup.
- Release workflow, release docs, code owners and code of conduct.
- PDF smoke tests through `pypdf`.
- Usage and development docs under `docs/`.
- Pytest coverage for Markdown helpers, Mermaid parsing and built-in rendering.
- GitHub Actions CI for linting, tests and smoke PDF builds.
- Contributor, security and issue/PR templates.

### Changed

- Mermaid CLI failures now use built-in renderers for supported diagram types.
- README now documents installation, development, troubleshooting and project limits.

## [0.1.0] - 2026-05-11

### Added

- Initial Markdown to PDF converter.
- Basic support for headings, paragraphs, lists, tables, code blocks and Mermaid diagrams.
