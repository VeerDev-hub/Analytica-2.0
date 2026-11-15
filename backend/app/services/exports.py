"""Build export artifacts (design 4.4): datasets per partition, code, notebook, templates."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.engine import codegen
from app.engine.readiness import check as readiness_check
from app.engine.transforms import SPLIT_COL
from app.engine.transforms.base import jsonable_state, state_from_bytes
from app.models import Dataset, DatasetSplit, DatasetVersion, Export, Pipeline, Project
from app.services.pipeline import steps_of
from app.storage.backend import get_storage, project_prefix

KINDS = {
    "dataset": ("csv", "parquet", "xlsx", "npy"),
    "script": ("py",),
    "notebook": ("ipynb",),
    "pipeline": ("json",),
    "pytorch": ("py",),
    "tensorflow": ("py",),
    "report": ("html",),
}
EXPORT_TTL = timedelta(days=7)


def pipeline_steps_with_state(db: Session, pipeline: Pipeline) -> list[dict]:
    out = []
    for s in steps_of(db, pipeline):
        if s.status != "applied":
            continue
        state = {}
        if s.fitted_state_key:
            try:
                state = state_from_bytes(get_storage().get_bytes(s.fitted_state_key))
            except Exception:  # noqa: BLE001 - code is still useful without learned values
                state = {}
        out.append(
            {
                "step_type": s.step_type,
                "params": s.params or {},
                "state": state,
                "is_enabled": s.is_enabled,
                "phase": s.phase,
            }
        )
    return out


def _partitions(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if SPLIT_COL not in df.columns:
        return {"data": df}
    return {
        p: df[df[SPLIT_COL] == p].drop(columns=[SPLIT_COL]).reset_index(drop=True)
        for p in ("train", "val", "test")
        if (df[SPLIT_COL] == p).any()
    }


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def build(
    db: Session, export: Export, project: Project, version: DatasetVersion, df: pd.DataFrame
) -> tuple[str, bytes, str]:
    """Return (filename, bytes, content_type)."""
    dataset = db.get(Dataset, version.dataset_id)
    pipeline = db.get(Pipeline, project.current_pipeline_id)
    base = (dataset.name or "dataset").replace(" ", "_")
    target = project.target_column
    kind, fmt = export.kind, export.format
    features = [c for c in df.columns if c not in (SPLIT_COL, target)]
    classification = project.task_type == "classification" or (
        target in df.columns and not pd.api.types.is_numeric_dtype(df[target])
    )

    if kind == "dataset":
        parts = _partitions(df)
        files: dict[str, bytes] = {}
        if fmt == "npy":
            bad = [c for c in features if not pd.api.types.is_numeric_dtype(df[c])]
            if bad:
                raise ValueError(f"NumPy export needs numeric features; encode: {bad[:5]}")
            for name, part in parts.items():
                for prefix, data in (
                    ("X", part[features]),
                    ("y", part[[target]] if target in part else None),
                ):
                    if data is None:
                        continue
                    buf = io.BytesIO()
                    np.save(
                        buf,
                        data.to_numpy(dtype="float64" if prefix == "X" else None),
                        allow_pickle=False,
                    )
                    files[f"{prefix}_{name}.npy"] = buf.getvalue()
            files["features.json"] = json.dumps({"features": features, "target": target}).encode()
        else:
            for name, part in parts.items():
                buf = io.BytesIO()
                if fmt == "csv":
                    part.to_csv(buf, index=False)
                elif fmt == "parquet":
                    part.to_parquet(buf, index=False)
                else:
                    part.to_excel(buf, index=False, engine="openpyxl")
                files[f"{name}.{fmt}"] = buf.getvalue()
        if len(files) == 1:
            name, data = next(iter(files.items()))
            return f"{base}_{name}", data, "application/octet-stream"
        files["README.txt"] = (
            f"Exported from Analytica Studio, project '{project.name}', version "
            f"v{version.version_no}.\nTarget: {target}\nPartitions: {', '.join(parts)}\n"
            "Statistics used by train-fitted steps were learned on train rows only.\n"
        ).encode()
        return f"{base}_{fmt}.zip", _zip(files), "application/zip"

    steps = pipeline_steps_with_state(db, pipeline)
    source = dataset.original_filename or "data.csv"
    if kind == "script":
        code = codegen.to_script(
            steps, title=project.name, source=source, target=target, filename=f"{base}_pipeline.py"
        )
        return f"{base}_pipeline.py", code.encode(), "text/x-python"
    if kind == "notebook":
        return (
            f"{base}_pipeline.ipynb",
            codegen.to_notebook(steps, title=project.name, source=source, target=target),
            "application/json",
        )
    if kind == "pipeline":
        doc = {
            "format": "analytica-pipeline/1",
            "project": project.name,
            "target": target,
            "task_type": project.task_type,
            "steps": [
                {
                    "step_type": s["step_type"],
                    "params": s["params"],
                    "is_enabled": s["is_enabled"],
                    "learned": jsonable_state(s["state"]),
                }
                for s in steps
            ],
        }
        return f"{base}_pipeline.json", json.dumps(doc, indent=2).encode(), "application/json"
    if kind in ("pytorch", "tensorflow"):
        fn = codegen.pytorch_template if kind == "pytorch" else codegen.tensorflow_template
        files = {f"train_{kind}.py": fn(features, target, classification).encode()}
        for name, part in _partitions(df).items():
            buf = io.BytesIO()
            part.to_parquet(buf, index=False)
            files[f"{name}.parquet"] = buf.getvalue()
        return f"{base}_{kind}.zip", _zip(files), "application/zip"
    if kind == "report":
        rep = readiness_check(df, target, project.task_type)
        return f"{base}_report.html", _report_html(project, version, rep).encode(), "text/html"
    raise ValueError(f"Unknown export kind {kind}")


def _report_html(project: Project, version: DatasetVersion, rep: dict) -> str:
    from html import escape

    prof = version.profile or {}
    s = prof.get("summary", {})
    rows = "".join(
        f"<tr><td>{escape(c['label'])}</td><td class='{c['status']}'>{c['status']}</td>"
        f"<td>{escape(c['detail'])}</td></tr>"
        for c in rep["checks"]
    )
    alerts = "".join(
        f"<li><b>{escape(a['severity'])}</b> {escape(a['message'])}</li>"
        for a in prof.get("alerts", [])
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(project.name)} report</title>
<style>body{{font:14px system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;
color:#0f172a;background:#fff}}td,th{{padding:4px 8px;border-bottom:1px solid #e2e8f0;
text-align:left}}table{{border-collapse:collapse;width:100%}}.pass{{color:#15803d}}
.warn{{color:#b45309}}.fail{{color:#dc2626}}</style></head><body>
<h1>{escape(project.name)}</h1><p>Version v{version.version_no} · {version.row_count:,} rows ×
{version.column_count} columns · target: {escape(str(project.target_column))}</p>
<h2>ML readiness: {rep["score"]}% {"(ready)" if rep["ready"] else "(not ready)"}</h2>
<table><tr><th>Check</th><th>Status</th><th>Detail</th></tr>{rows}</table>
<h2>Data quality</h2><p>Missing cells {s.get("missing_pct", 0)}% · duplicate rows
{s.get("duplicate_rows", 0)}</p><ul>{alerts}</ul>
<p style="color:#64748b">Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by Analytica Studio
</p></body></html>"""


def finish(
    db: Session, export: Export, project: Project, version: DatasetVersion, df: pd.DataFrame
) -> None:
    filename, data, ctype = build(db, export, project, version, df)
    key = f"{project_prefix(project.owner_id, project.id)}exports/{export.id}/{filename}"
    get_storage().put_bytes(key, data, ctype)
    export.storage_key = key
    export.size_bytes = len(data)
    export.status = "ready"
    export.expires_at = datetime.now(UTC) + EXPORT_TTL
    if export.kind == "dataset" and SPLIT_COL in df.columns:
        _record_split(db, project, version, df)


def _record_split(db: Session, project: Project, version: DatasetVersion, df: pd.DataFrame) -> None:
    """Persist train/val/test Parquet files once per version (dataset_splits table)."""
    from sqlalchemy import select

    if db.scalars(select(DatasetSplit).where(DatasetSplit.version_id == version.id)).first():
        return
    pipeline = db.get(Pipeline, project.current_pipeline_id)
    split = DatasetSplit(version_id=version.id, config=pipeline.split_config or {}, train_key="")
    db.add(split)
    db.flush()
    prefix = f"{project_prefix(project.owner_id, project.id)}splits/{split.id}/"
    keys = {}
    for name, part in _partitions(df).items():
        buf = io.BytesIO()
        part.to_parquet(buf, index=False)
        keys[name] = f"{prefix}{name}.parquet"
        get_storage().put_bytes(keys[name], buf.getvalue())
    split.train_key = keys.get("train", "")
    split.val_key, split.test_key = keys.get("val"), keys.get("test")
    target = project.target_column
    if target and target in df.columns:
        split.class_distribution = {
            name: {str(k): int(v) for k, v in part[target].value_counts().head(50).items()}
            for name, part in _partitions(df).items()
        }
