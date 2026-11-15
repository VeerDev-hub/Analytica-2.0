"""Object storage abstraction (design 3.6). S3Storage in AWS/local stack, LocalStorage in tests.

Key layout (design 2.4), always prefixed by owner and project for isolation (rule 7):

    users/{user_id}/projects/{project_id}/raw/{dataset_id}/{filename}
    users/{user_id}/projects/{project_id}/datasets/{dataset_id}/v{n}.parquet
    users/{user_id}/projects/{project_id}/states/{step_id}.joblib
    users/{user_id}/projects/{project_id}/splits/{split_id}/{train|val|test}.parquet
    users/{user_id}/projects/{project_id}/exports/{export_id}/{filename}
"""

from __future__ import annotations

import shutil
import uuid
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings


def project_prefix(user_id: uuid.UUID, project_id: uuid.UUID) -> str:
    return f"users/{user_id}/projects/{project_id}/"


class StorageBackend(ABC):
    @abstractmethod
    def put_file(self, key: str, path: str | Path, content_type: str | None = None) -> int: ...

    @abstractmethod
    def put_fileobj(self, key: str, fileobj: BinaryIO, content_type: str | None = None) -> None: ...

    @abstractmethod
    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None: ...

    @abstractmethod
    def get_bytes(self, key: str) -> bytes: ...

    @abstractmethod
    def download(self, key: str, dest: str | Path) -> Path: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete_prefix(self, prefix: str) -> int: ...

    @abstractmethod
    def presign_get(self, key: str, filename: str, expires_s: int = 300) -> str | None:
        """Short-lived download URL, or None if the backend cannot presign (local)."""


class S3Storage(StorageBackend):
    def __init__(self) -> None:
        from app.storage.s3 import get_s3_client

        self.client = get_s3_client()
        self.bucket = get_settings().s3_bucket

    def put_file(self, key, path, content_type=None):
        extra = {"ContentType": content_type} if content_type else None
        self.client.upload_file(str(path), self.bucket, key, ExtraArgs=extra)
        return Path(path).stat().st_size

    def put_fileobj(self, key, fileobj, content_type=None):
        extra = {"ContentType": content_type} if content_type else None
        self.client.upload_fileobj(fileobj, self.bucket, key, ExtraArgs=extra)

    def put_bytes(self, key, data, content_type=None):
        kwargs = {"ContentType": content_type} if content_type else {}
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, **kwargs)

    def get_bytes(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def download(self, key, dest):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + f".{uuid.uuid4().hex}.part")
        self.client.download_file(self.bucket, key, str(tmp))
        tmp.replace(dest)  # atomic: concurrent readers never see a half-written file
        return dest

    def exists(self, key):
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete_prefix(self, prefix):
        deleted = 0
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objs:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objs})
                deleted += len(objs)
        return deleted

    def presign_get(self, key, filename, expires_s=300):
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
            },
            ExpiresIn=expires_s,
        )


class LocalStorage(StorageBackend):
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or get_settings().local_storage_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("key escapes storage root")
        return p

    def put_file(self, key, path, content_type=None):
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        return dest.stat().st_size

    def put_fileobj(self, key, fileobj, content_type=None):
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as fh:
            shutil.copyfileobj(fileobj, fh)

    def put_bytes(self, key, data, content_type=None):
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def get_bytes(self, key):
        return self._path(key).read_bytes()

    def download(self, key, dest):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self._path(key), dest)
        return dest

    def exists(self, key):
        return self._path(key).exists()

    def delete_prefix(self, prefix):
        base = self._path(prefix)
        if base.is_dir():
            n = sum(1 for p in base.rglob("*") if p.is_file())
            shutil.rmtree(base)
            return n
        if base.is_file():
            base.unlink()
            return 1
        return 0

    def presign_get(self, key, filename, expires_s=300):
        return None


@lru_cache
def get_storage() -> StorageBackend:
    return LocalStorage() if get_settings().storage_backend == "local" else S3Storage()
