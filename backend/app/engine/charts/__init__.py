"""ChartFactory (design D-12): chart spec -> Plotly figure JSON, built server-side so the UI,
chat answers and reports share one engine. Ported from legacy/visualizations.py."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..profiling import correlations, infer_semantic_type, to_jsonable
from ..transforms import SPLIT_COL

KINDS = ("histogram", "bar", "box", "violin", "scatter", "line", "heatmap", "pie")
AGGS = ("count", "sum", "mean", "median", "min", "max")
MAX_POINTS = 20_000


class ChartError(ValueError):
    pass


def _need(df: pd.DataFrame, *cols: str | None) -> None:
    for c in cols:
        if c and c not in df.columns:
            raise ChartError(f"Unknown column '{c}'")


def from_spec(df: pd.DataFrame, spec: dict) -> dict:
    """spec = {kind, x, y?, color?, agg?, bins?, log_y?, top?}"""
    import plotly.express as px
    import plotly.io as pio

    kind = spec.get("kind")
    if kind not in KINDS:
        raise ChartError(f"kind must be one of {KINDS}")
    x, y, color = spec.get("x"), spec.get("y"), spec.get("color")
    _need(df, x, y, color)
    agg = spec.get("agg", "count")
    if agg not in AGGS:
        raise ChartError(f"agg must be one of {AGGS}")
    top = int(spec.get("top") or 25)
    title = spec.get("title")
    sampled = False
    if kind in ("scatter", "line", "box", "violin") and len(df) > MAX_POINTS:
        df = df.sample(MAX_POINTS, random_state=0)
        sampled = True

    if kind == "histogram":
        if not x:
            raise ChartError("Choose a column for x")
        fig = px.histogram(
            df,
            x=x,
            color=color,
            nbins=int(spec.get("bins") or 30),
            barmode="overlay" if color else "relative",
            opacity=0.8 if color else 1,
        )
    elif kind in ("bar", "pie"):
        if not x:
            raise ChartError("Choose a column for x")
        if agg == "count" or not y:
            keys = [x] + ([color] if color and kind == "bar" else [])
            data = df.groupby(keys, dropna=False).size().reset_index(name="count")
            val = "count"
        else:
            if not pd.api.types.is_numeric_dtype(df[y]):
                raise ChartError(f"'{y}' must be numeric to compute {agg}")
            keys = [x] + ([color] if color and kind == "bar" else [])
            data = df.groupby(keys, dropna=False)[y].agg(agg).reset_index(name=f"{agg}({y})")
            val = f"{agg}({y})"
        data[x] = data[x].astype(str)
        order = data.groupby(x)[val].sum().sort_values(ascending=False).head(top).index
        data = data[data[x].isin(order)]
        if kind == "pie":
            fig = px.pie(data, names=x, values=val, hole=0.4)
        else:
            fig = px.bar(data, x=x, y=val, color=color, category_orders={x: list(order)})
    elif kind in ("box", "violin"):
        if not (x or y):
            raise ChartError("Choose a numeric column")
        num, cat = (y, x) if y else (x, None)
        fn = px.box if kind == "box" else px.violin
        fig = fn(df, x=cat, y=num, color=color)
    elif kind == "scatter":
        if not (x and y):
            raise ChartError("Scatter needs x and y")
        fig = px.scatter(df, x=x, y=y, color=color, opacity=0.6)
    elif kind == "line":
        if not (x and y):
            raise ChartError("Line needs x and y")
        data = df[[c for c in (x, y, color) if c]].dropna(subset=[x])
        if agg != "count":
            keys = [x] + ([color] if color else [])
            data = data.groupby(keys)[y].agg(agg).reset_index()
        fig = px.line(data.sort_values(x), x=x, y=y, color=color)
    else:  # heatmap
        corr = correlations(
            df.drop(columns=[SPLIT_COL], errors="ignore"), spec.get("method", "pearson")
        )
        if not corr["columns"]:
            raise ChartError("Need at least two numeric columns for a correlation heatmap")
        fig = px.imshow(
            np.array(corr["matrix"], dtype=float),
            x=corr["columns"],
            y=corr["columns"],
            zmin=-1,
            zmax=1,
            color_continuous_scale="RdBu_r",
            text_auto=".2f" if len(corr["columns"]) <= 15 else False,
        )
    if spec.get("log_y"):
        fig.update_yaxes(type="log")
    fig.update_layout(title=title, margin={"l": 40, "r": 20, "t": 40 if title else 20, "b": 40})
    out = json.loads(pio.to_json(fig))
    out["layout"].pop("template", None)  # the UI applies its own light/dark theme
    out["meta"] = {"sampled": sampled, "rows": int(len(df)), "spec": spec}
    return out


def column_detail(df: pd.DataFrame, name: str, target: str | None = None) -> dict:
    """Distribution, outliers and relation to the target for one column."""
    if name not in df.columns:
        raise ChartError(f"Unknown column '{name}'")
    s = df[name]
    sem = infer_semantic_type(s, name)
    out: dict = {"name": name, "semantic_type": sem}
    if pd.api.types.is_numeric_dtype(s) and sem != "boolean":
        x = s.dropna().astype("float64")
        q = x.quantile([0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1]).to_dict()
        iqr = q[0.75] - q[0.25]
        lo, hi = q[0.25] - 1.5 * iqr, q[0.75] + 1.5 * iqr
        counts, edges = (
            np.histogram(x, bins=min(50, max(5, int(np.sqrt(len(x)) or 5)))) if len(x) else ([], [])
        )
        out.update(
            quantiles={str(k): to_jsonable(v) for k, v in q.items()},
            histogram={"edges": to_jsonable(list(edges)), "counts": to_jsonable(list(counts))},
            outliers={
                "low": int((x < lo).sum()),
                "high": int((x > hi).sum()),
                "bounds": [to_jsonable(lo), to_jsonable(hi)],
                "examples": to_jsonable(x[(x < lo) | (x > hi)].head(10).tolist()),
            },
        )
    else:
        vc = s.astype(str).where(s.notna()).value_counts(dropna=True)
        out["value_counts"] = [{"value": k, "count": int(v)} for k, v in vc.head(50).items()]
        out["distinct"] = int(vc.size)
    out["missing"] = int(s.isna().sum())

    if target and target in df.columns and target != name:
        t = df[target]
        t_sem = infer_semantic_type(t, target)
        rel: dict = {"target": target}
        if pd.api.types.is_numeric_dtype(t) and t_sem == "numeric":
            if pd.api.types.is_numeric_dtype(s):
                rel["correlation"] = to_jsonable(s.corr(t))
            else:
                g = (
                    t.groupby(s.astype(str))
                    .agg(["mean", "count"])
                    .sort_values("count", ascending=False)
                    .head(20)
                )
                rel["target_mean_by_value"] = [
                    {"value": k, "mean": to_jsonable(r["mean"]), "count": int(r["count"])}
                    for k, r in g.iterrows()
                ]
        else:
            tc = t.astype(str)
            if pd.api.types.is_numeric_dtype(s) and sem != "boolean":
                g = s.groupby(tc).agg(["mean", "median", "count"])
                rel["by_class"] = [
                    {
                        "class": k,
                        "mean": to_jsonable(r["mean"]),
                        "median": to_jsonable(r["median"]),
                        "count": int(r["count"]),
                    }
                    for k, r in g.iterrows()
                ]
            else:
                top = s.astype(str).value_counts().head(15).index
                ct = pd.crosstab(
                    s.astype(str).where(s.astype(str).isin(top), "Other"), tc, normalize="index"
                )
                rel["class_share_by_value"] = {
                    "values": list(ct.index),
                    "classes": list(map(str, ct.columns)),
                    "matrix": to_jsonable(ct.round(4).values.tolist()),
                }
        out["vs_target"] = rel
    return out
