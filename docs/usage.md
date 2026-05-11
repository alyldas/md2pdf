# Usage

## Installed command

After installing the package, run:

```bash
md2pdf input.md output.pdf
```

If arguments are omitted, the command reads `README.md` and writes `README.pdf` in the current directory.

## Local checkout

From a repository checkout, run the package without installing it:

```bash
PYTHONPATH=src python3 -m md2pdf README.md README.pdf
```

The npm shortcuts wrap the same command:

```bash
npm run pdf
npm run example
```

## Mermaid behavior

The converter first tries Mermaid CLI through the local `node_modules/.bin/mmdc` or a global `mmdc`. For supported diagram families, it uses a simple built-in renderer only when Mermaid CLI is unavailable or fails outside strict mode.

Use strict mode when CI should fail on Mermaid CLI errors:

```bash
md2pdf README.md README.pdf --strict-mermaid
```

The environment variable remains supported:

```bash
MD2PDF_STRICT_MERMAID=1 md2pdf README.md README.pdf
```

Use a custom directory for Mermaid intermediate files:

```bash
md2pdf README.md README.pdf --temp-dir .md2pdf/readme
```

Suppress built-in renderer warnings:

```bash
md2pdf README.md README.pdf --quiet
```

Keep Mermaid intermediate files for debugging:

```bash
md2pdf README.md README.pdf --keep-temp
```

Customize layout:

```bash
md2pdf README.md README.pdf --font-size 13 --line-height 1.45 --diagram-max-height 120
md2pdf README.md README.pdf --margins 30,10,20,20
```

Check local dependencies without building:

```bash
md2pdf --check-deps
```

Print the installed version:

```bash
md2pdf --version
```
