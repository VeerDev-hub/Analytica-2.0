"""Split, encoders, scalers, numeric transforms, binning, text features, feature selection,
PCA and resamplers. Everything that learns is fitted on the train partition only (rule 4)."""

from __future__ import annotations

import hashlib
import re

import numpy as np
import pandas as pd

from .base import (
    SPLIT_COL,
    Context,
    Issue,
    Param,
    StepError,
    Transform,
    as_float,
    numeric_cols,
)
from .registry import register


def _r(v) -> str:
    return repr(v)


def _safe(name: object) -> str:
    return re.sub(r"[^0-9A-Za-z_]+", "_", str(name)).strip("_")[:40] or "x"


def _is_classification(ctx: Context) -> bool:
    if ctx.task_type:
        return ctx.task_type == "classification"
    return ctx.columns.get(ctx.target or "", "") in ("nominal", "boolean", "ordinal")


# =============================================================== split
@register
class Split(Transform):
    step_type = "split"
    label = "Train / validation / test split"
    category = "split"
    phase = "split"
    changes_rows = False
    params = [
        Param(
            "method",
            "select",
            "Method",
            default="stratified",
            options=["random", "stratified", "time", "group"],
        ),
        Param("ratios", "ratios", "Train / validation / test", default=[0.7, 0.15, 0.15]),
        Param("seed", "integer", "Random seed", default=42),
        Param("stratify_by", "column", "Stratify by", help="Defaults to the target"),
        Param("time_column", "column", "Time column", column_filter="datetime"),
        Param(
            "group_column",
            "column",
            "Group column",
            help="Rows with the same value stay in the same partition (e.g. customer id)",
        ),
    ]
    explain_text = (
        "Marks every row as train, validation or test. Steps after the split learn "
        "only from train rows, which prevents data leakage."
    )

    def extra_validate(self, p, ctx):
        issues = []
        if ctx.has_split:
            issues.append(Issue("error", "The data is already split; a pipeline has one split"))
        r = p.get("ratios") or []
        if (
            len(r) != 3
            or any(not isinstance(x, int | float) or x < 0 for x in r)
            or abs(sum(r) - 1) > 1e-6
            or r[0] <= 0
        ):
            issues.append(
                Issue(
                    "error",
                    "Ratios must be three non-negative numbers that add up to 1, with train > 0",
                    "ratios",
                )
            )
        m = p.get("method")
        if m == "stratified" and not (p.get("stratify_by") or ctx.target):
            issues.append(
                Issue("error", "Choose a column to stratify by (or set a target)", "stratify_by")
            )
        if m == "time" and not p.get("time_column"):
            issues.append(Issue("error", "Choose the time column", "time_column"))
        if m == "group" and not p.get("group_column"):
            issues.append(Issue("error", "Choose the group column", "group_column"))
        return issues

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        n = len(df)
        tr, va, _ = p["ratios"]
        rng = np.random.default_rng(int(p["seed"]))
        labels = np.empty(n, dtype=object)
        method = p["method"]

        def assign(order: np.ndarray) -> None:
            a, b = int(round(tr * len(order))), int(round((tr + va) * len(order)))
            labels[order[:a]] = "train"
            labels[order[a:b]] = "val"
            labels[order[b:]] = "test"

        if method == "time":
            t = pd.to_datetime(df[p["time_column"]], errors="coerce", format="mixed")
            assign(np.argsort(t.fillna(pd.Timestamp.min).to_numpy(), kind="stable"))
        elif method == "group":
            g = df[p["group_column"]].astype(str).fillna("__nan__")
            uniq = g.unique()
            rng.shuffle(uniq)
            a, b = int(round(tr * len(uniq))), int(round((tr + va) * len(uniq)))
            part = (
                {u: "train" for u in uniq[:a]}
                | {u: "val" for u in uniq[a:b]}
                | {u: "test" for u in uniq[b:]}
            )
            labels = g.map(part).to_numpy(dtype=object)
        elif method == "stratified":
            col = p.get("stratify_by") or ctx.target
            strata = df[col].astype(str).fillna("__nan__")
            for _, idx in strata.groupby(strata).groups.items():
                pos = df.index.get_indexer(idx)
                rng.shuffle(pos)
                assign(pos)
        else:
            order = np.arange(n)
            rng.shuffle(order)
            assign(order)
        out = df.copy()
        out[SPLIT_COL] = labels
        return out

    def describe(self, params):
        p = self.defaults(params)
        r = p["ratios"]
        return f"Split {p['method']} {int(r[0] * 100)}/{int(r[1] * 100)}/{int(r[2] * 100)}"

    def code(self, params, state):
        p = self.defaults(params)
        tr, va, te = p["ratios"]
        strat = p.get("stratify_by") if p["method"] == "stratified" else None
        s = "y" if strat else "None"
        return (
            "from sklearn.model_selection import train_test_split\n"
            f"y = df[{_r(strat)}] if {_r(strat)} else None\n"
            f"train, rest = train_test_split(df, train_size={tr}, random_state={p['seed']}, "
            f"stratify={s})\n"
            + (
                f"val, test = train_test_split(rest, test_size={te / (va + te):.4f}, "
                f"random_state={p['seed']})\n"
                if va > 0
                else "test = rest\n"
            )
        )


# =============================================================== encoders
class _Encoder(Transform):
    category = "encode"
    phase = "post_split"
    requires_fit = True

    def extra_validate(self, p, ctx):
        bad = [c for c in self.columns(p, ctx) if ctx.columns.get(c) == "numeric"]
        if bad:
            return [Issue("warning", f"These look numeric already: {', '.join(bad)}", "columns")]
        return []


def _cat(s: pd.Series) -> pd.Series:
    return s.astype(str).where(s.notna(), None)


@register
class OneHotEncode(_Encoder):
    step_type = "one_hot"
    label = "One-hot encode"
    params = [
        Param("columns", "columns", "Columns", required=True, column_filter="categorical"),
        Param(
            "max_categories",
            "integer",
            "Max categories per column",
            default=30,
            min=1,
            help="Less frequent categories share an 'other' column",
        ),
        Param("drop_first", "boolean", "Drop first category (for linear models)", default=False),
        Param("missing_as_category", "boolean", "Missing gets its own column", default=False),
    ]
    explain_text = (
        "Creates one 0/1 column per category. Good for nominal data with few "
        "categories; categories unseen in training become all zeros."
    )
    warnings_text = ["Many categories create many columns; group rare categories first."]

    def fit(self, df, params, ctx):
        p = self.defaults(params)
        cats = {}
        for c in self.columns(p, ctx):
            vc = _cat(df[c]).value_counts()
            top = list(vc.index[: int(p["max_categories"])])
            cats[c] = {"categories": top, "has_other": len(vc) > len(top)}
        return {"categories": cats}

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        out = df.copy()
        for c, info in state["categories"].items():
            s = _cat(out[c])
            cats = info["categories"][1:] if p["drop_first"] else info["categories"]
            new = {f"{c}_{_safe(v)}": (s == v).astype("int8") for v in cats}
            if info["has_other"]:
                new[f"{c}_other"] = (s.notna() & ~s.isin(info["categories"])).astype("int8")
            if p["missing_as_category"]:
                new[f"{c}_missing"] = s.isna().astype("int8")
            out = pd.concat([out.drop(columns=[c]), pd.DataFrame(new, index=out.index)], axis=1)
        return out

    def code(self, params, state):
        cats = {c: i["categories"] for c, i in state.get("categories", {}).items()}
        return (
            f"categories = {_r(cats)}\nfor c, cats in categories.items():\n"
            "    for v in cats:\n        df[f'{c}_{v}'] = (df[c].astype(str) == v)"
            ".astype('int8')\n    df = df.drop(columns=[c])"
        )


@register
class OrdinalEncode(_Encoder):
    step_type = "ordinal"
    label = "Ordinal encode"
    params = [
        Param("columns", "columns", "Columns", required=True, column_filter="categorical"),
        Param(
            "order",
            "mapping",
            "Order per column",
            help='{"size": ["S", "M", "L"]}. Columns without an order use alphabetical.',
        ),
    ]
    explain_text = (
        "Maps categories with a natural order (S < M < L) to 0, 1, 2. Unknown categories become -1."
    )

    def fit(self, df, params, ctx):
        p = self.defaults(params)
        order = p.get("order") or {}
        maps = {}
        for c in self.columns(p, ctx):
            cats = order.get(c) or sorted(_cat(df[c]).dropna().unique().tolist())
            maps[c] = {str(v): i for i, v in enumerate(cats)}
        return {"maps": maps}

    def transform(self, df, params, state, ctx):
        out = df.copy()
        for c, m in state["maps"].items():
            s = _cat(out[c])
            mapped = s.map(m).astype("float64")
            mapped[s.notna() & mapped.isna()] = -1.0  # unseen category
            out[c] = mapped
        return out

    def code(self, params, state):
        return "\n".join(
            f"df[{_r(c)}] = df[{_r(c)}].astype(str).map({_r(m)}).fillna(-1)"
            for c, m in state.get("maps", {}).items()
        )


@register
class LabelEncode(_Encoder):
    step_type = "label_encode"
    label = "Label encode (target)"
    params = [Param("columns", "columns", "Columns", required=True, default=None)]
    explain_text = (
        "Turns class labels into integers 0..k-1, usually for the target column of a classifier."
    )

    def fit(self, df, params, ctx):
        maps = {}
        for c in self.columns(params, ctx):
            maps[c] = {v: i for i, v in enumerate(sorted(_cat(df[c]).dropna().unique()))}
        return {"maps": maps}

    def transform(self, df, params, state, ctx):
        out = df.copy()
        for c, m in state["maps"].items():
            out[c] = _cat(out[c]).map(m).astype("Int64")
        return out

    def code(self, params, state):
        return "\n".join(
            f"df[{_r(c)}] = df[{_r(c)}].astype(str).map({_r(m)})"
            for c, m in state.get("maps", {}).items()
        )


@register
class TargetEncode(_Encoder):
    step_type = "target_encode"
    label = "Target encode"
    params = [
        Param("columns", "columns", "Columns", required=True, column_filter="categorical"),
        Param(
            "smoothing",
            "number",
            "Smoothing",
            default=10,
            min=0,
            help="Higher = rare categories pulled more towards the overall mean",
        ),
    ]
    explain_text = (
        "Replaces each category with the average target value for that category "
        "(learned on train only, smoothed for rare categories). Powerful for "
        "high-cardinality columns."
    )
    warnings_text = ["Leaks the target if fitted on all rows. It is fitted on train only here."]

    def extra_validate(self, p, ctx):
        issues = super().extra_validate(p, ctx)
        if not ctx.target:
            issues.append(Issue("error", "Set a target column first"))
        elif _is_classification(ctx) and ctx.columns.get(ctx.target) != "boolean":
            issues.append(
                Issue(
                    "warning",
                    "For multi-class targets this uses the share of the most common class",
                )
            )
        if not ctx.has_split:
            issues.append(Issue("warning", "No split yet: the encoding sees every row's target"))
        return issues

    def _y(self, df, ctx, positive=None):
        y = df[ctx.target]
        if pd.api.types.is_numeric_dtype(y):
            return as_float(y), None
        pos = positive if positive is not None else _cat(y).value_counts().index[0]
        return (_cat(y) == pos).astype("float64").where(y.notna()), pos

    def fit(self, df, params, ctx):
        p = self.defaults(params)
        y, pos = self._y(df, ctx)
        prior = float(y.mean())
        m = float(p["smoothing"])
        maps = {}
        for c in self.columns(p, ctx):
            g = pd.DataFrame({"k": _cat(df[c]), "y": y}).dropna(subset=["y"]).groupby("k")["y"]
            stats = g.agg(["mean", "count"])
            enc = (stats["mean"] * stats["count"] + prior * m) / (stats["count"] + m)
            maps[c] = {str(k): float(v) for k, v in enc.items()}
        return {"maps": maps, "prior": prior, "positive": pos}

    def transform(self, df, params, state, ctx):
        out = df.copy()
        for c, m in state["maps"].items():
            out[c] = _cat(out[c]).map(m).astype("float64").fillna(state["prior"])
        return out

    def code(self, params, state):
        return "\n".join(
            f"df[{_r(c)}] = df[{_r(c)}].astype(str).map(enc_{_safe(c)})"
            f".fillna({state.get('prior')!r})  # enc_{_safe(c)} = {len(m)} values"
            for c, m in state.get("maps", {}).items()
        )


@register
class FrequencyEncode(_Encoder):
    step_type = "frequency_encode"
    label = "Frequency encode"
    params = [Param("columns", "columns", "Columns", required=True, column_filter="categorical")]
    explain_text = "Replaces each category with how often it appears in the training rows."

    def fit(self, df, params, ctx):
        return {
            "maps": {
                c: {str(k): float(v) for k, v in _cat(df[c]).value_counts(normalize=True).items()}
                for c in self.columns(params, ctx)
            }
        }

    def transform(self, df, params, state, ctx):
        out = df.copy()
        for c, m in state["maps"].items():
            out[c] = _cat(out[c]).map(m).astype("float64").fillna(0.0)
        return out

    def code(self, params, state):
        return "\n".join(
            f"df[{_r(c)}] = df[{_r(c)}].astype(str).map(freq_{_safe(c)}).fillna(0)"
            for c in state.get("maps", {})
        )


@register
class HashEncode(_Encoder):
    step_type = "hash_encode"
    label = "Hash encode"
    requires_fit = False
    params = [
        Param("columns", "columns", "Columns", required=True, column_filter="categorical"),
        Param("n_features", "integer", "Number of hash columns", default=16, min=2, max=1024),
    ]
    explain_text = (
        "Maps categories into a fixed number of columns with a stable hash. Handles "
        "huge or growing category sets; some categories share a column."
    )

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        k = int(p["n_features"])
        out = df.copy()
        for c in self.columns(p, ctx):
            s = _cat(out[c]).fillna("__missing__")
            uniq = {v: int(hashlib.md5(v.encode()).hexdigest(), 16) % k for v in s.unique()}
            bucket = s.map(uniq).to_numpy(dtype="int64")
            mat = np.zeros((len(out), k), dtype="int8")
            mat[np.arange(len(out)), bucket] = 1
            new = pd.DataFrame(mat, index=out.index, columns=[f"{c}_h{i}" for i in range(k)])
            out = pd.concat([out.drop(columns=[c]), new], axis=1)
        return out


# =============================================================== scaling / numeric
@register
class Scale(Transform):
    step_type = "scale"
    label = "Scale numbers"
    category = "scale"
    phase = "post_split"
    requires_fit = True
    params = [
        Param(
            "columns",
            "columns",
            "Columns",
            required=True,
            default=["@numeric"],
            column_filter="numeric",
        ),
        Param(
            "method",
            "select",
            "Method",
            default="standard",
            options=["standard", "minmax", "robust", "maxabs"],
        ),
    ]
    explain_text = (
        "Puts numeric columns on a similar scale. Standard = mean 0, std 1; min-max "
        "= 0..1; robust uses median/IQR and resists outliers. Learned on train rows."
    )
    warnings_text = ["Tree models (random forest, gradient boosting) don't need scaling."]

    def extra_validate(self, p, ctx):
        bad = [c for c in self.columns(p, ctx) if ctx.columns.get(c) not in ("numeric", "boolean")]
        return [Issue("error", f"Not numeric: {', '.join(bad)}", "columns")] if bad else []

    def fit(self, df, params, ctx):
        p = self.defaults(params)
        stats = {}
        for c in numeric_cols(df, self.columns(p, ctx)):
            s = as_float(df[c]).dropna()
            if s.empty:
                continue
            m = p["method"]
            if m == "standard":
                center, scale = s.mean(), s.std(ddof=0)
            elif m == "minmax":
                center, scale = s.min(), s.max() - s.min()
            elif m == "robust":
                center, scale = s.median(), s.quantile(0.75) - s.quantile(0.25)
            else:
                center, scale = 0.0, s.abs().max()
            stats[c] = [float(center), float(scale) if scale and np.isfinite(scale) else 1.0]
        return {"stats": stats}

    def transform(self, df, params, state, ctx):
        out = df.copy()
        for c, (center, scale) in state["stats"].items():
            if c in out.columns:
                out[c] = (as_float(out[c]) - center) / scale
        return out

    def describe(self, params):
        return f"{super().describe(params)} ({params.get('method', 'standard')})"

    def code(self, params, state):
        return "\n".join(
            f"df[{_r(c)}] = (df[{_r(c)}] - {a!r}) / {b!r}"
            for c, (a, b) in state.get("stats", {}).items()
        )


@register
class NumericTransform(Transform):
    step_type = "numeric_transform"
    label = "Transform skewed numbers"
    category = "scale"
    phase = "post_split"
    requires_fit = True
    params = [
        Param("columns", "columns", "Columns", required=True, column_filter="numeric"),
        Param(
            "method",
            "select",
            "Method",
            default="yeo_johnson",
            options=["log1p", "sqrt", "yeo_johnson", "box_cox", "square", "reciprocal"],
        ),
    ]
    explain_text = (
        "Reduces skew so linear models behave better. log1p needs values ≥ 0; "
        "Yeo-Johnson works for any values and learns its strength from train rows."
    )

    def extra_validate(self, p, ctx):
        bad = [c for c in self.columns(p, ctx) if ctx.columns.get(c) != "numeric"]
        return [Issue("error", f"Not numeric: {', '.join(bad)}", "columns")] if bad else []

    def fit(self, df, params, ctx):
        from scipy import stats as st

        p = self.defaults(params)
        lambdas = {}
        if p["method"] in ("yeo_johnson", "box_cox"):
            for c in numeric_cols(df, self.columns(p, ctx)):
                x = as_float(df[c]).dropna().to_numpy()
                if len(x) < 3 or np.ptp(x) == 0:
                    continue
                if p["method"] == "box_cox":
                    if (x <= 0).any():
                        raise StepError(f"Box-Cox needs positive values; '{c}' has values ≤ 0")
                    _, lam = st.boxcox(x)
                else:
                    _, lam = st.yeojohnson(x)
                lambdas[c] = float(lam)
        return {"lambdas": lambdas}

    def transform(self, df, params, state, ctx):
        from scipy import stats as st

        p = self.defaults(params)
        out = df.copy()
        for c in numeric_cols(out, self.columns(p, ctx)):
            x = as_float(out[c])
            m = p["method"]
            with np.errstate(all="ignore"):
                if m == "log1p":
                    out[c] = np.log1p(x.where(x > -1))
                elif m == "sqrt":
                    out[c] = np.sqrt(x.where(x >= 0))
                elif m == "square":
                    out[c] = x**2
                elif m == "reciprocal":
                    out[c] = (1 / x).replace([np.inf, -np.inf], np.nan)
                elif c in state.get("lambdas", {}):
                    lam = state["lambdas"][c]
                    vals = x.to_numpy()
                    mask = ~np.isnan(vals)
                    res = np.full_like(vals, np.nan)
                    if m == "box_cox":
                        res[mask] = st.boxcox(np.where(vals[mask] > 0, vals[mask], np.nan), lam)
                    else:
                        res[mask] = st.yeojohnson(vals[mask], lam)
                    out[c] = res
        return out

    def describe(self, params):
        return f"{super().describe(params)} ({params.get('method', 'yeo_johnson')})"

    def code(self, params, state):
        m = params.get("method", "yeo_johnson")
        if m == "log1p":
            return f"df[{_r(params.get('columns'))}] = np.log1p(df[{_r(params.get('columns'))}])"
        lam = state.get("lambdas", {})
        return "from scipy import stats\n" + "\n".join(
            f"df[{_r(c)}] = stats.yeojohnson(df[{_r(c)}], {v!r})" for c, v in lam.items()
        )


@register
class Binning(Transform):
    step_type = "binning"
    label = "Bin numbers into ranges"
    category = "feature"
    phase = "post_split"
    requires_fit = True
    params = [
        Param("columns", "columns", "Columns", required=True, column_filter="numeric"),
        Param(
            "method",
            "select",
            "Method",
            default="quantile",
            options=["quantile", "uniform", "custom"],
        ),
        Param("bins", "integer", "Number of bins", default=5, min=2, max=100),
        Param("edges", "text", "Custom edges", help="Comma-separated, e.g. 0, 18, 65, 120"),
        Param("keep_original", "boolean", "Keep the original column", default=True),
    ]
    explain_text = "Groups numbers into ranges (e.g. age bands). Bin edges come from train rows."

    def extra_validate(self, p, ctx):
        if p["method"] == "custom":
            try:
                edges = [float(x) for x in str(p.get("edges") or "").split(",") if x.strip()]
            except ValueError:
                return [Issue("error", "Edges must be numbers", "edges")]
            if len(edges) < 2 or edges != sorted(edges):
                return [Issue("error", "Give at least two increasing edges", "edges")]
        return []

    def fit(self, df, params, ctx):
        p = self.defaults(params)
        edges = {}
        for c in numeric_cols(df, self.columns(p, ctx)):
            x = as_float(df[c]).dropna()
            if p["method"] == "custom":
                e = [float(v) for v in str(p["edges"]).split(",") if v.strip()]
            elif p["method"] == "quantile":
                e = np.unique(x.quantile(np.linspace(0, 1, int(p["bins"]) + 1))).tolist()
            else:
                e = np.linspace(x.min(), x.max(), int(p["bins"]) + 1).tolist()
            if len(e) >= 2:
                e[0], e[-1] = -np.inf, np.inf
            edges[c] = [float(v) for v in e]
        return {"edges": edges}

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        out = df.copy()
        for c, e in state["edges"].items():
            if len(e) < 2:
                continue
            binned = pd.cut(as_float(out[c]), bins=e, include_lowest=True)
            labels = binned.astype(str).where(binned.notna(), None)
            if p["keep_original"]:
                out[f"{c}_bin"] = labels
            else:
                out[c] = labels
        return out


@register
class TextFeatures(Transform):
    step_type = "text_features"
    label = "Text features"
    category = "feature"
    phase = "post_split"
    requires_fit = True
    params = [
        Param("columns", "columns", "Text columns", required=True, column_filter="text"),
        Param(
            "features",
            "multiselect",
            "Features",
            default=["length", "word_count"],
            options=["length", "word_count", "digit_share", "upper_share", "tfidf"],
        ),
        Param("max_terms", "integer", "TF-IDF terms", default=50, min=1, max=1000),
        Param("drop_original", "boolean", "Drop the original column", default=True),
    ]
    explain_text = (
        "Turns free text into numbers: lengths and counts, or TF-IDF word weights "
        "learned from the training rows."
    )

    def fit(self, df, params, ctx):
        p = self.defaults(params)
        vocab = {}
        if "tfidf" in p["features"]:
            from sklearn.feature_extraction.text import TfidfVectorizer

            for c in self.columns(p, ctx):
                v = TfidfVectorizer(max_features=int(p["max_terms"]), stop_words="english")
                try:
                    v.fit(df[c].fillna("").astype(str))
                except ValueError:
                    continue
                vocab[c] = {
                    "vocabulary": {k: int(i) for k, i in v.vocabulary_.items()},
                    "idf": v.idf_.tolist(),
                }
        return {"tfidf": vocab}

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        out = df.copy()
        for c in self.columns(p, ctx):
            s = out[c].fillna("").astype(str)
            f = p["features"]
            if "length" in f:
                out[f"{c}_length"] = s.str.len()
            if "word_count" in f:
                out[f"{c}_words"] = s.str.split().str.len().fillna(0).astype(int)
            if "digit_share" in f:
                out[f"{c}_digit_share"] = s.str.count(r"\d") / s.str.len().clip(lower=1)
            if "upper_share" in f:
                out[f"{c}_upper_share"] = s.str.count(r"[A-Z]") / s.str.len().clip(lower=1)
            if c in state.get("tfidf", {}):
                from sklearn.feature_extraction.text import TfidfVectorizer

                info = state["tfidf"][c]
                v = TfidfVectorizer(vocabulary=info["vocabulary"])
                v.fit(["x"])  # sets internal state; idf replaced below
                v.idf_ = np.asarray(info["idf"])
                mat = v.transform(s).toarray()
                terms = sorted(info["vocabulary"], key=info["vocabulary"].get)
                new = pd.DataFrame(
                    mat, index=out.index, columns=[f"{c}_tf_{_safe(t)}" for t in terms]
                )
                out = pd.concat([out, new], axis=1)
            if p["drop_original"]:
                out = out.drop(columns=[c])
        return out


# =============================================================== selection / reduction
@register
class FeatureSelect(Transform):
    step_type = "feature_select"
    label = "Select features"
    category = "select"
    phase = "post_split"
    requires_fit = True
    params = [
        Param(
            "method",
            "select",
            "Method",
            default="variance",
            options=["variance", "correlation", "mutual_info", "k_best"],
        ),
        Param(
            "threshold",
            "number",
            "Threshold",
            default=0.0,
            help="variance: min variance; correlation: max |r| between features (e.g. 0.95)",
        ),
        Param("k", "integer", "Keep top k", default=20, min=1, help="mutual_info / k_best only"),
    ]
    explain_text = (
        "Drops features that carry little information (near-constant), duplicate "
        "each other (highly correlated), or relate weakly to the target. Scores come "
        "from train rows."
    )

    def extra_validate(self, p, ctx):
        if p["method"] in ("mutual_info", "k_best") and not ctx.target:
            return [Issue("error", "This method needs a target column")]
        if p["method"] == "correlation" and not 0 < float(p["threshold"] or 0) <= 1:
            return [
                Issue("error", "For correlation, threshold must be between 0 and 1", "threshold")
            ]
        return []

    def _features(self, df, ctx):
        return [
            c
            for c in df.columns
            if c not in (SPLIT_COL, ctx.target) and pd.api.types.is_numeric_dtype(df[c])
        ]

    def fit(self, df, params, ctx):
        p = self.defaults(params)
        feats = [c for c in self._features(df, ctx) if df[c].notna().any()]
        X = df[feats].astype("float64")
        drop: list[str] = []
        scores: dict[str, float] = {}
        if p["method"] == "variance":
            var = X.var()
            drop = var[var <= float(p["threshold"] or 0)].index.tolist()
            scores = var.to_dict()
        elif p["method"] == "correlation":
            corr = X.corr().abs()
            upper = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1))
            drop = [c for c in upper.columns if (upper[c] > float(p["threshold"])).any()]
        else:
            y = df[ctx.target]
            mask = y.notna()
            Xf = X[mask].fillna(X.median()).fillna(0.0)
            if _is_classification(ctx):
                yv = _cat(y[mask])
                from sklearn.feature_selection import f_classif, mutual_info_classif

                s = (
                    mutual_info_classif(Xf, yv, random_state=0)
                    if p["method"] == "mutual_info"
                    else np.nan_to_num(f_classif(Xf, yv)[0])
                )
            else:
                from sklearn.feature_selection import f_regression, mutual_info_regression

                yv = as_float(y[mask])
                s = (
                    mutual_info_regression(Xf, yv, random_state=0)
                    if p["method"] == "mutual_info"
                    else np.nan_to_num(f_regression(Xf, yv)[0])
                )
            scores = dict(zip(feats, map(float, s), strict=True))
            ranked = sorted(scores, key=scores.get, reverse=True)
            drop = ranked[int(p["k"]) :]
        return {"drop": drop, "scores": {k: float(v) for k, v in scores.items()}}

    def transform(self, df, params, state, ctx):
        return df.drop(columns=[c for c in state["drop"] if c in df.columns])

    def code(self, params, state):
        return f"df = df.drop(columns={_r(state.get('drop', []))})"


@register
class Pca(Transform):
    step_type = "pca"
    label = "PCA (reduce dimensions)"
    category = "select"
    phase = "post_split"
    requires_fit = True
    params = [
        Param(
            "columns",
            "columns",
            "Columns",
            required=True,
            default=["@numeric"],
            column_filter="numeric",
        ),
        Param(
            "n_components",
            "number",
            "Components",
            default=0.95,
            min=0,
            help="Integer = number of components; 0-1 = variance kept",
        ),
        Param("keep_original", "boolean", "Keep original columns", default=False),
    ]
    explain_text = (
        "Combines correlated numeric columns into fewer components. Scale first; "
        "fill missing values first."
    )

    def fit(self, df, params, ctx):
        from sklearn.decomposition import PCA

        p = self.defaults(params)
        cols = numeric_cols(df, self.columns(p, ctx))
        X = df[cols].astype("float64")
        if X.isna().any().any():
            raise StepError("PCA needs complete data: fill missing values first")
        n = float(p["n_components"])
        model = PCA(n_components=int(n) if n >= 1 else n, random_state=0).fit(X)
        return {
            "columns": cols,
            "mean": model.mean_,
            "components": model.components_,
            "explained": model.explained_variance_ratio_.tolist(),
        }

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        X = df[state["columns"]].astype("float64").to_numpy()
        Z = (X - state["mean"]) @ np.asarray(state["components"]).T
        new = pd.DataFrame(Z, index=df.index, columns=[f"pc_{i + 1}" for i in range(Z.shape[1])])
        out = df if p["keep_original"] else df.drop(columns=state["columns"])
        return pd.concat([out, new], axis=1)


# =============================================================== resampling (train only)
class _Resample(Transform):
    category = "resample"
    phase = "post_split"
    train_only = True
    changes_rows = True
    params = [
        Param(
            "sampling_strategy",
            "select",
            "Balance to",
            default="auto",
            options=["auto", "minority", "not majority", "all"],
        ),
        Param("seed", "integer", "Random seed", default=42),
    ]
    warnings_text = [
        "Only training rows are resampled; validation and test keep the real class balance."
    ]

    def extra_validate(self, p, ctx):
        issues = []
        if not ctx.target:
            issues.append(Issue("error", "Set a target column first"))
        elif not _is_classification(ctx):
            issues.append(Issue("error", "Resampling is for classification targets"))
        if not ctx.has_split:
            issues.append(
                Issue(
                    "error",
                    "Add a train/test split first: resampling before "
                    "splitting leaks synthetic rows into the test set",
                )
            )
        return issues

    def sampler(self, p):
        raise NotImplementedError

    def needs_numeric(self) -> bool:
        return False

    def transform(self, df, params, state, ctx):
        p = self.defaults(params)
        if SPLIT_COL not in df.columns or not ctx.target:
            raise StepError("Resampling needs a split and a target")
        train = df[df[SPLIT_COL] == "train"]
        rest = df[df[SPLIT_COL] != "train"]
        train = train[train[ctx.target].notna()]
        feats = [c for c in train.columns if c not in (SPLIT_COL, ctx.target)]
        y = train[ctx.target]
        if y.nunique() < 2:
            raise StepError("The training rows contain only one class")
        if self.needs_numeric():
            bad = [c for c in feats if not pd.api.types.is_numeric_dtype(train[c])]
            if bad:
                raise StepError(f"Encode these columns first: {', '.join(bad[:5])}")
            if train[feats].isna().any().any():
                raise StepError("Fill missing values before using synthetic oversampling")
            X = train[feats].astype("float64")
        else:
            X = pd.DataFrame({"__row__": np.arange(len(train))})
        try:
            Xr, yr = self.sampler(p).fit_resample(
                X, y.astype(str) if not pd.api.types.is_numeric_dtype(y) else y
            )
        except ValueError as e:
            raise StepError(f"Resampling failed: {e}") from e
        if self.needs_numeric():
            res = pd.DataFrame(Xr, columns=feats)
            res[ctx.target] = np.asarray(yr)
            for c in feats:
                if pd.api.types.is_integer_dtype(train[c]):
                    res[c] = res[c].round().astype(train[c].dtype)
            res[ctx.target] = res[ctx.target].astype(train[ctx.target].dtype, errors="ignore")
        else:
            res = train.iloc[np.asarray(Xr["__row__"])].copy()
        res[SPLIT_COL] = "train"
        return pd.concat([res[df.columns.tolist()], rest], ignore_index=True)


@register
class RandomUnder(_Resample):
    step_type = "random_under"
    label = "Random undersample"
    explain_text = "Drops majority-class training rows until classes are balanced."

    def sampler(self, p):
        from imblearn.under_sampling import RandomUnderSampler

        s = p["sampling_strategy"] if p["sampling_strategy"] != "minority" else "majority"
        return RandomUnderSampler(sampling_strategy=s, random_state=int(p["seed"]))


@register
class RandomOver(_Resample):
    step_type = "random_over"
    label = "Random oversample"
    explain_text = "Duplicates minority-class training rows until classes are balanced."

    def sampler(self, p):
        from imblearn.over_sampling import RandomOverSampler

        return RandomOverSampler(
            sampling_strategy=p["sampling_strategy"], random_state=int(p["seed"])
        )


@register
class Smote(_Resample):
    step_type = "smote"
    label = "SMOTE oversample"
    explain_text = (
        "Creates synthetic minority-class rows between existing neighbours. Needs "
        "numeric, complete features (encode and impute first)."
    )

    def needs_numeric(self):
        return True

    def sampler(self, p):
        from imblearn.over_sampling import SMOTE

        return SMOTE(sampling_strategy=p["sampling_strategy"], random_state=int(p["seed"]))


@register
class Adasyn(_Resample):
    step_type = "adasyn"
    label = "ADASYN oversample"
    explain_text = "Like SMOTE but generates more samples where the minority class is harder."

    def needs_numeric(self):
        return True

    def sampler(self, p):
        from imblearn.over_sampling import ADASYN

        return ADASYN(sampling_strategy=p["sampling_strategy"], random_state=int(p["seed"]))


@register
class TomekLinks(_Resample):
    step_type = "tomek"
    label = "Tomek links cleaning"
    explain_text = "Removes majority rows that sit right on the class boundary."
    params = [
        Param(
            "sampling_strategy",
            "select",
            "Clean",
            default="auto",
            options=["auto", "majority", "not minority", "all"],
        )
    ]

    def needs_numeric(self):
        return True

    def sampler(self, p):
        from imblearn.under_sampling import TomekLinks as TL

        return TL(sampling_strategy=p["sampling_strategy"])
