"""Dataset profiling: semantic types, per-column stats and quality alerts.

Ported from legacy/analytics.py (missingness, cardinality warnings, numeric-as-text detection,
correlations) and extended with semantic types and actionable suggestions. Every value
returned is JSON-safe (plain Python types) so it can go straight into JSONB.
"""

from __future__ import annotations

import math
import re
import warnings
from typing import Any

import numpy as np
import pandas as pd

SEMANTIC_TYPES = (
    "numeric",
    "boolean",
    "datetime",
    "nominal",
    "ordinal",
    "text",
    "id",
    "constant",
    "empty",
)

_ID_NAME_CI = re.compile(r"(^id$|[_ ]id$|^id_|uuid|guid|^key$|identifier)", re.I)
_ID_NAME_CAMEL = re.compile(r"[a-z]I[dD]$")  # PassengerId, userID


def _id_name(name: str) -> bool:
    return bool(_ID_NAME_CI.search(name) or _ID_NAME_CAMEL.search(name))


_BOOL_TOKENS = {"true", "false", "yes", "no", "y", "n", "t", "f", "0", "1"}


# --------------------------------------------------------------------------- helpers
def to_jsonable(v: Any) -> Any:
    """Convert numpy/pandas scalars to plain Python; NaN/inf become None."""
    if v is None:
        return None
    if isinstance(v, dict):
        return {str(k): to_jsonable(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [to_jsonable(x) for x in v]
    if isinstance(v, np.bool_ | bool):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating | float):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(v, pd.Timestamp | np.datetime64):
        ts = pd.Timestamp(v)
        return None if pd.isna(ts) else ts.isoformat()
    if isinstance(v, pd.Timedelta):
        return str(v)
    if v is pd.NaT:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _round(x: Any, n: int = 6) -> Any:
    x = to_jsonable(x)
    return round(x, n) if isinstance(x, float) else x


def _looks_datetime(s: pd.Series) -> bool:
    sample = s.dropna().astype(str).head(500)
    if sample.empty or not sample.str.contains(r"\d", regex=True).all():
        return False
    if not sample.str.contains(r"[-/:.]|\d{8}", regex=True).mean() > 0.9:
        return False
    # Pure numbers (e.g. 2021.5) are not dates.
    if pd.to_numeric(sample, errors="coerce").notna().mean() > 0.5:
        return False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    return parsed.notna().mean() >= 0.95


def infer_semantic_type(s: pd.Series, name: str = "") -> str:
    n = len(s)
    non_null = s.dropna()
    if non_null.empty:
        return "empty"
    nunique = non_null.nunique()
    if nunique <= 1:
        return "constant"
    if pd.api.types.is_bool_dtype(s):
        return "boolean"
    if nunique == 2 and {str(v).strip().lower() for v in non_null.unique()} <= _BOOL_TOKENS:
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    unique_ratio = nunique / max(len(non_null), 1)
    if pd.api.types.is_numeric_dtype(s):
        if pd.api.types.is_integer_dtype(s) and unique_ratio > 0.98 and n > 50 and _id_name(name):
            return "id"
        return "numeric"
    # text-like
    as_str = non_null.astype(str)
    if _looks_datetime(as_str):
        return "datetime"
    avg_len = as_str.str.len().mean()
    if numeric_as_text_ratio(non_null) >= 0.8:
        return "nominal"  # numbers stored as text; flagged NUMERIC_AS_TEXT for conversion
    if unique_ratio > 0.98 and n > 50 and (avg_len < 40 or _id_name(name)):
        return "id"
    words = as_str.head(2000).str.split().str.len().mean()
    if avg_len > 40 or (words and words > 5 and unique_ratio > 0.5):
        return "text"
    return "nominal"


def _histogram(values: pd.Series, bins: int = 20) -> dict:
    v = values.dropna().astype("float64")
    v = v[np.isfinite(v)]
    if v.empty:
        return {"edges": [], "counts": []}
    if v.min() == v.max():
        return {"edges": [float(v.min()), float(v.max())], "counts": [int(len(v))]}
    counts, edges = np.histogram(v, bins=bins)
    return {"edges": [float(e) for e in edges], "counts": [int(c) for c in counts]}


def _top_values(s: pd.Series, k: int = 10) -> list[dict]:
    vc = s.dropna().astype(str).value_counts().head(k)
    return [{"value": str(idx), "count": int(cnt)} for idx, cnt in vc.items()]


def iqr_bounds(s: pd.Series, k: float = 1.5) -> tuple[float, float]:
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    return float(q1 - k * iqr), float(q3 + k * iqr)


def numeric_as_text_ratio(s: pd.Series) -> float:
    """Share of non-null text values that become numbers after removing $ , % and spaces."""
    text = s.dropna().astype(str).str.strip()
    if text.empty:
        return 0.0
    cleaned = text.str.replace(r"[$€£₹,%\s]", "", regex=True)
    return float(pd.to_numeric(cleaned, errors="coerce").notna().mean())


# --------------------------------------------------------------------------- column stats
def column_stats(s: pd.Series, semantic_type: str) -> dict:
    n = len(s)
    non_null = s.dropna()
    stats: dict[str, Any] = {
        "count": int(non_null.size),
        "missing_pct": _round(100 * (n - non_null.size) / n if n else 0.0, 3),
        "unique_ratio": _round(non_null.nunique() / non_null.size if non_null.size else 0.0, 4),
        "sample_values": [to_jsonable(v) for v in non_null.head(5).tolist()],
    }
    if semantic_type in ("numeric",) and pd.api.types.is_numeric_dtype(s):
        x = non_null.astype("float64")
        lo, hi = iqr_bounds(x)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            stats.update(
                mean=_round(x.mean()),
                std=_round(x.std()),
                min=_round(x.min()),
                q1=_round(x.quantile(0.25)),
                median=_round(x.median()),
                q3=_round(x.quantile(0.75)),
                max=_round(x.max()),
                skew=_round(x.skew()),
                kurtosis=_round(x.kurt()),
                zeros=int((x == 0).sum()),
                negatives=int((x < 0).sum()),
                outliers_iqr=int(((x < lo) | (x > hi)).sum()),
                is_integer=bool(pd.api.types.is_integer_dtype(s) or (x % 1 == 0).all()),
                histogram=_histogram(x),
            )
    elif semantic_type == "datetime":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dt = (
                non_null
                if pd.api.types.is_datetime64_any_dtype(non_null)
                else pd.to_datetime(non_null.astype(str), errors="coerce", format="mixed")
            )
        dt = dt.dropna()
        if not dt.empty:
            stats.update(
                min=to_jsonable(dt.min()),
                max=to_jsonable(dt.max()),
                parse_rate=_round(dt.size / max(non_null.size, 1), 4),
            )
    else:
        as_str = non_null.astype(str)
        stats["top_values"] = _top_values(s)
        if semantic_type in ("text", "nominal", "id"):
            lengths = as_str.str.len()
            stats.update(
                avg_length=_round(lengths.mean(), 2),
                max_length=int(lengths.max()) if not lengths.empty else 0,
            )
        if not pd.api.types.is_numeric_dtype(s):
            stats["numeric_text_ratio"] = _round(numeric_as_text_ratio(s), 4)
    return stats


# --------------------------------------------------------------------------- alerts
def _alert(
    code: str,
    severity: str,
    message: str,
    column: str | None = None,
    suggestion: dict | None = None,
) -> dict:
    return {
        "code": code,
        "severity": severity,
        "column": column,
        "message": message,
        "suggestion": suggestion,
    }


def column_alerts(name: str, sem: str, stats: dict, n_rows: int) -> list[dict]:
    alerts: list[dict] = []
    missing = stats.get("missing_pct") or 0
    if sem == "empty":
        alerts.append(
            _alert(
                "EMPTY_COLUMN",
                "high",
                f"'{name}' has no values.",
                name,
                {"step_type": "drop_columns", "params": {"columns": [name]}},
            )
        )
        return alerts
    if missing >= 60:
        alerts.append(
            _alert(
                "HIGH_MISSING",
                "high",
                f"'{name}' is {missing:.1f}% missing.",
                name,
                {"step_type": "drop_columns", "params": {"columns": [name]}},
            )
        )
    elif missing >= 5:
        strategy = "median" if sem == "numeric" else "most_frequent"
        alerts.append(
            _alert(
                "MISSING_VALUES",
                "medium" if missing >= 20 else "low",
                f"'{name}' is {missing:.1f}% missing.",
                name,
                {"step_type": "impute", "params": {"columns": [name], "strategy": strategy}},
            )
        )
    if sem == "constant":
        alerts.append(
            _alert(
                "CONSTANT",
                "medium",
                f"'{name}' has a single value; it carries no information for a model.",
                name,
                {"step_type": "drop_columns", "params": {"columns": [name]}},
            )
        )
    if sem == "id":
        alerts.append(
            _alert(
                "ID_LIKE",
                "medium",
                f"'{name}' looks like an identifier (almost "
                "every value is unique). Exclude it from model features.",
                name,
                {"step_type": "drop_columns", "params": {"columns": [name]}},
            )
        )
    if sem == "nominal":
        uniq = stats.get("unique_ratio", 0) * stats.get("count", 0)
        if uniq > 50:
            alerts.append(
                _alert(
                    "HIGH_CARDINALITY",
                    "low",
                    f"'{name}' has {int(uniq)} "
                    "categories; one-hot encoding would create many columns.",
                    name,
                    {
                        "step_type": "rare_group",
                        "params": {"columns": [name], "min_frequency": 0.01},
                    },
                )
            )
        if (stats.get("numeric_text_ratio") or 0) >= 0.8:
            alerts.append(
                _alert(
                    "NUMERIC_AS_TEXT",
                    "medium",
                    f"'{name}' is stored as text but most values are numbers.",
                    name,
                    {"step_type": "change_type", "params": {"columns": [name], "to": "numeric"}},
                )
            )
    if sem == "datetime" and stats.get("parse_rate") is not None:
        alerts.append(
            _alert(
                "DATETIME_AS_TEXT",
                "low",
                f"'{name}' contains dates stored as text.",
                name,
                {"step_type": "change_type", "params": {"columns": [name], "to": "datetime"}},
            )
        )
    if sem == "numeric":
        skew = stats.get("skew")
        if skew is not None and abs(skew) > 2:
            alerts.append(
                _alert(
                    "SKEWED",
                    "low",
                    f"'{name}' is highly skewed (skew {skew:.1f}).",
                    name,
                    {
                        "step_type": "numeric_transform",
                        "params": {"columns": [name], "method": "yeo_johnson"},
                    },
                )
            )
        outl = stats.get("outliers_iqr") or 0
        if stats.get("count") and outl / stats["count"] > 0.05:
            alerts.append(
                _alert(
                    "OUTLIERS",
                    "low",
                    f"'{name}' has {outl} values outside 1.5×IQR.",
                    name,
                    {
                        "step_type": "outliers",
                        "params": {"columns": [name], "method": "iqr", "action": "clip"},
                    },
                )
            )
    return alerts


# --------------------------------------------------------------------------- dataset profile
def profile(df: pd.DataFrame, target: str | None = None) -> dict:
    """Full profile used to fill `column_profiles` and `dataset_versions.profile`."""
    n_rows, n_cols = df.shape
    columns: list[dict] = []
    alerts: list[dict] = []
    for pos, name in enumerate(df.columns):
        s = df[name]
        sem = infer_semantic_type(s, str(name))
        stats = column_stats(s, sem)
        columns.append(
            {
                "name": str(name),
                "position": pos,
                "dtype": str(s.dtype),
                "semantic_type": sem,
                "missing_count": int(s.isna().sum()),
                "unique_count": int(s.nunique(dropna=True)),
                "stats": stats,
            }
        )
        alerts += column_alerts(str(name), sem, stats, n_rows)

    try:
        dup = int(df.duplicated().sum()) if n_rows else 0
    except TypeError:  # unhashable cells
        dup = 0
    if dup:
        alerts.insert(
            0,
            _alert(
                "DUPLICATE_ROWS",
                "medium" if dup / n_rows > 0.01 else "low",
                f"{dup} duplicate rows ({100 * dup / n_rows:.1f}%).",
                None,
                {"step_type": "drop_duplicates", "params": {}},
            ),
        )
    if target and target in df.columns:
        alerts += target_alerts(df, target)

    missing_cells = int(df.isna().sum().sum())
    total = n_rows * n_cols
    type_counts: dict[str, int] = {}
    for c in columns:
        type_counts[c["semantic_type"]] = type_counts.get(c["semantic_type"], 0) + 1
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda a: severity_rank.get(a["severity"], 3))
    summary = {
        "row_count": n_rows,
        "column_count": n_cols,
        "missing_cells": missing_cells,
        "missing_pct": _round(100 * missing_cells / total if total else 0.0, 3),
        "duplicate_rows": dup,
        "duplicate_pct": _round(100 * dup / n_rows if n_rows else 0.0, 3),
        "memory_mb": _round(df.memory_usage(deep=True).sum() / 1024 / 1024, 3),
        "type_counts": type_counts,
        "completeness_score": _round(100 * (1 - missing_cells / total) if total else 100.0, 2),
    }
    return {"summary": summary, "columns": columns, "alerts": alerts}


def target_alerts(df: pd.DataFrame, target: str) -> list[dict]:
    s = df[target]
    out: list[dict] = []
    if s.isna().any():
        out.append(
            _alert(
                "TARGET_MISSING",
                "high",
                f"Target '{target}' has {int(s.isna().sum())} "
                "missing values; those rows cannot be used for training.",
                target,
                {"step_type": "drop_missing_rows", "params": {"columns": [target]}},
            )
        )
    vc = s.value_counts(normalize=True)
    if 1 < len(vc) <= 50 and vc.iloc[-1] < 0.2:
        out.append(
            _alert(
                "CLASS_IMBALANCE",
                "medium" if vc.iloc[-1] < 0.1 else "low",
                f"Target '{target}' is imbalanced: smallest class is "
                f"{100 * vc.iloc[-1]:.1f}% of rows.",
                target,
                {"step_type": "smote", "params": {}},
            )
        )
    return out


def correlations(df: pd.DataFrame, method: str = "pearson", max_cols: int = 60) -> dict:
    num = df.select_dtypes(include=[np.number])
    num = num.loc[:, num.nunique() > 1].iloc[:, :max_cols]
    if num.shape[1] < 2:
        return {"columns": list(num.columns), "matrix": [], "top_pairs": []}
    corr = num.corr(method=method)
    cols = [str(c) for c in corr.columns]
    pairs = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            v = corr.iat[i, j]
            if not pd.isna(v):
                pairs.append({"a": cols[i], "b": cols[j], "r": round(float(v), 4)})
    pairs.sort(key=lambda p: abs(p["r"]), reverse=True)
    return {
        "columns": cols,
        "matrix": to_jsonable(corr.round(4).values.tolist()),
        "top_pairs": pairs[:15],
    }


def schema_snapshot(prof: dict) -> list[dict]:
    return [
        {"name": c["name"], "dtype": c["dtype"], "semantic_type": c["semantic_type"]}
        for c in prof["columns"]
    ]
