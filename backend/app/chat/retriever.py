"""Retrieval over the project's data dictionary and text cells (design D-10).

Chunks live in `embedding_chunks`. Embeddings need a separate provider (open question 4 in
the design), so until one is configured the `embedding` column stays NULL and retrieval uses
PostgreSQL full-text ranking. When vectors exist, pgvector cosine search is used instead.
Numbers never come from here: aggregates always go through the SQL tool.
"""

from __future__ import annotations

import uuid

import pandas as pd
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.models import ColumnProfile, DatasetVersion, EmbeddingChunk, Project

MAX_TEXT_CHUNKS = 300


def index_version(
    db: Session, project: Project, version: DatasetVersion, df: pd.DataFrame | None = None
) -> int:
    """(Re)build chunks for a version: one per column doc, plus sampled text cells."""
    db.execute(
        delete(EmbeddingChunk).where(
            EmbeddingChunk.project_id == project.id, EmbeddingChunk.version_id == version.id
        )
    )
    cols = list(
        db.scalars(
            select(ColumnProfile)
            .where(ColumnProfile.version_id == version.id)
            .order_by(ColumnProfile.position)
        )
    )
    n = 0
    for c in cols:
        if c.is_private:
            content = f"Column {c.name}: private (values hidden)."
        else:
            s = c.stats or {}
            top = ", ".join(t["value"] for t in s.get("top_values", [])[:8])
            rng = f" range {s.get('min')} to {s.get('max')}." if s.get("min") is not None else ""
            content = (
                f"Column {c.name} ({c.semantic_type}, {c.dtype}). "
                f"{c.description or ''} Missing {s.get('missing_pct', 0)}%. "
                f"{c.unique_count} distinct values.{rng}"
                + (f" Common values: {top}." if top else "")
            )
        db.add(
            EmbeddingChunk(
                project_id=project.id,
                version_id=version.id,
                source_type="column_doc",
                content=content,
                meta={"column": c.name},
            )
        )
        n += 1
    if df is not None:
        text_cols = [
            c.name
            for c in cols
            if c.semantic_type == "text" and not c.is_private and c.name in df.columns
        ]
        for col in text_cols:
            vals = df[col].dropna().astype(str)
            sample = vals.sample(
                min(len(vals), MAX_TEXT_CHUNKS // max(len(text_cols), 1)), random_state=0
            )
            for idx, v in sample.items():
                db.add(
                    EmbeddingChunk(
                        project_id=project.id,
                        version_id=version.id,
                        source_type="text_cell",
                        content=v[:2000],
                        meta={"column": col, "row": int(idx)},
                    )
                )
                n += 1
    db.flush()
    return n


def ensure_indexed(
    db: Session, project: Project, version: DatasetVersion, df: pd.DataFrame | None = None
) -> None:
    exists = db.scalar(
        select(func.count())
        .select_from(EmbeddingChunk)
        .where(EmbeddingChunk.version_id == version.id)
    )
    if not exists:
        index_version(db, project, version, df)


def search(
    db: Session, project_id: uuid.UUID, version_id: uuid.UUID, query: str, k: int = 8
) -> list[dict]:
    q = (query or "").strip()[:300]
    if not q:
        return []
    rows = db.execute(
        text("""
        SELECT source_type, content, metadata,
               ts_rank(to_tsvector('english', content), websearch_to_tsquery('english', :q))
                 AS rank
        FROM embedding_chunks
        WHERE project_id = :p AND version_id = :v
          AND to_tsvector('english', content) @@ websearch_to_tsquery('english', :q)
        ORDER BY rank DESC LIMIT :k
    """),
        {"q": q, "p": project_id, "v": version_id, "k": k},
    ).all()
    if not rows:  # fall back to substring match on any word
        words = [w for w in q.split() if len(w) > 2][:5]
        if words:
            cond = " OR ".join(f"content ILIKE :w{i}" for i in range(len(words)))
            params = {f"w{i}": f"%{w}%" for i, w in enumerate(words)}
            rows = db.execute(
                text(
                    f"SELECT source_type, content, metadata, 0.0 AS rank FROM embedding_chunks "
                    f"WHERE project_id = :p AND version_id = :v AND ({cond}) LIMIT :k"
                ),
                {"p": project_id, "v": version_id, "k": k, **params},
            ).all()
    return [{"source": r[0], "content": r[1], "meta": r[2]} for r in rows]
