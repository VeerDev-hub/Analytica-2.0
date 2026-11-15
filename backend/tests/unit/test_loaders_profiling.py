import numpy as np
import pandas as pd
import pytest

from app.engine.loaders import LoadError, detect_format, read_any
from app.engine.profiling import correlations, infer_semantic_type, profile, to_jsonable


def test_detect_format():
    assert detect_format("a.CSV") == "csv"
    assert detect_format("a.tsv") == "csv"
    with pytest.raises(LoadError):
        detect_format("a.docx")


def test_semicolon_latin1_csv():
    data = "name;price\nCafé;1,50\nThé;2,00\n".encode("latin-1")
    df = read_any(data, "x.csv")
    assert list(df.columns) == ["name", "price"]
    assert df["name"].tolist() == ["Café", "Thé"]
    # "1,50" is a European decimal, not a thousands separator: must stay text, not 150.
    assert df["price"].dtype == object


def test_lossless_numeric_and_names():
    data = b'Amount, amount ,Unnamed: 2\n"1,200",3,\n$5,4,\n,,\n'
    df = read_any(data, "x.csv")
    assert list(df.columns) == ["Amount", "amount"]  # empty unnamed column removed
    assert df["Amount"].tolist()[:2] == [1200.0, 5.0]
    assert len(df) == 2  # fully empty row removed


def test_duplicate_column_names_are_suffixed():
    df = read_any(b"a,a,b\n1,2,3\n", "x.csv")
    assert len(set(df.columns)) == 3


def test_mixed_text_not_converted():
    df = read_any(b"code\n001\nA12\n7\n", "x.csv")
    assert df["code"].dtype == object


@pytest.mark.parametrize(
    "values,name,expected",
    [
        ([1.5, 2.5, 3.5, None], "x", "numeric"),
        (["a", "b", "a", "c"], "x", "nominal"),
        (["yes", "no", "yes", None], "x", "boolean"),
        (["2024-01-01", "2024-02-03", "2023-12-31"], "x", "datetime"),
        ([7, 7, 7], "x", "constant"),
        ([None, None], "x", "empty"),
        ([f"u{i:05d}" for i in range(200)], "user_id", "id"),
        (list(range(200)), "customer_id", "id"),
        (list(range(200)), "age", "numeric"),
    ],
)
def test_semantic_types(values, name, expected):
    assert infer_semantic_type(pd.Series(values), name) == expected


def test_profile_alerts_and_json_safety():
    rng = np.random.default_rng(0)
    df = pd.DataFrame(
        {
            "income": np.concatenate([rng.lognormal(10, 1.5, 195), [np.nan] * 5]),
            "const": ["x"] * 200,
            "num_text": [f"{i}%" for i in range(200)],
            "y": ["a"] * 190 + ["b"] * 10,
        }
    )
    df = pd.concat([df, df.iloc[:3]], ignore_index=True)
    prof = profile(df, target="y")
    codes = {a["code"] for a in prof["alerts"]}
    assert {"CONSTANT", "SKEWED", "DUPLICATE_ROWS", "CLASS_IMBALANCE"} <= codes
    assert "NUMERIC_AS_TEXT" in codes
    assert prof["summary"]["duplicate_rows"] == 3
    import json

    json.dumps(prof)  # no numpy types / NaN left


def test_profile_handles_all_missing_and_empty_frames():
    prof = profile(pd.DataFrame({"a": [None, None], "b": [1, 2]}))
    assert prof["columns"][0]["semantic_type"] == "empty"
    prof = profile(pd.DataFrame({"a": pd.Series([], dtype=float)}))
    assert prof["summary"]["row_count"] == 0


def test_correlations_and_jsonable():
    df = pd.DataFrame({"a": [1, 2, 3, 4], "b": [2, 4, 6, 8.5], "c": [1, 1, 1, 1]})
    out = correlations(df)
    assert out["columns"] == ["a", "b"] and out["top_pairs"][0]["r"] > 0.99
    assert to_jsonable(np.float64("nan")) is None
    assert to_jsonable({"x": np.int64(3)}) == {"x": 3}
