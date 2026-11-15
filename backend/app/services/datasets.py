"""Upload a file: stream to storage under raw/, create dataset + ingest job (design 4.2).

Files are parsed only in the worker, never in the API process (design 5.5).
"""

from __future__ import annotations

import hashlib
import re
import tempfile
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.errors import AppError, ValidationFailed
from app.engine.loaders import LoadError, detect_format
from app.models import Dataset, Project, User
from app.services import jobs as job_service
from app.storage.backend import get_storage, project_prefix

CHUNK = 1024 * 1024


def safe_filename(name: str) -> str:
    base = Path(name or "upload").name
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip() or "upload"
    return base[:200]


def upload_dataset(
    db: Session, user: User, project: Project, file: UploadFile, options: dict
) -> tuple[Dataset, uuid.UUID]:
    filename = safe_filename(file.filename or "upload.csv")
    try:
        fmt = detect_format(filename)
    except LoadError as exc:
        raise ValidationFailed(str(exc), code="UNSUPPORTED_FILE") from exc

    from app.services import app_settings

    max_mb = int(app_settings.get(db, "max_upload_mb"))
    limit = max_mb * 1024 * 1024
    sha = hashlib.sha256()
    size = 0
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        while chunk := file.file.read(CHUNK):
            size += len(chunk)
            if size > limit:
                tmp.close()
                Path(tmp.name).unlink(missing_ok=True)
                raise AppError(
                    f"File is larger than {max_mb} MB",
                    code="FILE_TOO_LARGE",
                    status_code=413,
                )
            sha.update(chunk)
            tmp.write(chunk)
    if size == 0:
        Path(tmp.name).unlink(missing_ok=True)
        raise ValidationFailed("The file is empty", code="EMPTY_FILE")

    from app.services.quota import QuotaExceeded, ensure_room

    try:
        ensure_room(db, user, size)
    except QuotaExceeded:
        Path(tmp.name).unlink(missing_ok=True)
        raise

    dataset_id = uuid.uuid4()
    key = f"{project_prefix(user.id, project.id)}raw/{dataset_id}/{filename}"
    try:
        get_storage().put_file(key, tmp.name)
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    dataset = Dataset(
        id=dataset_id,
        project_id=project.id,
        name=Path(filename).stem,
        source_type="upload",
        original_filename=filename,
        original_format=fmt,
        original_sha256=sha.hexdigest(),
        original_size_bytes=size,
        original_storage_key=key,
        sheet_name=options.get("sheet_name"),
        load_options=options,
    )
    db.add(dataset)
    db.flush()
    job = job_service.create_job(
        db,
        project_id=project.id,
        user_id=user.id,
        job_type="ingest",
        params={"dataset_id": str(dataset.id), "filename": filename},
    )
    from app.tasks.ingest import task_ingest

    job_service.enqueue(db, job, task_ingest)
    return dataset, job.id
