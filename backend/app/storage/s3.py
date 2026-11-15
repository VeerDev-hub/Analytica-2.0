"""S3 client factory. SeaweedFS is used locally; AWS S3 in deployed environments.

The full `StorageBackend` / `S3Storage` / `LocalStorage` classes (design 3.6) arrive in Phase 1.
"""

from functools import lru_cache

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from app.core.config import get_settings


@lru_cache
def get_s3_client() -> BaseClient:
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url or None,
        region_name=s.s3_region,
        aws_access_key_id=s.aws_access_key_id,
        aws_secret_access_key=s.aws_secret_access_key,
        config=Config(
            signature_version="s3v4",
            connect_timeout=2,
            read_timeout=5,
            retries={"max_attempts": 1},
            s3={"addressing_style": "path"},
        ),
    )
