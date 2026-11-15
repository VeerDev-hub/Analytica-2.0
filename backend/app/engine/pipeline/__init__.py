"""PipelineExecutor and PipelineValidator (class diagram 3.4)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..transforms import SPLIT_COL, Context, Issue, StepError, registry


@dataclass
class StepSpec:
    step_type: str
    params: dict
    is_enabled: bool = True
    id: str | None = None


@dataclass
class StepResult:
    df: pd.DataFrame
    state: dict
    rows_before: int
    rows_after: int
    cols_before: int
    cols_after: int
    added_columns: list[str] = field(default_factory=list)
    dropped_columns: list[str] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "rows_before": self.rows_before,
            "rows_after": self.rows_after,
            "cols_before": self.cols_before,
            "cols_after": self.cols_after,
            "added_columns": self.added_columns,
            "dropped_columns": self.dropped_columns,
            "warnings": self.warnings,
        }


def train_rows(df: pd.DataFrame) -> pd.DataFrame:
    return df[df[SPLIT_COL] == "train"] if SPLIT_COL in df.columns else df


def run_step(
    step: StepSpec,
    df: pd.DataFrame,
    *,
    target: str | None = None,
    task_type: str | None = None,
    state: dict | None = None,
) -> StepResult:
    """Validate, fit (on train rows only) and apply one step."""
    t = registry.get(step.step_type)
    ctx = Context.from_df(df, target, task_type)
    params = t.defaults(step.params)
    issues = t.validate(step.params, ctx)
    errors = [i for i in issues if i.level == "error"]
    if errors:
        raise StepError("; ".join(i.message for i in errors))
    warns = [i.to_dict() for i in issues if i.level == "warning"]

    if state is None:
        if t.requires_fit:
            fit_df = train_rows(df)
            if SPLIT_COL not in df.columns and t.phase == "post_split":
                warns.append(
                    {
                        "level": "warning",
                        "field": None,
                        "message": "No split yet: statistics are learned from all rows. "
                        "Add a split to avoid data leakage.",
                    }
                )
            if fit_df.empty:
                raise StepError("There are no training rows to learn from")
            state = t.fit(fit_df, params, ctx)
        else:
            state = {}
    out = t.transform(df, params, state, ctx)
    if not isinstance(out, pd.DataFrame):
        raise StepError("Transform did not return a table")
    before, after = list(df.columns), list(out.columns)
    return StepResult(
        df=out.reset_index(drop=True),
        state=state,
        rows_before=len(df),
        rows_after=len(out),
        cols_before=len([c for c in before if c != SPLIT_COL]),
        cols_after=len([c for c in after if c != SPLIT_COL]),
        added_columns=[c for c in after if c not in before and c != SPLIT_COL],
        dropped_columns=[c for c in before if c not in after and c != SPLIT_COL],
        warnings=warns,
    )


def run_all(
    steps: list[StepSpec],
    df: pd.DataFrame,
    *,
    target: str | None = None,
    task_type: str | None = None,
    states: dict[str, dict] | None = None,
) -> tuple[pd.DataFrame, list[StepResult]]:
    """Replay a recipe. Pass `states` (by step id) to reuse fitted state on new data."""
    results = []
    for s in steps:
        if not s.is_enabled:
            continue
        r = run_step(
            s, df, target=target, task_type=task_type, state=(states or {}).get(s.id or "")
        )
        results.append(r)
        df = r.df
        if s.step_type == "rename_columns" and target in (s.params.get("mapping") or {}):
            target = s.params["mapping"][target]
    return df, results


def validate_pipeline(steps: list[StepSpec], target: str | None = None) -> list[Issue]:
    """Structural checks that don't need data: one split, phase order, leakage."""
    issues: list[Issue] = []
    enabled = [s for s in steps if s.is_enabled]
    splits = [i for i, s in enumerate(enabled) if s.step_type == "split"]
    if len(splits) > 1:
        issues.append(Issue("error", "A pipeline can contain only one split step"))
    split_at = splits[0] if splits else None
    for i, s in enumerate(enabled):
        if not registry.has(s.step_type):
            issues.append(Issue("error", f"Unknown step type '{s.step_type}'"))
            continue
        t = registry.get(s.step_type)
        if t.phase == "post_split" and split_at is not None and i < split_at:
            issues.append(
                Issue(
                    "error",
                    f"'{t.label}' learns from the data and must come after "
                    "the split, otherwise test rows leak into training",
                )
            )
        if t.train_only and split_at is None:
            issues.append(Issue("error", f"'{t.label}' needs a split before it"))
    return issues
