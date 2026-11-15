"""Cleaning, column and row transforms. Ported from legacy/preprocessing.py where it applies
(missing values, duplicates, outliers), now with fit/transform separation."""

from __future__ import annotations

import re
import warnings

import numpy as np
import pandas as pd

from .base import (
    SPLIT_COL,
    Issue,
    Param,
    StepError,
    Transform,
    as_float,
    numeric_cols,
)
from .registry import register

COLS = Param("columns", "columns", "Columns", required=True)


def _r(v) -> str:
    return repr(v)


# =============================================================== columns
@register
class DropColumns(Transform):
    step_type = "drop_columns"
    label = "Drop columns"
    category = "columns"
    params = [COLS]
    explain_text = "Removes columns you do not want to keep, such as identifiers or leaks."

    def extra_validate(self, p, ctx):
        if ctx.target and ctx.target in self.columns(p, ctx):
            return [Issue("warning", f"You are dropping the target column '{ctx.target}'")]
        return []

    def transform(self, df, params, state, ctx):
        cols = [c for c in self.columns(params, ctx) if c in df.columns]
        return df.drop(columns=cols)

    def code(self, params, state):
        return f"df = df.drop(columns={_r(params.get('columns'))})"


@register
class KeepColumns(Transform):
    step_type = "keep_columns"
    label = "Keep only columns"
    category = "columns"
    params = [COLS]
    explain_text = "Keeps the listed columns (and the split marker) and drops everything else."

    def transform(self, df, params, state, ctx):
        keep = [c for c in self.columns(params, ctx) if c in df.columns]
        if SPLIT_COL in df.columns:
            keep.append(SPLIT_COL)
        return df[keep]

    def code(self, params, state):
        return f"df = df[{_r(params.get('columns'))}]"


@register
class RenameColumns(Transform):
    step_type = "rename_columns"
    label = "Rename columns"
    category = "columns"
    params = [Param("mapping", "mapping", "Old name → new name", required=True)]
    explain_text = "Gives columns clearer names. Downstream steps must use the new names."

    def extra_validate(self, p, ctx):
        mapping = p.get("mapping") or {}
        issues = [
            Issue("error", f"Unknown column '{k}'", "mapping")
            for k in mapping
            if k not in ctx.columns
        ]
        new_names = [v for v in mapping.values()]
        remaining = [c for c in ctx.columns if c not in mapping]
        dup = {n for n in new_names if new_names.count(n) > 1 or n in remaining}
        if dup:
            issues.append(Issue("error", f"Duplicate column names after rename: {sorted(dup)}"))
        if any(not str(v).strip() for v in new_names):
            issues.append(Issue("error", "New names cannot be empty"))
        return issues

    def transform(self, df, params, state, ctx):
        return df.rename(columns={k: str(v).strip() for k, v in params["mapping"].items()})

    def describe(self, params):
        m = params.get("mapping") or {}
        return "Rename " + ", ".join(f"{k} → {v}" for k, v in list(m.items())[:3])

    def code(self, params, state):
        return f"df = df.rename(columns={_r(params.get('mapping'))})"


TYPES = ["numeric", "integer", "text", "datetime", "boolean", "category"]
_BOOL_MAP = {
    "true": True,
    "false": False,
    "yes": True,
    "no": False,
    "y": True,
    "n": False,
    "t": True,
    "f": False,
    "1": True,
    "0": False,
    "1.0": True,
    "0.0": False,
}


def to_numeric_text(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s
    cleaned = s.astype("string").str.strip().str.replace(r"[$€£₹,%\s]", "", regex=True)
    neg = cleaned.str.match(r"^\(.*\)$", na=False)  # accounting negatives: (123)
    cleaned = cleaned.str.replace(r"^\((.*)\)$", r"\1", regex=True)
    out = pd.to_numeric(cleaned, errors="coerce")
    return out.where(~neg, -out)


@register
class ChangeType(Transform):
    step_type = "change_type"
    label = "Change type"
    category = "clean"
    params = [
        COLS,
        Param("to", "select", "New type", default="numeric", options=TYPES),
        Param(
            "datetime_format",
            "text",
            "Date format (optional)",
            help="e.g. %d/%m/%Y. Leave empty to detect.",
        ),
    ]
    explain_text = (
        "Converts columns to another type. Values that cannot be converted become "
        "empty, and the preview shows how many."
    )

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        out = df.copy()
        for c in self.columns(p, ctx):
            s = out[c]
            to = p["to"]
            if to == "numeric":
                out[c] = to_numeric_text(s).astype("float64")
            elif to == "integer":
                out[c] = to_numeric_text(s).round().astype("Int64")
            elif to == "text":
                out[c] = s.astype("string").astype(object).where(s.notna(), None)
            elif to == "datetime":
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    fmt = p.get("datetime_format") or None
                    out[c] = pd.to_datetime(s, errors="coerce", format=fmt or "mixed")
            elif to == "boolean":
                mapped = s.astype("string").str.strip().str.lower().map(_BOOL_MAP)
                out[c] = mapped.astype("boolean")
            elif to == "category":
                out[c] = s.astype("string").astype(object).where(s.notna(), None)
        return out

    def describe(self, params):
        return f"{super().describe(params)} → {params.get('to', 'numeric')}"

    def code(self, params, state):
        to, cols = params.get("to", "numeric"), params.get("columns")
        if to in ("numeric", "integer"):
            return (
                f"for c in {_r(cols)}:\n    df[c] = pd.to_numeric(df[c].astype(str)"
                f".str.replace(r'[$€£₹,%\\s]', '', regex=True), errors='coerce')"
            )
        if to == "datetime":
            return f"for c in {_r(cols)}:\n    df[c] = pd.to_datetime(df[c], errors='coerce')"
        return f"for c in {_r(cols)}:\n    df[c] = df[c].astype('string')"


@register
class TrimText(Transform):
    step_type = "trim_text"
    label = "Clean text"
    category = "clean"
    params = [
        Param(
            "columns", "columns", "Columns", default=["@categorical"], column_filter="categorical"
        ),
        Param(
            "case",
            "select",
            "Letter case",
            default="none",
            options=["none", "lower", "upper", "title"],
        ),
        Param("collapse_spaces", "boolean", "Collapse repeated spaces", default=True),
        Param("empty_to_null", "boolean", "Treat empty strings as missing", default=True),
    ]
    explain_text = (
        "Trims spaces and normalises case so ' Paris', 'paris' and 'PARIS' become one category."
    )

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        out = df.copy()
        for c in self.columns(p, ctx):
            if c not in out.columns or pd.api.types.is_numeric_dtype(out[c]):
                continue
            mask = out[c].notna()
            s = out.loc[mask, c].astype(str).str.strip()
            if p["collapse_spaces"]:
                s = s.str.replace(r"\s+", " ", regex=True)
            if p["case"] != "none":
                s = getattr(s.str, p["case"])()
            out[c] = out[c].astype(object)
            out.loc[mask, c] = s
            if p["empty_to_null"]:
                out.loc[out[c] == "", c] = None
        return out

    def code(self, params, state):
        return (
            f"for c in {_r(params.get('columns'))}:\n"
            f"    df[c] = df[c].str.strip().str.replace(r'\\s+', ' ', regex=True)"
        )


@register
class ReplaceValues(Transform):
    step_type = "replace_values"
    label = "Replace values"
    category = "clean"
    params = [
        COLS,
        Param(
            "mapping",
            "mapping",
            "Find → replace with",
            required=True,
            help="Use an empty replacement to mark values as missing.",
        ),
        Param("match", "select", "Match", default="exact", options=["exact", "contains", "regex"]),
    ]
    explain_text = "Fixes typos and recodes values, e.g. 'N/A' → missing or 'M' → 'Male'."

    def extra_validate(self, p, ctx):
        if p.get("match") == "regex":
            for k in p.get("mapping") or {}:
                try:
                    re.compile(k)
                except re.error as e:
                    return [Issue("error", f"Invalid pattern '{k}': {e}", "mapping")]
        return []

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        out = df.copy()
        mapping = {str(k): (None if v in ("", None) else v) for k, v in p["mapping"].items()}
        for c in self.columns(p, ctx):
            s = out[c]
            if p["match"] == "exact":
                as_str = s.astype(str).where(s.notna(), None)
                for k, v in mapping.items():
                    hit = as_str == k
                    if hit.any():
                        out[c] = out[c].astype(object)
                        out.loc[hit, c] = v
            else:
                as_str = s.astype("string")
                for k, v in mapping.items():
                    pat = k if p["match"] == "regex" else re.escape(k)
                    if v is None:
                        out.loc[as_str.str.contains(pat, regex=True, na=False), c] = None
                    else:
                        as_str = as_str.str.replace(pat, str(v), regex=True)
                        out[c] = as_str.astype(object).where(as_str.notna(), None)
        return out

    def code(self, params, state):
        return (
            f"df[{_r(params.get('columns'))}] = df[{_r(params.get('columns'))}].replace("
            f"{_r(params.get('mapping'))})"
        )


# =============================================================== rows
@register
class DropDuplicates(Transform):
    step_type = "drop_duplicates"
    label = "Remove duplicate rows"
    category = "rows"
    changes_rows = True
    params = [
        Param(
            "columns", "columns", "Compare only these columns", help="Empty = compare whole rows"
        ),
        Param("keep", "select", "Keep", default="first", options=["first", "last", "none"]),
    ]
    explain_text = "Removes repeated rows, which inflate counts and can leak between splits."

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        subset = self.columns(p, ctx) or [c for c in df.columns if c != SPLIT_COL]
        keep = False if p["keep"] == "none" else p["keep"]
        return df.drop_duplicates(subset=subset, keep=keep).reset_index(drop=True)

    def describe(self, params):
        cols = params.get("columns")
        return "Remove duplicate rows" + (f" (by {', '.join(cols[:3])})" if cols else "")

    def code(self, params, state):
        return f"df = df.drop_duplicates(subset={_r(params.get('columns') or None)})"


@register
class DropMissingRows(Transform):
    step_type = "drop_missing_rows"
    label = "Drop rows with missing values"
    category = "rows"
    changes_rows = True
    params = [
        Param("columns", "columns", "In columns", help="Empty = any column"),
        Param("how", "select", "Drop when", default="any", options=["any", "all"]),
    ]
    explain_text = "Removes rows that are missing values in the chosen columns."
    warnings_text = ["Dropping rows can bias the data if values are not missing at random."]

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        subset = self.columns(p, ctx) or [c for c in df.columns if c != SPLIT_COL]
        return df.dropna(subset=subset, how=p["how"]).reset_index(drop=True)

    def code(self, params, state):
        return (
            f"df = df.dropna(subset={_r(params.get('columns') or None)}, "
            f"how={_r(params.get('how', 'any'))})"
        )


FILTER_OPS = [
    "==",
    "!=",
    ">",
    ">=",
    "<",
    "<=",
    "contains",
    "not_contains",
    "is_missing",
    "not_missing",
    "in",
]


@register
class FilterRows(Transform):
    step_type = "filter_rows"
    label = "Filter rows"
    category = "rows"
    changes_rows = True
    params = [
        Param("column", "column", "Column", required=True),
        Param("op", "select", "Condition", default="==", options=FILTER_OPS),
        Param("value", "text", "Value"),
        Param("keep", "select", "Matching rows are", default="kept", options=["kept", "removed"]),
    ]
    explain_text = "Keeps or removes rows matching a condition, e.g. age ≥ 18."

    def _mask(self, df, p):
        s, op, v = df[p["column"]], p["op"], p.get("value")
        if op == "is_missing":
            return s.isna()
        if op == "not_missing":
            return s.notna()
        if op in ("contains", "not_contains"):
            m = s.astype("string").str.contains(str(v), case=False, regex=False, na=False)
            return m if op == "contains" else ~m
        if op == "in":
            vals = [x.strip() for x in str(v).split(",")]
            return s.astype(str).isin(vals)
        if pd.api.types.is_numeric_dtype(s):
            try:
                v = float(v)
            except (TypeError, ValueError) as exc:
                raise StepError(f"'{v}' is not a number") from exc
        elif pd.api.types.is_datetime64_any_dtype(s):
            v = pd.Timestamp(v)
        else:
            s = s.astype(str)
            v = str(v)
        return {"==": s == v, "!=": s != v, ">": s > v, ">=": s >= v, "<": s < v, "<=": s <= v}[
            op
        ].fillna(False)

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        m = self._mask(df, p).astype(bool)
        return df[m if p["keep"] == "kept" else ~m].reset_index(drop=True)

    def describe(self, params):
        verb = "Keep" if params.get("keep", "kept") == "kept" else "Remove"
        return (
            f"{verb} rows where {params.get('column')} {params.get('op', '==')} "
            f"{params.get('value', '')}".strip()
        )

    def code(self, params, state):
        p = self.defaults(params)
        c, op, v = _r(p.get("column")), p.get("op"), p.get("value")
        if op == "is_missing":
            mask = f"df[{c}].isna()"
        elif op == "not_missing":
            mask = f"df[{c}].notna()"
        elif op in ("contains", "not_contains"):
            neg = "~" if op == "not_contains" else ""
            mask = f"{neg}df[{c}].astype(str).str.contains({_r(str(v))}, case=False, regex=False)"
        elif op == "in":
            mask = f"df[{c}].astype(str).isin({_r([x.strip() for x in str(v).split(',')])})"
        else:
            try:
                lit = repr(float(v))
            except (TypeError, ValueError):
                lit = repr(str(v))
            mask = f"(df[{c}] {op} {lit})"
        keep = mask if p.get("keep", "kept") == "kept" else f"~({mask})"
        return f"df = df[{keep}].reset_index(drop=True)"


# =============================================================== post-split cleaning
IMPUTE = ["mean", "median", "most_frequent", "constant", "ffill", "bfill", "interpolate"]


@register
class Impute(Transform):
    step_type = "impute"
    label = "Fill missing values"
    category = "clean"
    phase = "post_split"
    requires_fit = True
    params = [
        COLS,
        Param("strategy", "select", "Fill with", default="median", options=IMPUTE),
        Param("fill_value", "text", "Constant value"),
        Param("add_indicator", "boolean", "Add a 'was missing' flag column", default=False),
    ]
    explain_text = (
        "Fills gaps using statistics learned from the training rows only, so the "
        "test set never influences the fill value."
    )
    warnings_text = ["Mean is sensitive to outliers; median is a safer default for skewed data."]

    def extra_validate(self, p, ctx):
        issues = []
        if p["strategy"] in ("mean", "median", "interpolate"):
            bad = [c for c in self.columns(p, ctx) if ctx.columns.get(c) != "numeric"]
            if bad:
                issues.append(
                    Issue(
                        "error",
                        f"{p['strategy']} needs numeric columns; not numeric: {', '.join(bad)}",
                        "columns",
                    )
                )
        if p["strategy"] == "constant" and p.get("fill_value") in (None, ""):
            issues.append(Issue("error", "Enter the constant value", "fill_value"))
        if p["strategy"] in ("ffill", "bfill", "interpolate"):
            issues.append(
                Issue("warning", "Forward/back fill only makes sense if rows are in time order")
            )
        return issues

    def fit(self, df, params, ctx):
        p = self.defaults(params)
        fills = {}
        for c in self.columns(p, ctx):
            s = df[c]
            if p["strategy"] == "mean":
                fills[c] = float(as_float(s).mean()) if s.notna().any() else 0.0
            elif p["strategy"] == "median":
                fills[c] = float(as_float(s).median()) if s.notna().any() else 0.0
            elif p["strategy"] == "most_frequent":
                mode = s.mode(dropna=True)
                v = mode.iloc[0] if len(mode) else None
                fills[c] = v.item() if hasattr(v, "item") else v
            elif p["strategy"] == "constant":
                v = p.get("fill_value")
                if pd.api.types.is_numeric_dtype(s):
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        pass
                fills[c] = v
        return {"fills": fills}

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        out = df.copy()
        for c in self.columns(p, ctx):
            if p["add_indicator"]:
                out[f"{c}_was_missing"] = out[c].isna().astype("int8")
            if p["strategy"] == "ffill":
                out[c] = out[c].ffill()
            elif p["strategy"] == "bfill":
                out[c] = out[c].bfill()
            elif p["strategy"] == "interpolate":
                out[c] = as_float(out[c]).interpolate(limit_direction="both")
            else:
                fill = state.get("fills", {}).get(c)
                if fill is not None:
                    if (
                        pd.api.types.is_integer_dtype(out[c])
                        and isinstance(fill, float)
                        and not fill.is_integer()
                    ):
                        out[c] = out[c].astype("float64")
                    out[c] = out[c].fillna(fill)
        return out

    def describe(self, params):
        return f"{super().describe(params)} ({params.get('strategy', 'median')})"

    def code(self, params, state):
        fills = state.get("fills", {})
        if fills:
            return f"df = df.fillna({_r(fills)})  # values learned on the training rows"
        return f"df[{_r(params.get('columns'))}] = df[{_r(params.get('columns'))}].ffill()"


@register
class Outliers(Transform):
    step_type = "outliers"
    label = "Handle outliers"
    category = "clean"
    phase = "post_split"
    requires_fit = True
    changes_rows = True
    params = [
        Param("columns", "columns", "Columns", required=True, column_filter="numeric"),
        Param(
            "method",
            "select",
            "Detect with",
            default="iqr",
            options=["iqr", "zscore", "percentile"],
        ),
        Param(
            "threshold",
            "number",
            "Threshold",
            default=1.5,
            min=0,
            help="IQR multiplier (1.5), z-score (3) or percentile (1 = 1st/99th)",
        ),
        Param("action", "select", "Then", default="clip", options=["clip", "remove", "flag"]),
    ]
    explain_text = (
        "Caps (clip) or removes extreme values. Bounds are learned on training rows; "
        "'remove' only drops training rows so the test set stays realistic."
    )

    def extra_validate(self, p, ctx):
        bad = [c for c in self.columns(p, ctx) if ctx.columns.get(c) != "numeric"]
        return [Issue("error", f"Not numeric: {', '.join(bad)}", "columns")] if bad else []

    def fit(self, df, params, ctx):
        p = self.defaults(params)
        k = float(p["threshold"])
        bounds = {}
        for c in numeric_cols(df, self.columns(p, ctx)):
            s = as_float(df[c]).dropna()
            if s.empty:
                continue
            if p["method"] == "iqr":
                q1, q3 = s.quantile(0.25), s.quantile(0.75)
                lo, hi = q1 - k * (q3 - q1), q3 + k * (q3 - q1)
            elif p["method"] == "zscore":
                lo, hi = s.mean() - k * s.std(), s.mean() + k * s.std()
            else:
                pct = min(max(k, 0.0), 49.0)
                lo, hi = s.quantile(pct / 100), s.quantile(1 - pct / 100)
            bounds[c] = [float(lo), float(hi)]
        return {"bounds": bounds}

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        out = df.copy()
        bounds = state.get("bounds", {})
        if p["action"] == "clip":
            for c, (lo, hi) in bounds.items():
                if c in out.columns:
                    out[c] = as_float(out[c]).clip(lo, hi)
            return out
        hit = pd.Series(False, index=out.index)
        for c, (lo, hi) in bounds.items():
            if c in out.columns:
                s = as_float(out[c])
                hit |= (s < lo) | (s > hi)
        if p["action"] == "flag":
            out["is_outlier"] = hit.astype("int8")
            return out
        if SPLIT_COL in out.columns:
            hit &= out[SPLIT_COL] == "train"
        return out[~hit].reset_index(drop=True)

    def code(self, params, state):
        b = state.get("bounds", {})
        action = self.defaults(params)["action"]
        if action == "clip":
            lines = [f"df[{_r(c)}] = df[{_r(c)}].clip({lo!r}, {hi!r})" for c, (lo, hi) in b.items()]
            return "\n".join(lines) or "# no bounds"
        cond = " | ".join(f"~df[{_r(c)}].between({lo!r}, {hi!r})" for c, (lo, hi) in b.items())
        if action == "flag":
            return f"df['is_outlier'] = ({cond}).astype('int8')"
        return (
            "# The UI removes outliers from training rows only.\n"
            f"df = df[~(({cond}) & (df.get('__split__', 'train') == 'train'))]"
        )


@register
class RareGroup(Transform):
    step_type = "rare_group"
    label = "Group rare categories"
    category = "clean"
    phase = "post_split"
    requires_fit = True
    params = [
        Param("columns", "columns", "Columns", required=True, column_filter="categorical"),
        Param(
            "min_frequency",
            "number",
            "Minimum share",
            default=0.01,
            min=0,
            max=0.5,
            help="Categories below this share of training rows become 'Other'",
        ),
        Param("max_categories", "integer", "Keep at most", default=None, min=1),
        Param("other_label", "text", "Label for the rest", default="Other"),
    ]
    explain_text = (
        "Merges infrequent categories into 'Other' so encoders don't create "
        "hundreds of sparse columns. Frequencies come from training rows."
    )

    def fit(self, df, params, ctx):
        p = self.defaults(params)
        keep = {}
        for c in self.columns(p, ctx):
            vc = df[c].astype(str).where(df[c].notna()).value_counts(normalize=True)
            kept = vc[vc >= float(p["min_frequency"])]
            if p.get("max_categories"):
                kept = kept.head(int(p["max_categories"]))
            keep[c] = list(kept.index)
        return {"keep": keep}

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        out = df.copy()
        for c, kept in state.get("keep", {}).items():
            s = out[c].astype(str).where(out[c].notna())
            out[c] = s.where(s.isin(kept) | s.isna(), p["other_label"]).astype(object)
        return out

    def code(self, params, state):
        lines = []
        for c, kept in state.get("keep", {}).items():
            lines.append(
                f"df[{_r(c)}] = df[{_r(c)}].where(df[{_r(c)}].isin({_r(kept)}) | "
                f"df[{_r(c)}].isna(), {_r(params.get('other_label', 'Other'))})"
            )
        return "\n".join(lines)


# =============================================================== features (stateless)
DT_PARTS = [
    "year",
    "quarter",
    "month",
    "day",
    "dayofweek",
    "dayofyear",
    "hour",
    "minute",
    "is_weekend",
    "is_month_start",
    "is_month_end",
    "month_sin_cos",
    "elapsed_days",
]


@register
class DatetimeFeatures(Transform):
    step_type = "datetime_features"
    label = "Extract date parts"
    category = "feature"
    params = [
        Param("columns", "columns", "Date columns", required=True, column_filter="datetime"),
        Param(
            "parts",
            "multiselect",
            "Parts",
            default=["year", "month", "dayofweek"],
            options=DT_PARTS,
        ),
        Param("drop_original", "boolean", "Drop the original column", default=True),
    ]
    explain_text = "Turns a date into model-friendly numbers like month and weekday."

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        out = df.copy()
        for c in self.columns(p, ctx):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                d = pd.to_datetime(out[c], errors="coerce", format="mixed")
            for part in p["parts"]:
                if part == "is_weekend":
                    out[f"{c}_is_weekend"] = (d.dt.dayofweek >= 5).astype("Int8")
                elif part == "month_sin_cos":
                    out[f"{c}_month_sin"] = np.sin(2 * np.pi * d.dt.month / 12)
                    out[f"{c}_month_cos"] = np.cos(2 * np.pi * d.dt.month / 12)
                elif part == "elapsed_days":
                    out[f"{c}_elapsed_days"] = (d - pd.Timestamp("1970-01-01")).dt.days
                elif part in ("is_month_start", "is_month_end"):
                    out[f"{c}_{part}"] = getattr(d.dt, part).astype("Int8")
                else:
                    out[f"{c}_{part}"] = getattr(d.dt, part).astype("Int64")
            if p["drop_original"]:
                out = out.drop(columns=[c])
        return out

    def code(self, params, state):
        return f"for c in {_r(params.get('columns'))}:\n    d = pd.to_datetime(df[c])\n" + "".join(
            f"    df[f'{{c}}_{part}'] = d.dt.{part}\n"
            for part in params.get("parts", [])
            if part in ("year", "month", "day", "dayofweek", "hour", "quarter")
        )


@register
class Formula(Transform):
    step_type = "formula"
    label = "New column from formula"
    category = "feature"
    params = [
        Param("name", "text", "New column name", required=True),
        Param(
            "expression",
            "expression",
            "Formula",
            required=True,
            help='e.g. price * quantity, log(income + 1), col("Total Amount") / 12',
        ),
    ]
    explain_text = (
        "Creates a column from arithmetic on other columns. Supports + - * / ** % "
        "comparisons, and log, sqrt, abs, exp, round, min, max."
    )

    def extra_validate(self, p, ctx):
        from .formula import FormulaError, parse

        try:
            refs = parse(p.get("expression") or "")
        except FormulaError as e:
            return [Issue("error", str(e), "expression")]
        missing = [r for r in refs if r not in ctx.columns]
        return (
            [Issue("error", f"Unknown column(s): {', '.join(missing)}", "expression")]
            if missing
            else []
        )

    def transform(self, df, params, state, ctx):
        from .formula import FormulaError, evaluate

        out = df.copy()
        try:
            out[str(params["name"]).strip()] = evaluate(params["expression"], out)
        except FormulaError as e:
            raise StepError(str(e)) from e
        return out

    def describe(self, params):
        return f"{params.get('name')} = {params.get('expression')}"

    def code(self, params, state):
        return f"df[{_r(params.get('name'))}] = df.eval({_r(params.get('expression'))})"
