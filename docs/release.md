# Release Process

## Versioning

Use semantic versioning. Before tagging a release, keep these values aligned:

- `pyproject.toml` project version;
- `src/md2pdf/config.py` `VERSION`;
- `package.json` version;
- `CHANGELOG.md`.

## Local Checklist

```bash
npm install
python -m pip install -e ".[dev]"
npm run check
python -m build
md2pdf --version
```

Linux release runners install `fonts-liberation` so public PDF artifacts use Liberation Serif instead of the wider DejaVu Serif fallback.

Render the public artifacts:

```bash
npm run pdf
npm run example
```

## Wheel Smoke Test

Install the built wheel in a clean virtual environment and run the public CLI:

```bash
python3 -m venv /tmp/md2pdf-wheel-smoke
/tmp/md2pdf-wheel-smoke/bin/python -m pip install --upgrade pip
/tmp/md2pdf-wheel-smoke/bin/python -m pip install dist/md2pdf_gost-<version>-py3-none-any.whl
/tmp/md2pdf-wheel-smoke/bin/md2pdf --version
/tmp/md2pdf-wheel-smoke/bin/md2pdf --check-deps
/tmp/md2pdf-wheel-smoke/bin/md2pdf examples/example.md /tmp/md2pdf-wheel-smoke/example.pdf --quiet
```

## PDF Artifacts

`README.pdf` and `examples/example.pdf` are committed as public examples. Update them only when one of these changes:

- Markdown source;
- PDF rendering behavior;
- package version in public documentation.

## Tagging

Create an annotated tag from a clean main branch:

```bash
git tag -a v<version> -m "Release v<version>"
git push origin v<version>
```

The release workflow runs checks, builds wheel and source distributions, and attaches Python distributions plus generated PDF examples to the GitHub release.

## PyPI

PyPI publication uses Trusted Publishing through GitHub Actions. The PyPI project must trust this exact publisher:

- project: `md2pdf-gost`;
- owner: `alyldas`;
- repository: `md2pdf`;
- workflow: `release.yml`;
- environment: `pypi`.

The GitHub `pypi` environment is used by the publish job. It may have required reviewers enabled if releases should require manual approval before upload.

Do not tag a PyPI-publishing release until the trusted publisher is configured on PyPI. Without that PyPI-side trust record, the GitHub release will build artifacts, but the PyPI upload job will fail authorization.

Publish only after verifying:

- the GitHub release artifacts;
- the package version;
- `md2pdf --version`;
- smoke PDF output from the built wheel.
