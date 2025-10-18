import re
from typing import List, Dict, Any
import pandas as pd
from .base_parser import BaseParser

AMT = r"[+-]?(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?"
DATE = r"(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4})"

class GenericParser(BaseParser):
    """
    A regex-based fallback parser that works for many bank statements of the form:
      08/12/2025  STARBUCKS #1234     -5.67      1,234.56
    Captures:
      Date, Description, Debit or Credit, optional Balance
    Supports:
      - ignore_patterns: list of regex strings — lines matching any will be skipped
    """

    def __init__(self, template: Dict[str, Any] | None = None):
        self.template = template or {}
        # Prefer template patterns if provided
        self.date_pat = self.template.get("date_patterns", [DATE])
        # line_regex supports named groups: date, desc, debit, credit, amount, balance, checkno
        self.line_regex = self.template.get("line_regex") or rf"^(?P<date>{DATE})\s+(?P<desc>.+?)\s+(?P<amount>{AMT})(?:\s+(?P<balance>{AMT}))?$"
        self.split_credit_debit = self.template.get("split_credit_debit", True)
        self.negative_is_debit = self.template.get("negative_is_debit", True)

        self.ignore_pats = [re.compile(p) for p in self.template.get("ignore_patterns", [])]

    def _norm_amt(self, s: str | None):
        if not s: return None
        s = s.replace(",", "").strip()
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        try:
            return float(s)
        except:
            return None

    def _looks_like_date(self, s: str) -> bool:
        import re
        for dp in self.date_pat:
            if re.match(dp + r"$", s.strip()):
                return True
        return False

    def _ignored(self, text: str) -> bool:
        for rx in self.ignore_pats:
            if rx.search(text):
                return True
        return False

    def parse(self, lines: List[Dict[str, Any]]) -> pd.DataFrame:
        out = []
        unparsed = []
        ignored = []
        rx = re.compile(self.line_regex)

        for ln in lines:
            text = " ".join(ln["text"].split())  # normalize spaces

            if self._ignored(text):
                ignored.append(ln)
                continue

            m = rx.search(text)
            if not m:
                unparsed.append(ln)
                continue

            gd = m.groupdict()
            date = gd.get("date")
            desc = gd.get("desc")
            amount = self._norm_amt(gd.get("amount"))
            balance = self._norm_amt(gd.get("balance"))

            debit, credit = None, None
            if self.split_credit_debit:
                if amount is not None:
                    if self.negative_is_debit and amount < 0:
                        debit = abs(amount)
                    elif (not self.negative_is_debit) and amount < 0:
                        credit = abs(amount)
                    else:
                        # positive amounts → credits by default
                        credit = amount
            else:
                credit = amount

            out.append({
                "Date": date,
                "Description": desc,
                "Debit": debit,
                "Credit": credit,
                "Balance": balance,
                "CheckNo": None,
                "Page": ln.get("page"),
                "SourceLine": text
            })

        df = pd.DataFrame(out)
        df = self.ensure_columns(df)

        # Attach unparsed/ignored lines for the caller to log into Issues sheet
        df.attrs["unparsed"] = unparsed
        df.attrs["ignored"] = ignored
        return df
