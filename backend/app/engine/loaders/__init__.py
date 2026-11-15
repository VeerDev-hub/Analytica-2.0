"""Load CSV / Excel / Parquet into a clean DataFrame (dataset version 1).

Ported from legacy/preprocessing.py with fixes:
- encoding and delimiter are detected instead of assumed;
- numeric conversion is lossless only (every non-null value must parse), so nothing is
  silently turned into NaN; partially numeric columns are reported by the profiler instead;
- column names are de-duplicated with suffixes rather than dropping columns.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

SUPPORTED_FORMATS = ("csv", "tsv", "txt", "xlsx", "xls", "parquet")


class LoadError(ValueError):
    """The file cannot be parsed. Message is safe to show to the user."""


@dataclass
class LoadResult:
    df: pd.DataFrame
    options: dict = field(default_factory=dict)  # what was detected/used
    notes: list[str] = field(default_factory=list)  # human-readable changes made on load


def detect_format(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in SUPPORTED_FORMATS:
        raise LoadError(f"Unsupported file type '.{ext}'. Use CSV, Excel or Parquet.")
    return "csv" if ext in ("tsv", "txt") else ext


def _detect_encoding(head: bytes) -> str:
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        head.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    from charset_normalizer import from_bytes

    best = from_bytes(head).best()
    return best.encoding if best else "latin-1"


def _detect_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _read_csv(path: Path, options: dict) -> tuple[pd.DataFrame, dict]:
    with path.open("rb") as fh:
        head = fh.read(1024 * 1024)
    encoding = options.get("encoding") or _detect_encoding(head)
    sample = head.decode(encoding, errors="replace")
    # Trim to whole lines so the sniffer doesn't see a cut-off row.
    sample = sample[: sample.rfind("\n")] if "\n" in sample else sample
    delimiter = options.get("delimiter") or _detect_delimiter(sample[:64_000])
    header_row = int(options.get("header_row", 0))
    try:
        df = pd.read_csv(
            path,
            encoding=encoding,
            sep=delimiter,
            header=header_row,
            low_memory=False,
            on_bad_lines="warn",
            skipinitialspace=True,
        )
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise LoadError(f"Could not parse CSV: {exc}") from exc
    return df, {"encoding": encoding, "delimiter": delimiter, "header_row": header_row}


def _read_excel(path: Path, fmt: str, options: dict) -> tuple[pd.DataFrame, dict]:
    engine = "openpyxl" if fmt == "xlsx" else "xlrd"
    header_row = int(options.get("header_row", 0))
    try:
        book = pd.ExcelFile(path, engine=engine)
        sheet = options.get("sheet_name") or book.sheet_names[0]
        if sheet not in book.sheet_names:
            raise LoadError(f"Sheet '{sheet}' not found. Sheets: {', '.join(book.sheet_names)}")
        df = book.parse(sheet, header=header_row)
    except LoadError:
        raise
    except Exception as exc:  # noqa: BLE001 - any reader failure is a user-facing load error
        raise LoadError(f"Could not read Excel file: {exc}") from exc
    return df, {"sheet_name": sheet, "sheet_names": book.sheet_names, "header_row": header_row}


def clean_column_names(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    notes: list[str] = []
    names: list[str] = []
    seen: dict[str, int] = {}
    for i, col in enumerate(df.columns):
        name = re.sub(r"\s+", " ", str(col)).strip()
        if not name or name.lower().startswith("unnamed:"):
            name = f"column_{i + 1}"
        if name in seen:
            seen[name] += 1
            new = f"{name}_{seen[name]}"
            notes.append(f"Renamed duplicate column '{name}' to '{new}'")
            name = new
        else:
            seen[name] = 1
        names.append(name)
    out = df.copy()
    out.columns = names
    return out, notes


_NUMERIC_JUNK = re.compile(r"^\s*[$€£₹]?\s*|\s*$")


def _lossless_numeric(series: pd.Series) -> pd.Series | None:
    """Convert text to numbers only if *every* non-null value parses."""
    non_null = series.dropna()
    if non_null.empty:
        return None
    text = non_null.astype(str).str.strip()
    if text.str.contains(r"[A-Za-z%]", regex=True).any():
        return None
    cleaned = text.str.replace(_NUMERIC_JUNK, "", regex=True)
    # Thousands separators only in valid positions (1,234,567.89).
    has_commas = cleaned.str.contains(",", regex=False)
    if has_commas.any():
        valid = cleaned[has_commas].str.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?")
        if not valid.all():
            return None
        cleaned = cleaned.str.replace(",", "", regex=False)
    converted = pd.to_numeric(cleaned, errors="coerce")
    if converted.isna().any():
        return None
    result = pd.Series(np.nan, index=series.index, dtype="float64")
    result.loc[converted.index] = converted.astype("float64")
    if (result.dropna() % 1 == 0).all() and series.notna().all():
        return result.astype("int64")
    return result


def normalize_dtypes(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Make the frame Parquet-safe and convert clearly-numeric text."""
    notes: list[str] = []
    out = df.copy()
    for col in out.columns:
        s = out[col]
        if s.dtype == object:
            converted = _lossless_numeric(s)
            if converted is not None:
                out[col] = converted
                notes.append(f"Converted '{col}' from text to numbers")
                continue
            # Mixed Python types (e.g. ints and strings) break Parquet; store as text.
            kinds = {type(v) for v in s.dropna().head(10_000)}
            if len(kinds) > 1 or (kinds and kinds != {str}):
                out[col] = s.map(lambda v: v if pd.isna(v) else str(v)).astype(object)
    return out, notes


def load_file(path: str | Path, fmt: str, options: dict | None = None) -> LoadResult:
    path = Path(path)
    options = dict(options or {})
    if fmt == "csv":
        df, used = _read_csv(path, options)
    elif fmt in ("xlsx", "xls"):
        df, used = _read_excel(path, fmt, options)
    elif fmt == "parquet":
        try:
            df, used = pd.read_parquet(path), {}
        except Exception as exc:  # noqa: BLE001
            raise LoadError(f"Could not read Parquet file: {exc}") from exc
    else:
        raise LoadError(f"Unsupported format: {fmt}")

    notes: list[str] = []
    before = len(df)
    df = df.dropna(how="all")
    if len(df) < before:
        notes.append(f"Removed {before - len(df)} completely empty rows")
    empty_cols = [c for c in df.columns if df[c].isna().all() and str(c).startswith("Unnamed")]
    if empty_cols:
        df = df.drop(columns=empty_cols)
        notes.append(f"Removed {len(empty_cols)} empty unnamed columns")
    df, n = clean_column_names(df)
    notes += n
    df, n = normalize_dtypes(df)
    notes += n
    df = df.reset_index(drop=True)
    if df.shape[1] == 0:
        raise LoadError("The file has no columns.")
    return LoadResult(df=df, options=used, notes=notes)


def read_any(data: bytes, filename: str) -> pd.DataFrame:
    """Convenience for tests and small in-memory files."""
    import tempfile

    fmt = detect_format(filename)
    with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as tmp:
        tmp.write(data)
    try:
        return load_file(tmp.name, fmt).df
    finally:
        Path(tmp.name).unlink(missing_ok=True)


__all__ = ["SUPPORTED_FORMATS", "LoadError", "LoadResult", "detect_format", "load_file", "read_any"]
