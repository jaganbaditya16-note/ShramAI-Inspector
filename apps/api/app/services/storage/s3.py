"""S3-compatible object-storage backend (AWS S3, MinIO, Cloudflare R2, ...).

Security posture:

- Objects are private by default: ``put_object`` never sets a public ACL and
  buckets are expected to block public access at the provider side.
- No public URLs are ever built. The only signed surface is an optional,
  short-lived presigned GET (``presign_get``), used only when explicitly
  enabled; the default download path streams through the authorised API.
- Credentials come exclusively from environment configuration; they are never
  hard-coded, never logged, and never included in error messages or ``repr``.
- Keys are validated against the server-generated shape before every call, so
  no client value can traverse paths or address another tenant's prefix.
"""

from __future__ import annotations

import logging
from typing import Any

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from .base import (
    DocumentStore,
    MissingObjectError,
    ObjectMeta,
    StorageError,
    _checked,
    new_key,
)

logger = logging.getLogger("shramai.storage")

_CONNECT_TIMEOUT = 10
_READ_TIMEOUT = 60
_MISSING_CODES = {"NoSuchKey", "404", "NotFound"}


def _error_code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


class S3Store(DocumentStore):
    """Stores document originals in a private S3-compatible bucket.

    ``client`` may be injected in tests; production builds a botocore client
    from environment configuration (see ``app.core.config``).
    """

    ephemeral_paths = True

    def __init__(
        self,
        *,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        session_token: str = "",
        endpoint_url: str = "",
        region: str = "",
        server_side_encryption: str = "",
        client: Any | None = None,
    ) -> None:
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.server_side_encryption = server_side_encryption
        if client is not None:
            self._client = client
        else:
            import boto3

            self._client = boto3.client(
                "s3",
                endpoint_url=endpoint_url or None,
                region_name=region or None,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                aws_session_token=session_token or None,
                config=Config(
                    signature_version="s3v4",
                    connect_timeout=_CONNECT_TIMEOUT,
                    read_timeout=_READ_TIMEOUT,
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )

    def __repr__(self) -> str:  # credentials and endpoint never leak
        return f"<S3Store bucket={self.bucket!r}>"

    # --- write -----------------------------------------------------------------

    def save(self, data: bytes, suffix: str) -> str:
        key = new_key(suffix)
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": key, "Body": data}
        if self.server_side_encryption:
            params["ServerSideEncryption"] = self.server_side_encryption
        try:
            self._client.put_object(**params)
        except (ClientError, BotoCoreError, OSError) as exc:
            logger.error("event=storage_put_failed bucket=%s phase=write", self.bucket)
            raise StorageError(
                "The storage backend rejected the write."
            ) from exc
        return key

    # --- read ------------------------------------------------------------------

    def get_bytes(self, key: str) -> bytes:
        checked = _checked(key)
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=checked)
            return response["Body"].read()
        except ClientError as exc:
            if _error_code(exc) in _MISSING_CODES:
                raise MissingObjectError("Object not found.") from exc
            logger.error("event=storage_get_failed bucket=%s phase=read", self.bucket)
            raise StorageError("The storage backend could not read the object.") from exc
        except (BotoCoreError, OSError) as exc:
            logger.error("event=storage_get_failed bucket=%s phase=read", self.bucket)
            raise StorageError("The storage backend could not read the object.") from exc

    def exists(self, key: str) -> bool:
        checked = _checked(key)
        try:
            self._client.head_object(Bucket=self.bucket, Key=checked)
            return True
        except ClientError as exc:
            if _error_code(exc) in _MISSING_CODES:
                return False
            logger.error("event=storage_head_failed bucket=%s phase=head", self.bucket)
            raise StorageError("The storage backend could not be reached.") from exc
        except (BotoCoreError, OSError) as exc:
            logger.error("event=storage_head_failed bucket=%s phase=head", self.bucket)
            raise StorageError("The storage backend could not be reached.") from exc

    def stat(self, key: str) -> ObjectMeta | None:
        checked = _checked(key)
        try:
            head = self._client.head_object(Bucket=self.bucket, Key=checked)
        except ClientError as exc:
            if _error_code(exc) in _MISSING_CODES:
                return None
            logger.error("event=storage_head_failed bucket=%s phase=head", self.bucket)
            raise StorageError("The storage backend could not be reached.") from exc
        except (BotoCoreError, OSError) as exc:
            logger.error("event=storage_head_failed bucket=%s phase=head", self.bucket)
            raise StorageError("The storage backend could not be reached.") from exc
        return ObjectMeta(
            key=checked,
            size_bytes=int(head.get("ContentLength", 0)),
            etag=str(head.get("ETag", "")).strip('"') or None,
            last_modified=head.get("LastModified"),
            content_type=head.get("ContentType"),
        )

    # --- delete / signing --------------------------------------------------------

    def delete(self, key: str) -> None:
        """DeleteObject is idempotent: a missing object is a successful delete."""
        checked = _checked(key)
        try:
            self._client.delete_object(Bucket=self.bucket, Key=checked)
        except (ClientError, BotoCoreError, OSError) as exc:
            logger.error("event=storage_delete_failed bucket=%s phase=delete", self.bucket)
            raise StorageError("The storage backend could not delete the object.") from exc

    def presign_get(self, key: str, ttl_seconds: int) -> str | None:
        """Short-lived signed GET URL (sigv4). Only invoked when the operator
        explicitly enables presigned downloads; never for public sharing."""
        checked = _checked(key)
        ttl = max(30, min(int(ttl_seconds), 3600))
        try:
            return self._client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket, "Key": checked},
                ExpiresIn=ttl,
            )
        except (ClientError, BotoCoreError, OSError) as exc:
            logger.error("event=storage_presign_failed bucket=%s phase=presign", self.bucket)
            raise StorageError("The storage backend could not sign the URL.") from exc
