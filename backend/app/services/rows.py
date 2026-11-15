"""Server-side paging, sorting and filtering of a version's rows with DuckDB."""

from __future__ import annotations

import datetime as dt
import decimal
import json
import math

import duckdb

from app.core.errors import ValidationFailed
from app.models import DatasetVersion
from app.storage.cache import local_path

FILTER_OPS = {
    "eq": "= ?",
    "neq": "<> ?",
    "gt": "> ?",
    "gte": ">= ?",
    "lt": "< ?",
    "lte": "<= ?",
    "contains": None,
    "is_null": "IS NULL",
    "not_null": "IS NOT NULL",
}


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def py_jsonable(v):
    if v is None:
        return None
    if isinstance(v, float):
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(v, dt.datetime | dt.date | dt.time):
        return v.isoformat()
    if isinstance(v, dt.timedelta):
        return str(v)
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    if isinstance(v, list | tuple):
        return [py_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): py_jsonable(x) for k, x in v.items()}
    return v


def parse_filters(raw: str | None, columns: set[str]) -> tuple[str, list]:
    if not raw:
        return "", []
    try:
        items = json.loads(raw)
        assert isinstance(items, list)
    except (ValueError, AssertionError) as exc:
        raise ValidationFailed("filter must be a JSON list of {column, op, value}") from exc
    clauses, params = [], []
    for f in items[:20]:
        col, op = f.get("column"), f.get("op", "eq")
        if col not in columns or op not in FILTER_OPS:
            raise ValidationFailed(f"Invalid filter: {f}")
        ident = quote_ident(col)
        if op == "contains":
            clauses.append(f"CAST({ident} AS VARCHAR) ILIKE ?")
            params.append(f"%{f.get('value', '')}%")
        elif op in ("is_null", "not_null"):
            clauses.append(f"{ident} {FILTER_OPS[op]}")
        else:
            clauses.append(f"{ident} {FILTER_OPS[op]}")
            params.append(f.get("value"))
    return "WHERE " + " AND ".join(clauses), params


def query_rows(
    version: DatasetVersion,
    offset: int,
    limit: int,
    sort: str | None,
    filter_raw: str | None,
    columns: list[str] | None = None,
) -> dict:
    path = str(local_path(version.storage_key))
    con = duckdb.connect()
    try:
        src = "read_parquet(?, file_row_number=true)"
        schema = con.execute(f"DESCRIBE SELECT * FROM {src}", [path]).fetchall()
        all_cols = [(r[0], r[1]) for r in schema if r[0] != "file_row_number"]
        names = {c for c, _ in all_cols}
        if columns:
            all_cols = [(c, t) for c, t in all_cols if c in set(columns)]
        where, params = parse_filters(filter_raw, names)
        order = "ORDER BY file_row_number"
        if sort:
            col, _, direction = sort.rpartition(":") if ":" in sort else (sort, "", "asc")
            if col not in names:
                raise ValidationFailed(f"Unknown sort column '{col}'")
            d = "DESC" if direction.lower() == "desc" else "ASC"
            order = f"ORDER BY {quote_ident(col)} {d} NULLS LAST, file_row_number"
        total = con.execute(f"SELECT count(*) FROM {src} {where}", [path, *params]).fetchone()[0]
        select_cols = ", ".join(quote_ident(c) for c, _ in all_cols)
        rows = con.execute(
            f"SELECT file_row_number, {select_cols} FROM {src} {where} {order} LIMIT ? OFFSET ?",
            [path, *params, limit, offset],
        ).fetchall()
    except duckdb.Error as exc:
        raise ValidationFailed(f"Query failed: {exc}") from exc
    finally:
        con.close()
    return {
        "columns": [{"name": c, "type": t} for c, t in all_cols],
        "rows": [[py_jsonable(v) for v in r[1:]] for r in rows],
        "row_ids": [int(r[0]) for r in rows],
        "total": int(total),
        "offset": offset,
        "limit": limit,
    }
