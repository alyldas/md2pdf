# Changelog

Формат основан на Keep a Changelog, версии следуют Semantic Versioning.

## [Unreleased]

### Changed

- Nothing yet.

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
