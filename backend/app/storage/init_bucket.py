"""Create the data bucket if missing. Local/dev only; in AWS the bucket comes from Terraform.

Run with:  python -m app.storage.init_bucket
"""

import logging
import sys
import time

from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.storage.s3 import get_s3_client

logger = logging.getLogger(__name__)


def ensure_bucket(attempts: int = 30, delay_s: float = 2.0) -> None:
    bucket = get_settings().s3_bucket
    client = get_s3_client()
    for attempt in range(1, attempts + 1):
        try:
            client.head_bucket(Bucket=bucket)
            logger.info("bucket %s already exists", bucket)
            return
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchBucket"):
                client.create_bucket(Bucket=bucket)
                logger.info("created bucket %s", bucket)
                return
            last = exc
        except BotoCoreError as exc:  # storage not accepting connections yet
            last = exc
        logger.info("storage not ready (attempt %d/%d): %s", attempt, attempts, last)
        time.sleep(delay_s)
    raise SystemExit(f"could not reach object storage to create bucket {bucket!r}")


if __name__ == "__main__":
    configure_logging(get_settings().log_level)
    if get_settings().environment not in ("local", "dev", "test"):
        sys.exit("init_bucket is for local/dev only")
    ensure_bucket()
