"""Transform contract (design rule 3 / class diagram 3.3).

Every step is a `Transform` subclass with:
    validate(params, ctx) -> list[Issue]   # before running; ctx knows the schema and target
    fit(train_df, params, ctx) -> dict     # learned state; empty for stateless transforms
    transform(df, params, state, ctx) -> DataFrame
    describe(params) -> str                # human text for the pipeline panel
    code(params) -> str                    # pandas/sklearn snippet for the exported script

Phases (rule 4): `pre_split` = row-wise and stateless; `post_split` = learns statistics, fitted
on the train partition only; `split` = the single split step.
"""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar

import joblib
import numpy as np
import pandas as pd

SPLIT_COL = "__split__"
RESERVED_COLUMNS = (SPLIT_COL,)


@dataclass
class Issue:
    level: str  # error | warning
    message: str
    field: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class StepError(ValueError):
    """Raised by a transform when it cannot run; message is shown to the user."""


@dataclass
class Param:
    name: str
    type: str  # columns | column | select | multiselect | number | integer | text | boolean
    #            | mapping | ratios | expression
    label: str
    default: Any = None
    required: bool = False
    options: list[Any] | None = None
    help: str | None = None
    column_filter: str | None = None  # numeric | categorical | datetime | text | any
    min: float | None = None
    max: float | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Context:
    """What a transform may know about the data besides the frame itself."""

    columns: dict[str, str] = field(default_factory=dict)  # name -> semantic type
    target: str | None = None
    task_type: str | None = None
    has_split: bool = False

    @classmethod
    def from_df(
        cls, df: pd.DataFrame, target: str | None = None, task_type: str | None = None
    ) -> Context:
        from ..profiling import infer_semantic_type

        cols = {c: infer_semantic_type(df[c], c) for c in df.columns if c not in RESERVED_COLUMNS}
        return cls(
            columns=cols, target=target, task_type=task_type, has_split=SPLIT_COL in df.columns
        )


# Column selector tokens let recipes say "all numeric columns" instead of names.
SELECTORS = {
    "@numeric": {"numeric"},
    "@categorical": {"nominal", "ordinal", "boolean"},
    "@nominal": {"nominal"},
    "@datetime": {"datetime"},
    "@text": {"text"},
    "@all": None,
}


def resolve_columns(spec: Any, ctx: Context, *, include_target: bool = False) -> list[str]:
    if spec is None:
        return []
    items = [spec] if isinstance(spec, str) else list(spec)
    out: list[str] = []
    for item in items:
        if isinstance(item, str) and item in SELECTORS:
            types = SELECTORS[item]
            for name, sem in ctx.columns.items():
                if (types is None or sem in types) and (include_target or name != ctx.target):
                    out.append(name)
        else:
            out.append(str(item))
    seen: set[str] = set()
    return [c for c in out if not (c in seen or seen.add(c))]


class Transform:
    step_type: ClassVar[str]
    label: ClassVar[str]
    category: ClassVar[str]  # clean | columns | rows | encode | scale | feature | resample | select
    phase: ClassVar[str] = "pre_split"
    requires_fit: ClassVar[bool] = False
    params: ClassVar[list[Param]] = []
    explain_text: ClassVar[str] = ""
    warnings_text: ClassVar[list[str]] = []
    changes_rows: ClassVar[bool] = False
    train_only: ClassVar[bool] = False  # resamplers: only touch train rows

    # ---- catalog
    @classmethod
    def spec(cls) -> dict:
        return {
            "step_type": cls.step_type,
            "label": cls.label,
            "category": cls.category,
            "phase": cls.phase,
            "requires_fit": cls.requires_fit,
            "params": [p.to_dict() for p in cls.params],
            "explain": cls.explain_text,
            "warnings": cls.warnings_text,
            "changes_rows": cls.changes_rows,
        }

    # ---- helpers
    @classmethod
    def defaults(cls, params: dict) -> dict:
        merged = {p.name: p.default for p in cls.params}
        merged.update({k: v for k, v in (params or {}).items() if v is not None})
        return merged

    @classmethod
    def columns(cls, params: dict, ctx: Context, key: str = "columns") -> list[str]:
        return resolve_columns(params.get(key), ctx)

    # ---- contract
    def validate(self, params: dict, ctx: Context) -> list[Issue]:
        issues: list[Issue] = []
        p = self.defaults(params)
        for spec in self.params:
            v = p.get(spec.name)
            if spec.required and (v is None or v == "" or v == [] or v == {}):
                issues.append(Issue("error", f"'{spec.label}' is required", spec.name))
                continue
            if v is None:
                continue
            if spec.type in ("columns", "column"):
                names = resolve_columns(v, ctx, include_target=True)
                missing = [c for c in names if c not in ctx.columns]
                if missing:
                    issues.append(
                        Issue("error", f"Unknown column(s): {', '.join(missing)}", spec.name)
                    )
                if spec.type == "columns" and spec.required and not names:
                    issues.append(Issue("error", f"'{spec.label}' matched no columns", spec.name))
                if (
                    ctx.target
                    and ctx.target in names
                    and self.category not in ("rows", "clean", "columns")
                ):
                    issues.append(
                        Issue(
                            "warning",
                            f"This step changes the target column '{ctx.target}'",
                            spec.name,
                        )
                    )
            if spec.type in ("select",) and spec.options and v not in spec.options:
                issues.append(
                    Issue("error", f"'{spec.label}' must be one of {spec.options}", spec.name)
                )
            if spec.type in ("number", "integer"):
                try:
                    num = float(v)
                except (TypeError, ValueError):
                    issues.append(Issue("error", f"'{spec.label}' must be a number", spec.name))
                    continue
                if spec.min is not None and num < spec.min:
                    issues.append(Issue("error", f"'{spec.label}' must be ≥ {spec.min}", spec.name))
                if spec.max is not None and num > spec.max:
                    issues.append(Issue("error", f"'{spec.label}' must be ≤ {spec.max}", spec.name))
        issues += self.extra_validate(p, ctx)
        return issues

    def extra_validate(self, params: dict, ctx: Context) -> list[Issue]:
        return []

    def fit(self, df: pd.DataFrame, params: dict, ctx: Context) -> dict:
        return {}

    def transform(self, df: pd.DataFrame, params: dict, state: dict, ctx: Context) -> pd.DataFrame:
        raise NotImplementedError

    def describe(self, params: dict) -> str:
        p = self.defaults(params)
        cols = p.get("columns")
        if isinstance(cols, list) and cols:
            shown = ", ".join(map(str, cols[:3])) + (f" +{len(cols) - 3}" if len(cols) > 3 else "")
            return f"{self.label}: {shown}"
        return self.label

    def code(self, params: dict, state: dict) -> str:
        return f"# {self.describe(params)}\n# (no code template for {self.step_type})"


# ---------------------------------------------------------------- fitted state persistence
def state_to_bytes(state: dict) -> bytes:
    buf = io.BytesIO()
    joblib.dump(state, buf, compress=3)
    return buf.getvalue()


def state_from_bytes(data: bytes) -> dict:
    return joblib.load(io.BytesIO(data))


def numeric_cols(df: pd.DataFrame, cols: list[str]) -> list[str]:
    return [c for c in cols if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]


def as_float(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("float64")


def jsonable_state(state: dict) -> dict:
    """Small, human-readable summary of fitted state for the UI."""
    from ..profiling import to_jsonable

    out = {}
    for k, v in state.items():
        if isinstance(v, dict | list | str | int | float | bool) or v is None:
            out[k] = to_jsonable(v)
        elif isinstance(v, np.ndarray) and v.size <= 50:
            out[k] = to_jsonable(v.tolist())
    return out
