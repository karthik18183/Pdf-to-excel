# PDF → Excel (Bank Statements) — Starter Kit

This starter kit parses **bank statement PDFs** into a clean Excel workbook with columns:
`Date, Description, Debit, Credit, Balance, CheckNo, Page, SourceLine`.
It also includes:
- **Raw_Extract** sheet with the exact lines (and coordinates) we pulled from the PDF
- **Issues** sheet with validation flags (e.g., unparsed lines, balance mismatches)
- **Metadata** sheet with file info and extraction details

## Features
- Handles both **text-based PDFs** and **scanned PDFs** (OCR via Tesseract if installed).
- Two extraction paths:
  1. **Tables first** with Camelot (lattice & stream).
  2. **Regex/line-parser** with pdfplumber (fallback & for non-tabular layouts).
- Template-ready: add bank-specific rules via `config/*.yaml`.
- Robust parsing of amounts (commas, parentheses for negatives), dates, and running balance checks.
- Exports a styled Excel with filters, freeze panes, and currency formats.

## Quick Start
```bash
# 1) Create & activate a virtualenv (recommended)
python -m venv .venv && source .venv/bin/activate  # (on Windows: .venv\Scripts\activate)

# 2) Install deps (Poppler & Tesseract are optional but recommended)
pip install -r requirements.txt

# 3) Run
python parse_pdf_to_excel.py --pdf /path/to/YourStatement.pdf --out /path/to/out.xlsx
# Optional: provide a template to guide parsing
python parse_pdf_to_excel.py --pdf /path/to/YourStatement.pdf --out /path/to/out.xlsx --template config/example_template.yaml
```

### System Packages (optional, for best results)
- **Tesseract** (OCR): `brew install tesseract` (macOS) or `sudo apt-get install tesseract-ocr` (Ubuntu).
- **Poppler** (for pdf2image): `brew install poppler` or `sudo apt-get install poppler-utils`.

## Add Your Own Template
Copy `config/example_template.yaml` and adjust:
- `date_patterns`: regex for the date formats your bank uses
- `line_regex`: how a transaction line is structured
- `columns_map`: which capture group goes to which column

Then pass `--template your.yaml` when running.

## Notes
- If your PDF is purely images (no embedded text), the pipeline automatically switches to OCR if available.
- If tables fail to extract, the parser falls back to a regex per line.
- Everything unparsed lands in **Raw_Extract** and **Issues** for manual review.
