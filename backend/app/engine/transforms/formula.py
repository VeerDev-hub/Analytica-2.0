"""Safe arithmetic formulas over columns. Parsed with `ast` and evaluated by walking the tree,
so no Python code from users is ever executed (no eval/exec, no attribute access)."""

from __future__ import annotations

import ast

import numpy as np
import pandas as pd


class FormulaError(ValueError):
    pass


_FUNCS = {
    "log": lambda x: np.log(x.where(x > 0)) if isinstance(x, pd.Series) else np.log(x),
    "log1p": np.log1p,
    "sqrt": np.sqrt,
    "abs": np.abs,
    "exp": np.exp,
    "round": lambda x, n=0: np.round(x, int(n)),
    "min": lambda a, b: np.minimum(a, b),
    "max": lambda a, b: np.maximum(a, b),
    "is_missing": lambda x: x.isna().astype("int8"),
    "fill_missing": lambda x, v: x.fillna(v),
}
_BIN = {
    ast.Add: np.add,
    ast.Sub: np.subtract,
    ast.Mult: np.multiply,
    ast.Div: np.divide,
    ast.Pow: np.power,
    ast.Mod: np.mod,
    ast.FloorDiv: np.floor_divide,
}
_CMP = {
    ast.Gt: np.greater,
    ast.GtE: np.greater_equal,
    ast.Lt: np.less,
    ast.LtE: np.less_equal,
    ast.Eq: np.equal,
    ast.NotEq: np.not_equal,
}


def _tree(expr: str) -> ast.Expression:
    if not expr or len(expr) > 500:
        raise FormulaError("Formula is empty or too long")
    try:
        return ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise FormulaError(f"Formula syntax error: {e.msg}") from e


def _col_ref(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "col":
        if (
            len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            return node.args[0].value
        raise FormulaError('col() takes one quoted column name, e.g. col("Total Amount")')
    return None


def parse(expr: str) -> list[str]:
    """Validate the formula; return referenced column names."""
    refs: list[str] = []

    def walk(n: ast.AST) -> None:
        if (ref := _col_ref(n)) is not None:
            refs.append(ref)
            return
        if isinstance(n, ast.Expression):
            walk(n.body)
        elif isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            walk(n.left)
            walk(n.right)
        elif isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub | ast.UAdd | ast.Not):
            walk(n.operand)
        elif isinstance(n, ast.BoolOp):
            for v in n.values:
                walk(v)
        elif isinstance(n, ast.Compare) and all(type(o) in _CMP for o in n.ops):
            walk(n.left)
            for c in n.comparators:
                walk(c)
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS:
            if n.keywords:
                raise FormulaError("Keyword arguments are not supported")
            for a in n.args:
                walk(a)
        elif isinstance(n, ast.Name):
            refs.append(n.id)
        elif isinstance(n, ast.Constant) and isinstance(n.value, int | float | bool):
            pass
        else:
            raise FormulaError(f"Not allowed in a formula: {ast.dump(n)[:60]}")

    walk(_tree(expr))
    return refs


def evaluate(expr: str, df: pd.DataFrame) -> pd.Series:
    parse(expr)

    def ev(n: ast.AST):
        if (ref := _col_ref(n)) is not None:
            return _column(df, ref)
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.BinOp):
            return _BIN[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else (~v if isinstance(n.op, ast.Not) else v)
        if isinstance(n, ast.BoolOp):
            vals = [ev(v) for v in n.values]
            out = vals[0]
            for v in vals[1:]:
                out = (out & v) if isinstance(n.op, ast.And) else (out | v)
            return out
        if isinstance(n, ast.Compare):
            left, result = ev(n.left), None
            for op, comp in zip(n.ops, n.comparators, strict=True):
                right = ev(comp)
                r = _CMP[type(op)](left, right)
                result = r if result is None else (result & r)
                left = right
            return result
        if isinstance(n, ast.Call):
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        if isinstance(n, ast.Name):
            return _column(df, n.id)
        if isinstance(n, ast.Constant):
            return n.value
        raise FormulaError("Unsupported expression")

    with np.errstate(all="ignore"):
        result = ev(_tree(expr))
    if not isinstance(result, pd.Series):
        result = pd.Series(result, index=df.index)
    if result.dtype == bool:
        result = result.astype("int8")
    return result.replace([np.inf, -np.inf], np.nan)


def _column(df: pd.DataFrame, name: str) -> pd.Series:
    if name not in df.columns:
        raise FormulaError(f"Unknown column '{name}'")
    s = df[name]
    if pd.api.types.is_bool_dtype(s):
        return s.astype("int8")
    if not pd.api.types.is_numeric_dtype(s):
        conv = pd.to_numeric(s, errors="coerce")
        if conv.notna().sum() < s.notna().sum() * 0.9:
            raise FormulaError(f"Column '{name}' is not numeric")
        return conv
    return s.astype("float64")
