import uuid

from fastapi import APIRouter, Query

from app.api.deps import DB, CurrentUser
from app.core.errors import ValidationFailed
from app.engine.charts import ChartError, column_detail, from_spec
from app.engine.profiling import correlations
from app.repositories.access import get_version
from app.schemas.pipeline import ChartSpec
from app.services.versions import load_version_df

router = APIRouter(tags=["eda"])


@router.get("/versions/{version_id}/columns/{name}/detail")
def detail(version_id: uuid.UUID, name: str, user: CurrentUser, db: DB) -> dict:
    v, _, project = get_version(db, user, version_id)
    df = load_version_df(v)
    try:
        return column_detail(df, name, project.target_column)
    except ChartError as e:
        raise ValidationFailed(str(e)) from e


@router.post("/versions/{version_id}/chart")
def chart(version_id: uuid.UUID, spec: ChartSpec, user: CurrentUser, db: DB) -> dict:
    v, _, _ = get_version(db, user, version_id)
    cols = [c for c in (spec.x, spec.y, spec.color) if c]
    known = {c["name"] for c in v.schema_snapshot}
    unknown = [c for c in cols if c not in known]
    if unknown:
        raise ValidationFailed(f"Unknown column '{unknown[0]}'", code="CHART_INVALID")
    df = load_version_df(v, columns=cols or None) if spec.kind != "heatmap" else load_version_df(v)
    try:
        return from_spec(df, spec.model_dump(exclude_none=True))
    except ChartError as e:
        raise ValidationFailed(str(e), code="CHART_INVALID") from e


@router.get("/versions/{version_id}/correlations")
def corr(
    version_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    method: str = Query("pearson", pattern="^(pearson|spearman|kendall)$"),
) -> dict:
    v, _, _ = get_version(db, user, version_id)
    return correlations(load_version_df(v).drop(columns=["__split__"], errors="ignore"), method)
