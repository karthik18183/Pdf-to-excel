from abc import ABC, abstractmethod
from typing import List, Dict, Any
import pandas as pd

class BaseParser(ABC):
    """Abstract base for statement parsers. Implement `parse` to return a DataFrame of transactions."""
    required_columns = ["Date","Description","Debit","Credit","Balance","CheckNo","Page","SourceLine"]

    @abstractmethod
    def parse(self, lines: List[Dict[str, Any]]) -> pd.DataFrame:
        """lines: list of dicts with {text, x0, x1, top, bottom, page}"""
        pass

    def ensure_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in self.required_columns:
            if col not in df.columns:
                df[col] = None
        return df[self.required_columns]
