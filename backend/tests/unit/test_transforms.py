"""Definition of done for transforms (design 6.4): edge-case columns, fit on train only,
deterministic replay, every catalog entry has explain text."""

import numpy as np
import pandas as pd
import pytest

from app.engine.pipeline import StepSpec, run_all, run_step, validate_pipeline
from app.engine.transforms import SPLIT_COL, StepError, registry
from app.engine.transforms.formula import FormulaError, evaluate, parse


def frame(n=120, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "age": np.where(rng.random(n) < 0.1, np.nan, rng.integers(18, 80, n)).astype(float),
            "income": rng.lognormal(10, 1, n),
            "city": rng.choice(["Paris", "Rome", "Oslo", "Lima"], n, p=[0.5, 0.3, 0.15, 0.05]),
            "const": ["k"] * n,
            "all_na": [np.nan] * n,
            "mixed": [str(i) if i % 3 else "x" for i in range(n)],
            "joined": pd.date_range("2020-01-01", periods=n, freq="D"),
            "y": rng.choice(["yes", "no"], n, p=[0.2, 0.8]),
        }
    )


def split(df, method="stratified"):
    return run_step(
        StepSpec("split", {"method": method, "ratios": [0.6, 0.2, 0.2]}), df, target="y"
    ).df


def test_catalog_complete():
    cat = registry.catalog()
    assert len(cat) >= 30
    for s in cat:
        assert s["explain"], s["step_type"]
        assert s["phase"] in ("pre_split", "post_split", "split")


CASES = [
    ("drop_columns", {"columns": ["const", "all_na"]}),
    ("keep_columns", {"columns": ["age", "y"]}),
    ("rename_columns", {"mapping": {"age": "Age"}}),
    ("change_type", {"columns": ["mixed"], "to": "numeric"}),
    ("trim_text", {"columns": ["city"], "case": "lower"}),
    ("replace_values", {"columns": ["city"], "mapping": {"Lima": "Other"}}),
    ("drop_duplicates", {}),
    ("drop_missing_rows", {"columns": ["age"]}),
    ("filter_rows", {"column": "age", "op": ">=", "value": "30"}),
    ("impute", {"columns": ["age"], "strategy": "median", "add_indicator": True}),
    ("impute", {"columns": ["city", "all_na"], "strategy": "most_frequent"}),
    ("outliers", {"columns": ["income"], "method": "iqr", "action": "clip"}),
    ("rare_group", {"columns": ["city"], "min_frequency": 0.1}),
    (
        "datetime_features",
        {"columns": ["joined"], "parts": ["year", "month", "is_weekend", "month_sin_cos"]},
    ),
    ("formula", {"name": "ratio", "expression": "income / (age + 1)"}),
    ("one_hot", {"columns": ["city", "const"], "max_categories": 2}),
    ("ordinal", {"columns": ["city"]}),
    ("label_encode", {"columns": ["y"]}),
    ("target_encode", {"columns": ["city"]}),
    ("frequency_encode", {"columns": ["city"]}),
    ("hash_encode", {"columns": ["city"], "n_features": 4}),
    ("scale", {"columns": ["income", "age"], "method": "robust"}),
    ("numeric_transform", {"columns": ["income"], "method": "yeo_johnson"}),
    ("numeric_transform", {"columns": ["income"], "method": "log1p"}),
    ("binning", {"columns": ["income"], "method": "quantile", "bins": 4}),
    ("feature_select", {"method": "variance", "threshold": 0}),
    ("feature_select", {"method": "correlation", "threshold": 0.9}),
    ("feature_select", {"method": "mutual_info", "k": 1}),
]


@pytest.mark.parametrize("step_type,params", CASES)
def test_transform_runs_and_replays_identically(step_type, params):
    df = split(frame())
    a = run_step(StepSpec(step_type, params), df, target="y", task_type="classification")
    b = run_step(StepSpec(step_type, params), df, target="y", task_type="classification")
    pd.testing.assert_frame_equal(a.df, b.df)
    # Reusing the fitted state on the same data gives the same result (export/replay path).
    c = run_step(
        StepSpec(step_type, params), df, target="y", task_type="classification", state=a.state
    )
    pd.testing.assert_frame_equal(a.df, c.df)
    assert registry.get(step_type).describe(params)
    assert isinstance(registry.get(step_type).code(params, a.state), str)


@pytest.mark.parametrize("step_type,params", CASES)
def test_transform_handles_empty_frame(step_type, params):
    df = split(frame()).iloc[:0]
    try:
        run_step(StepSpec(step_type, params), df, target="y", task_type="classification")
    except StepError:
        pass  # a clear user-facing error is acceptable; a crash is not


def test_post_split_fit_uses_train_rows_only():
    df = split(frame(200))
    # Make test rows extreme: if they leaked into fitting, the median would move.
    df.loc[df[SPLIT_COL] == "test", "income"] = 1e12
    df.loc[df[SPLIT_COL] == "test", "age"] = np.nan
    r = run_step(StepSpec("impute", {"columns": ["age"], "strategy": "median"}), df, target="y")
    expected = df.loc[df[SPLIT_COL] == "train", "age"].median()
    assert r.state["fills"]["age"] == pytest.approx(expected)
    s = run_step(StepSpec("scale", {"columns": ["income"], "method": "minmax"}), df, target="y")
    lo, rng = s.state["stats"]["income"]
    assert lo + rng < 1e11  # max learned from train only


def test_split_partitions_and_stratification():
    df = split(frame(1000))
    counts = df[SPLIT_COL].value_counts(normalize=True)
    assert counts["train"] == pytest.approx(0.6, abs=0.02)
    share = df.groupby(SPLIT_COL)["y"].apply(lambda s: (s == "yes").mean())
    assert share.max() - share.min() < 0.05
    with pytest.raises(StepError):
        split(df)  # only one split


def test_group_split_keeps_groups_together():
    df = frame(300)
    df["customer"] = np.arange(300) % 40
    out = run_step(StepSpec("split", {"method": "group", "group_column": "customer"}), df).df
    assert (out.groupby("customer")[SPLIT_COL].nunique() == 1).all()


def test_resampling_touches_train_only_and_balances():
    df = split(frame(600))
    df = run_step(
        StepSpec("drop_columns", {"columns": ["city", "const", "all_na", "mixed", "joined"]}), df
    ).df
    df = run_step(StepSpec("impute", {"columns": ["age"], "strategy": "median"}), df, target="y").df
    test_before = df[df[SPLIT_COL] != "train"].reset_index(drop=True)
    for st in ("smote", "random_over", "random_under"):
        out = run_step(StepSpec(st, {}), df, target="y", task_type="classification").df
        tr = out[out[SPLIT_COL] == "train"]["y"].value_counts()
        assert tr.min() == tr.max(), st
        pd.testing.assert_frame_equal(
            out[out[SPLIT_COL] != "train"].reset_index(drop=True), test_before
        )


def test_resampling_requires_split():
    with pytest.raises(StepError, match="split"):
        run_step(StepSpec("random_over", {}), frame(), target="y", task_type="classification")


def test_validator_blocks_leaky_order():
    steps = [StepSpec("scale", {"columns": ["income"]}), StepSpec("split", {})]
    assert any("leak" in i.message for i in validate_pipeline(steps))
    assert not [i for i in validate_pipeline(list(reversed(steps))) if i.level == "error"]
    assert validate_pipeline([StepSpec("smote", {})])[0].level == "error"


def test_one_hot_unseen_category_is_all_zero():
    df = split(frame())
    r = run_step(StepSpec("one_hot", {"columns": ["city"], "max_categories": 10}), df)
    new = pd.DataFrame({"city": ["Tokyo"], SPLIT_COL: ["test"]})
    out = run_step(
        StepSpec("one_hot", {"columns": ["city"], "max_categories": 10}), new, state=r.state
    ).df
    assert out.drop(columns=[SPLIT_COL]).to_numpy().sum() == 0


def test_run_all_replays_recipe_on_new_data():
    steps = [
        StepSpec("trim_text", {"columns": ["city"], "case": "lower"}, id="1"),
        StepSpec("split", {"method": "random"}, id="2"),
        StepSpec("one_hot", {"columns": ["city"]}, id="3"),
        StepSpec("scale", {"columns": ["income"]}, is_enabled=False, id="4"),
    ]
    out, results = run_all(steps, frame(), target="y")
    assert len(results) == 3 and "city_paris" in out.columns and "income" in out.columns


def test_formula_is_safe():
    df = pd.DataFrame({"a": [1.0, 2.0], "b c": [3.0, 4.0]})
    assert evaluate('a * 2 + col("b c")', df).tolist() == [5.0, 8.0]
    assert evaluate("log(a)", df).iloc[0] == 0.0
    assert set(parse("a > 1 and a < 5")) == {"a"}
    for bad in ("__import__('os')", "a.__class__", "[1,2]", "lambda: 1", "open('x')"):
        with pytest.raises(FormulaError):
            parse(bad)


def test_validation_messages():
    t = registry.get("impute")
    from app.engine.transforms import Context

    ctx = Context.from_df(frame(), "y")
    issues = t.validate({"columns": ["city"], "strategy": "mean"}, ctx)
    assert any(i.level == "error" and "numeric" in i.message for i in issues)
    issues = t.validate({"columns": ["nope"]}, ctx)
    assert any("Unknown column" in i.message for i in issues)
