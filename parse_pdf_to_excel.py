import argparse, os, io, math, yaml
import pandas as pd
from typing import List, Dict, Any
from datetime import datetime

# Extraction libs
import pdfplumber
try:
    import camelot
except Exception:
    camelot = None

try:
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image
except Exception:
    pytesseract = None

from parsers.generic_parser import GenericParser

COLUMNS = ["Date","Description","Debit","Credit","Balance","CheckNo","Page","SourceLine"]

def detect_text_pdf(pdf_path: str) -> bool:
    """Return True if the PDF seems to contain extractable text."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:3]:
                words = page.extract_words(x_tolerance=1, y_tolerance=1) or []
                if len(words) > 0:
                    return True
        return False
    except Exception:
        return False

def ocr_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """OCR each page to text lines. Requires tesseract/poppler; falls back to empty if not installed."""
    lines = []
    if pytesseract is None:
        return lines
    images = convert_from_path(pdf_path, dpi=300)
    for i, img in enumerate(images, start=1):
        text = pytesseract.image_to_string(img)
        for line in text.splitlines():
            line = line.strip()
            if line:
                lines.append({"text": line, "x0": None, "x1": None, "top": None, "bottom": None, "page": i})
    return lines

def extract_lines_pdfplumber(pdf_path: str) -> List[Dict[str, Any]]:
    """Extract per-line text with coordinates from a text-based PDF."""
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            # Get lines by grouping words by their y-coordinate bands
            words = page.extract_words(x_tolerance=2, y_tolerance=2) or []
            if not words:
                text = (page.extract_text() or "").splitlines()
                for t in text:
                    if t.strip():
                        out.append({"text": t.strip(), "x0": None, "x1": None, "top": None, "bottom": None, "page": i})
                continue

            words.sort(key=lambda w: (round(w["top"], 1), w["x0"]))
            current_top = None
            buffer = []
            for w in words:
                t = round(w["top"], 1)
                if current_top is None:
                    current_top = t
                if abs(t - current_top) <= 1.0:
                    buffer.append(w)
                else:
                    if buffer:
                        text = " ".join(x["text"] for x in sorted(buffer, key=lambda z: z["x0"]))
                        x0 = min(x["x0"] for x in buffer)
                        x1 = max(x["x1"] for x in buffer)
                        top = min(x["top"] for x in buffer)
                        bottom = max(x["bottom"] for x in buffer)
                        out.append({"text": text, "x0": x0, "x1": x1, "top": top, "bottom": bottom, "page": i})
                    buffer = [w]
                    current_top = t
            if buffer:
                text = " ".join(x["text"] for x in sorted(buffer, key=lambda z: z["x0"]))
                x0 = min(x["x0"] for x in buffer)
                x1 = max(x["x1"] for x in buffer)
                top = min(x["top"] for x in buffer)
                bottom = max(x["bottom"] for x in buffer)
                out.append({"text": text, "x0": x0, "x1": x1, "top": top, "bottom": bottom, "page": i})
    return out

def try_camelot(pdf_path: str) -> List[pd.DataFrame]:
    """Attempt to extract tables with camelot (both lattice and stream)."""
    if camelot is None:
        return []
    dfs = []
    try:
        r1 = camelot.read_pdf(pdf_path, flavor="lattice", pages="all")
        dfs += [t.df for t in r1]
    except Exception:
        pass
    try:
        r2 = camelot.read_pdf(pdf_path, flavor="stream", pages="all")
        dfs += [t.df for t in r2]
    except Exception:
        pass
    return dfs

def normalize_tables(dfs: List[pd.DataFrame]) -> pd.DataFrame:
    """Heuristic: try to convert table dfs into the standard columns; best-effort merge."""
    if not dfs:
        return pd.DataFrame(columns=COLUMNS)
    candidates = []
    for df in dfs:
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        df = df.applymap(lambda x: (str(x).strip() if pd.notna(x) else ""))
        for col in df.columns:
            df[col] = df[col].str.replace("\\n", " ", regex=False).str.replace("\\s+", " ", regex=True).str.strip()
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        desc_col = next((c for c in df.columns if "descr" in c.lower() or "details" in c.lower() or "transaction" in c.lower()), None)
        amt_col = next((c for c in df.columns if any(k in c.lower() for k in ["amount","amt","debit/credit","debit credit"])), None)
        debit_col = next((c for c in df.columns if "debit" in c.lower()), None)
        credit_col = next((c for c in df.columns if "credit" in c.lower()), None)
        balance_col = next((c for c in df.columns if "balance" in c.lower()), None)
        checkno_col = next((c for c in df.columns if "check" in c.lower()), None)

        out = pd.DataFrame(columns=COLUMNS)
        if date_col and desc_col and (amt_col or debit_col or credit_col):
            out["Date"] = df[date_col]
            out["Description"] = df[desc_col]
            if amt_col:
                def norm_amt(x):
                    x = str(x).replace(",", "").strip()
                    if x.startswith("(") and x.endswith(")"):
                        x = "-" + x[1:-1]
                    try:
                        return float(x)
                    except:
                        return None
                vals = df[amt_col].map(norm_amt)
                out["Debit"] = vals.map(lambda v: abs(v) if v is not None and v < 0 else None)
                out["Credit"] = vals.map(lambda v: v if v is not None and v >= 0 else None)
            else:
                out["Debit"] = pd.to_numeric(df[debit_col], errors="coerce")
                out["Credit"] = pd.to_numeric(df[credit_col], errors="coerce")
            out["Balance"] = pd.to_numeric(df[balance_col], errors="coerce") if balance_col else None
            out["CheckNo"] = df[checkno_col] if checkno_col else None
            candidates.append(out)

    if not candidates:
        return pd.DataFrame(columns=COLUMNS)
    merged = pd.concat(candidates, ignore_index=True)
    merged["Page"] = None
    merged["SourceLine"] = None
    return merged[COLUMNS]

def write_excel(out_path: str, tx: pd.DataFrame, raw_lines: pd.DataFrame, issues: pd.DataFrame, meta: Dict[str, Any]):
    with pd.ExcelWriter(out_path, engine="xlsxwriter") as xw:
        tx.to_excel(xw, index=False, sheet_name="Transactions")
        ws = xw.sheets["Transactions"]
        ws.autofilter(0, 0, len(tx), len(tx.columns)-1)
        ws.freeze_panes(1, 0)
        wb = xw.book
        fmt_money = wb.add_format({"num_format": "$#,##0.00"})
        try:
            dcol = tx.columns.get_loc("Debit")
            ccol = tx.columns.get_loc("Credit")
            bcol = tx.columns.get_loc("Balance")
            ws.set_column(dcol, dcol, 14, fmt_money)
            ws.set_column(ccol, ccol, 14, fmt_money)
            ws.set_column(bcol, bcol, 14, fmt_money)
        except Exception:
            pass

        raw_lines.to_excel(xw, index=False, sheet_name="Raw_Extract")
        xw.sheets["Raw_Extract"].freeze_panes(1, 0)

        issues.to_excel(xw, index=False, sheet_name="Issues")
        xw.sheets["Issues"].freeze_panes(1, 0)

        md = pd.DataFrame([meta])
        md.to_excel(xw, index=False, sheet_name="Metadata")

def validate_running_balance(df: pd.DataFrame) -> List[str]:
    problems = []
    try:
        tmp = df.copy()
        for col in ["Debit","Credit","Balance"]:
            tmp[col] = pd.to_numeric(tmp[col], errors="coerce")
        tmp["Net"] = (tmp["Credit"].fillna(0) - tmp["Debit"].fillna(0))
        if tmp["Balance"].notna().sum() >= 2:
            prev = None
            for idx, row in tmp.iterrows():
                if pd.notna(row["Balance"]):
                    if prev is not None:
                        expected = prev + row.get("Net", 0)
                        if pd.notna(row["Net"]) and abs(row["Balance"] - expected) > 0.02:
                            problems.append(f"Row {idx}: balance jump mismatch; expected ~{expected:.2f}, saw {row['Balance']:.2f}")
                    prev = row["Balance"]
    except Exception as e:
        problems.append(f"Balance validation error: {e}")
    return problems

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True, help="Path to input PDF")
    ap.add_argument("--out", required=True, help="Path to output Excel (.xlsx)")
    ap.add_argument("--template", help="YAML template with regex/column rules", default=None)
    args = ap.parse_args()

    meta = {
        "input_pdf": os.path.abspath(args.pdf),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method": None,
        "notes": []
    }

    template = None
    if args.template and os.path.exists(args.template):
        with open(args.template, "r") as f:
            template = yaml.safe_load(f) or {}

    tables_df = normalize_tables(try_camelot(args.pdf))
    is_text_pdf = detect_text_pdf(args.pdf)
    if is_text_pdf:
        lines = extract_lines_pdfplumber(args.pdf)
        meta["method"] = "text-pdf + line-parse"
    else:
        meta["notes"].append("No embedded text detected; trying OCR.")
        lines = ocr_pdf(args.pdf)
        meta["method"] = "ocr + line-parse"

    raw_lines = pd.DataFrame(lines, columns=["page","text","x0","x1","top","bottom"])

    parser = GenericParser(template=template)
    tx_df = parser.parse(lines)

    if tables_df is not None and not tables_df.empty and (tx_df is None or tx_df.empty):
        tx_df = tables_df
        meta["notes"].append("Used Camelot table output (regex parse was empty).")
    elif tables_df is not None and not tables_df.empty and not tx_df.empty:
        merged = pd.concat([tx_df, tables_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["Date","Description","Debit","Credit","Balance"], keep="first")
        tx_df = merged
        meta["notes"].append("Merged Camelot and regex results; removed duplicates.")

    issues = []
    unparsed = tx_df.attrs.get("unparsed", []) if hasattr(tx_df, "attrs") else []
    for up in unparsed:
        issues.append({"type":"unparsed_line","page":up.get("page"),"text":up.get("text")})
    ignored = tx_df.attrs.get("ignored", []) if hasattr(tx_df, "attrs") else []
    for ig in ignored:
        issues.append({"type":"ignored_line","page":ig.get("page"),"text":ig.get("text")})

    val_problems = validate_running_balance(tx_df)
    for p in val_problems:
        issues.append({"type":"balance_validation","detail":p})

    issues_df = pd.DataFrame(issues) if issues else pd.DataFrame(columns=["type","page","text","detail"])

    for col in ["Date","Description","Debit","Credit","Balance","CheckNo","Page","SourceLine"]:
        if col not in tx_df.columns:
            tx_df[col] = None
    tx_df = tx_df[["Date","Description","Debit","Credit","Balance","CheckNo","Page","SourceLine"]]

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_excel(args.out, tx_df, raw_lines, issues_df, meta)
    print(f"Done. Wrote: {args.out}")

if __name__ == "__main__":
    main()
