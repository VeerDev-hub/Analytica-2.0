"""ReadinessChecker (class diagram 3.4) and a quick baseline model."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from ..profiling import infer_semantic_type, to_jsonable
from ..transforms import SPLIT_COL

PASS, WARN, FAIL = "pass", "warn", "fail"


def _check(cid: str, label: str, status: str, detail: str, fix: dict | None = None) -> dict:
    return {"id": cid, "label": label, "status": status, "detail": detail, "fix": fix}


def features_of(df: pd.DataFrame, target: str | None) -> list[str]:
    return [c for c in df.columns if c not in (SPLIT_COL, target)]


def check(
    df: pd.DataFrame, target: str | None, task_type: str | None, framework: str = "sklearn"
) -> dict:
    checks: list[dict] = []
    feats = features_of(df, target)
    n = len(df)

    # target
    if not target or target not in df.columns:
        checks.append(
            _check(
                "target",
                "Target column chosen",
                FAIL,
                "Choose the column the model should predict.",
            )
        )
    else:
        miss = int(df[target].isna().sum())
        checks.append(
            _check(
                "target",
                "Target column chosen",
                PASS if not miss else FAIL,
                f"'{target}'" + (f" has {miss} missing values" if miss else ""),
                {"step_type": "drop_missing_rows", "params": {"columns": [target]}}
                if miss
                else None,
            )
        )
        if task_type is None:
            checks.append(
                _check(
                    "task",
                    "Task type set",
                    WARN,
                    "Set classification or regression for better checks.",
                )
            )

    # split
    has_split = SPLIT_COL in df.columns
    if has_split:
        counts = df[SPLIT_COL].value_counts().to_dict()
        checks.append(
            _check(
                "split",
                "Train / test split",
                PASS,
                " · ".join(f"{k} {v:,}" for k, v in counts.items()),
            )
        )
    else:
        checks.append(
            _check(
                "split",
                "Train / test split",
                FAIL,
                "Add a split so the model is evaluated on unseen rows.",
                {"step_type": "split", "params": {}},
            )
        )

    # missing values
    miss_cols = [c for c in feats if df[c].isna().any()]
    checks.append(
        _check(
            "no_missing",
            "No missing values in features",
            PASS if not miss_cols else FAIL,
            "All features are complete."
            if not miss_cols
            else f"{len(miss_cols)} column(s) have gaps: {', '.join(miss_cols[:6])}",
            {"step_type": "impute", "params": {"columns": miss_cols[:20], "strategy": "median"}}
            if miss_cols
            else None,
        )
    )

    # numeric only
    sem = {c: infer_semantic_type(df[c], c) for c in feats}
    non_num = [
        c
        for c in feats
        if not (pd.api.types.is_numeric_dtype(df[c]) or pd.api.types.is_bool_dtype(df[c]))
    ]
    cat_cols = [c for c in non_num if sem[c] in ("nominal", "boolean", "ordinal")]
    checks.append(
        _check(
            "numeric_only",
            "All features are numeric",
            PASS if not non_num else FAIL,
            "Ready for any model."
            if not non_num
            else f"Encode or drop: {', '.join(non_num[:6])}" + ("…" if len(non_num) > 6 else ""),
            {"step_type": "one_hot", "params": {"columns": cat_cols[:20]}}
            if cat_cols
            else (
                {"step_type": "drop_columns", "params": {"columns": non_num[:20]}}
                if non_num
                else None
            ),
        )
    )

    # constant / id-like
    const = [c for c in feats if df[c].nunique(dropna=True) <= 1]
    if const:
        checks.append(
            _check(
                "constant",
                "No constant features",
                WARN,
                f"No information in: {', '.join(const[:6])}",
                {"step_type": "drop_columns", "params": {"columns": const}},
            )
        )
    ids = [c for c in feats if sem[c] == "id"]
    if ids:
        checks.append(
            _check(
                "id_like",
                "No identifier columns",
                WARN,
                f"Identifiers let models memorise rows: {', '.join(ids[:6])}",
                {"step_type": "drop_columns", "params": {"columns": ids}},
            )
        )

    # leakage: features that predict the target almost perfectly
    if target and target in df.columns and n >= 20:
        leaks = target_leakage(df, target, feats)
        checks.append(
            _check(
                "leakage",
                "No target leakage",
                WARN if leaks else PASS,
                "No feature is a near-copy of the target."
                if not leaks
                else "Suspiciously strong: " + ", ".join(f"{c} ({why})" for c, why in leaks[:5]),
                {"step_type": "drop_columns", "params": {"columns": [c for c, _ in leaks]}}
                if leaks
                else None,
            )
        )

    # split contamination
    if has_split:
        dup = split_contamination(df)
        checks.append(
            _check(
                "contamination",
                "Test rows not duplicated in train",
                PASS if dup == 0 else WARN,
                "No identical rows across partitions."
                if dup == 0
                else f"{dup} test/validation rows also appear in train: scores will look too good.",
                {"step_type": "drop_duplicates", "params": {}} if dup else None,
            )
        )

    # imbalance
    if (
        target
        and target in df.columns
        and (
            task_type == "classification"
            or (
                task_type is None
                and sem.get(target, infer_semantic_type(df[target], target))
                in ("nominal", "boolean")
            )
        )
    ):
        train = df[df[SPLIT_COL] == "train"] if has_split else df
        vc = train[target].value_counts(normalize=True)
        if len(vc) >= 2:
            minority = float(vc.iloc[-1])
            checks.append(
                _check(
                    "imbalance",
                    "Classes reasonably balanced",
                    PASS if minority >= 0.2 else WARN,
                    f"Smallest class is {minority:.1%} of training rows.",
                    {"step_type": "smote", "params": {}} if minority < 0.2 else None,
                )
            )

    # width vs rows
    if feats:
        ratio = len(feats) / max(n, 1)
        checks.append(
            _check(
                "width",
                "Enough rows per feature",
                PASS if ratio < 0.1 else WARN,
                f"{len(feats)} features for {n:,} rows.",
                {"step_type": "feature_select", "params": {"method": "variance"}}
                if ratio >= 0.1
                else None,
            )
        )

    # scale spread (matters for linear models and neural nets)
    num = [c for c in feats if pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique() > 2]
    if len(num) >= 2:
        spans = df[num].astype("float64").abs().max().replace(0, np.nan).dropna()
        if len(spans) >= 2 and spans.max() / spans.min() > 1000:
            status = WARN if framework in ("sklearn", "pytorch", "tensorflow") else PASS
            checks.append(
                _check(
                    "scale",
                    "Features on similar scales",
                    status,
                    f"Ranges differ by {spans.max() / spans.min():,.0f}×. Scale "
                    "for linear models and neural networks (not needed for trees).",
                    {"step_type": "scale", "params": {"columns": ["@numeric"]}},
                )
            )

    score = round(100 * sum(c["status"] == PASS for c in checks) / max(len(checks), 1))
    ready = not any(c["status"] == FAIL for c in checks)
    return {
        "ready": ready,
        "score": score,
        "checks": checks,
        "rows": n,
        "features": len(feats),
        "target": target,
        "task_type": task_type,
    }


def target_leakage(df: pd.DataFrame, target: str, feats: list[str]) -> list[tuple[str, str]]:
    out = []
    y = df[target]
    y_num = pd.api.types.is_numeric_dtype(y) and y.nunique() > 2
    sample = df.sample(min(len(df), 50_000), random_state=0) if len(df) > 50_000 else df
    for c in feats:
        s = sample[c]
        if s.nunique(dropna=True) <= 1:
            continue
        if y_num and pd.api.types.is_numeric_dtype(s):
            r = s.corr(sample[target])
            if r is not None and abs(r) > 0.98:
                out.append((c, f"r={r:.3f}"))
        elif not y_num:
            ok = sample[[c, target]].dropna()
            if len(ok) < 20 or ok[c].nunique() > 0.5 * len(ok):
                continue
            purity = ok.groupby(c)[target].agg(lambda t: t.value_counts(normalize=True).iloc[0])
            weights = ok[c].value_counts(normalize=True)
            p = float((purity * weights.reindex(purity.index)).sum())
            baseline = float(ok[target].value_counts(normalize=True).iloc[0])
            if p > 0.995 and baseline < 0.95:
                out.append((c, "predicts the target perfectly"))
    return out


def split_contamination(df: pd.DataFrame) -> int:
    cols = [c for c in df.columns if c != SPLIT_COL]
    h = pd.util.hash_pandas_object(df[cols], index=False)
    train_hashes = set(h[df[SPLIT_COL] == "train"].tolist())
    return int(h[df[SPLIT_COL] != "train"].isin(train_hashes).sum())


def frame_fingerprint(df: pd.DataFrame) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()[
        :16
    ]


# --------------------------------------------------------------------------- baseline
def baseline(df: pd.DataFrame, target: str, task_type: str | None) -> dict:
    """Train quick reference models on train rows, score on validation (or test)."""
    from sklearn.dummy import DummyClassifier, DummyRegressor
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.metrics import (
        accuracy_score,
        balanced_accuracy_score,
        f1_score,
        mean_absolute_error,
        r2_score,
        roc_auc_score,
        root_mean_squared_error,
    )
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if target not in df.columns:
        raise ValueError("Choose a target column first")
    df = df[df[target].notna()]
    if SPLIT_COL in df.columns:
        train = df[df[SPLIT_COL] == "train"]
        evalset = df[df[SPLIT_COL] == "val"]
        eval_name = "validation"
        if evalset.empty:
            evalset, eval_name = df[df[SPLIT_COL] == "test"], "test"
    else:
        rng = np.random.default_rng(0)
        mask = rng.random(len(df)) < 0.8
        train, evalset, eval_name = df[mask], df[~mask], "random 20% hold-out (no split set)"
    feats = [
        c
        for c in features_of(df, target)
        if pd.api.types.is_numeric_dtype(df[c]) or pd.api.types.is_bool_dtype(df[c])
    ]
    dropped = [c for c in features_of(df, target) if c not in feats]
    if not feats:
        raise ValueError("No numeric features: encode categorical columns first")
    if len(train) < 10 or len(evalset) < 5:
        raise ValueError("Not enough rows in the training or evaluation partition")
    Xtr, Xev = train[feats].astype("float64"), evalset[feats].astype("float64")
    classification = task_type == "classification" or (
        task_type is None
        and (not pd.api.types.is_numeric_dtype(df[target]) or df[target].nunique() <= 20)
    )
    results = []
    if classification:
        ytr, yev = train[target].astype(str), evalset[target].astype(str)
        models = {
            "Most frequent class": DummyClassifier(strategy="most_frequent"),
            "Gradient boosting": HistGradientBoostingClassifier(max_iter=200, random_state=0),
        }
        if not Xtr.isna().any().any():
            models["Logistic regression"] = make_pipeline(
                StandardScaler(), LogisticRegression(max_iter=1000)
            )
        binary = ytr.nunique() == 2
        for name, m in models.items():
            m.fit(Xtr, ytr)
            pred = m.predict(Xev)
            row = {
                "model": name,
                "accuracy": accuracy_score(yev, pred),
                "balanced_accuracy": balanced_accuracy_score(yev, pred),
                "f1_macro": f1_score(yev, pred, average="macro", zero_division=0),
            }
            if binary and hasattr(m, "predict_proba") and yev.nunique() == 2:
                pos = m.classes_[1]
                row["roc_auc"] = roc_auc_score(yev == pos, m.predict_proba(Xev)[:, 1])
            results.append(row)
        primary = "balanced_accuracy"
    else:
        ytr, yev = train[target].astype("float64"), evalset[target].astype("float64")
        models = {
            "Mean value": DummyRegressor(),
            "Gradient boosting": HistGradientBoostingRegressor(max_iter=200, random_state=0),
        }
        if not Xtr.isna().any().any():
            models["Ridge regression"] = make_pipeline(StandardScaler(), Ridge())
        for name, m in models.items():
            m.fit(Xtr, ytr)
            pred = m.predict(Xev)
            results.append(
                {
                    "model": name,
                    "r2": r2_score(yev, pred),
                    "mae": mean_absolute_error(yev, pred),
                    "rmse": root_mean_squared_error(yev, pred),
                }
            )
        primary = "r2"

    importances = []
    gb = models["Gradient boosting"]
    try:
        from sklearn.inspection import permutation_importance

        sub = min(len(Xev), 2000)
        pi = permutation_importance(gb, Xev.iloc[:sub], yev.iloc[:sub], n_repeats=3, random_state=0)
        order = np.argsort(pi.importances_mean)[::-1][:15]
        importances = [
            {"feature": feats[i], "importance": float(pi.importances_mean[i])} for i in order
        ]
    except Exception:  # noqa: BLE001 - importances are a nice-to-have
        pass
    return to_jsonable(
        {
            "task": "classification" if classification else "regression",
            "evaluated_on": eval_name,
            "train_rows": len(train),
            "eval_rows": len(evalset),
            "features_used": len(feats),
            "features_dropped": dropped[:50],
            "primary_metric": primary,
            "results": results,
            "importances": importances,
        }
    )
