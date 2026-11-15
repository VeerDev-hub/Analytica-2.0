"""Read-only SQL sandbox over one Parquet snapshot (design 5.5 "Chat safety").

- The version is copied into an in-memory DuckDB table named `data`; private columns are
  never loaded, so no query can reveal them.
- External access (files, network, extensions) is then disabled and the configuration
  locked, so a query cannot read anything else on disk.
- Only a single SELECT / WITH statement is accepted; results are capped in rows, time
  and memory.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass

import duckdb

from app.services.rows import py_jsonable, quote_ident

MAX_ROWS = 200
TIMEOUT_S = 10
_FORBIDDEN = re.compile(
    r"\b(attach|detach|copy|export|import|install|load|pragma|set|reset|call|create|insert|"
    r"update|delete|drop|alter|vacuum|checkpoint|read_csv\w*|read_parquet|read_json\w*|"
    r"read_text|read_blob|glob|httpfs)\b",
    re.I,
)


class SqlError(ValueError):
    pass


@dataclass
class SqlResult:
    sql: str
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool

    def to_dict(self) -> dict:
        return {
            "sql": self.sql,
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "truncated": self.truncated,
        }


def clean_sql(sql: str) -> str:
    s = re.sub(r"--[^\n]*", " ", sql or "")
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S).strip().rstrip(";").strip()
    if not s:
        raise SqlError("Empty query")
    if ";" in s:
        raise SqlError("Only one statement is allowed")
    if not re.match(r"^(select|with)\b", s, re.I):
        raise SqlError("Only SELECT queries are allowed")
    if _FORBIDDEN.search(s):
        raise SqlError("The query uses a command that is not allowed; query the table `data`")
    return s


class SqlSandbox:
    def __init__(
        self,
        parquet_path: str,
        private_columns: set[str] | None = None,
        drop_columns: set[str] | None = None,
    ):
        self.con = duckdb.connect(":memory:", config={"threads": 2, "memory_limit": "1GB"})
        cols = [
            r[0]
            for r in self.con.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [parquet_path]
            ).fetchall()
        ]
        hidden = (private_columns or set()) | (drop_columns or set())
        keep = [c for c in cols if c not in hidden]
        if not keep:
            raise SqlError("No queryable columns")
        select = ", ".join(quote_ident(c) for c in keep)
        self.con.execute(
            f"CREATE TABLE data AS SELECT {select} FROM read_parquet(?)", [parquet_path]
        )
        self.con.execute("SET enable_external_access = false")
        self.con.execute("SET lock_configuration = true")
        self.columns = keep

    def run(self, sql: str, max_rows: int = MAX_ROWS) -> SqlResult:
        q = clean_sql(sql)
        timer = threading.Timer(TIMEOUT_S, self.con.interrupt)
        timer.start()
        try:
            cur = self.con.execute(f"SELECT * FROM ({q}) AS _q LIMIT {max_rows + 1}")
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
        except duckdb.InterruptException as e:
            raise SqlError(f"Query took longer than {TIMEOUT_S}s") from e
        except duckdb.Error as e:
            raise SqlError(str(e).split("\n")[0][:300]) from e
        finally:
            timer.cancel()
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        return SqlResult(
            sql=q,
            columns=cols,
            rows=[[py_jsonable(v) for v in r] for r in rows],
            row_count=len(rows),
            truncated=truncated,
        )

    def close(self) -> None:
        self.con.close()
