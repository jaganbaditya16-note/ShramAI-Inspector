"""Storage backend contract tests.

The S3 adapter is exercised against an in-repo fake botocore client (no
network, no moto); the same contract suite runs against both backends so the
local-disk implementation and the S3 implementation are provably
interchangeable. Covers: upload, download, exists, delete, metadata,
integrity (byte-exact roundtrip + sha256), missing objects, storage
failures, traversal guards, private-by-default writes, presign TTL clamps
and credential non-leakage.
"""

from __future__ import annotations

import hashlib
import io

import pytest
from app.core.config import settings
from app.services.storage import (
    DocumentStore,
    InvalidStorageKey,
    LocalDiskStore,
    MissingObjectError,
    S3Store,
    StorageError,
    is_valid_key,
    reset_store,
)
from botocore.exceptions import ClientError

# --- fake botocore client -------------------------------------------------------------


class FakeBody(io.BytesIO):
    """Minimal stand-in for botocore's StreamingBody."""


class FakeS3Client:
    """Implements the botocore client surface used by S3Store, in memory."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.heads: dict[str, dict] = {}
        self.calls: list[tuple[str, dict]] = []
        self.fail_on: set[str] = set()  # operation names to fail with ServiceError

    def _fail(self, op: str) -> None:
        if op in self.fail_on:
            raise ClientError(
                {"Error": {"Code": "ServiceUnavailable", "Message": "backend down"}}, op
            )

    def put_object(self, **kwargs) -> dict:
        self.calls.append(("put_object", kwargs))
        self._fail("put_object")
        self.objects[kwargs["Key"]] = kwargs["Body"]
        return {}

    def get_object(self, **kwargs) -> dict:
        self.calls.append(("get_object", kwargs))
        self._fail("get_object")
        key = kwargs["Key"]
        if key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}, "GetObject")
        return {"Body": FakeBody(self.objects[key])}

    def head_object(self, **kwargs) -> dict:
        self.calls.append(("head_object", kwargs))
        self._fail("head_object")
        key = kwargs["Key"]
        if key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")
        meta = self.heads.get(key, {})
        return {
            "ContentLength": len(self.objects[key]),
            "ETag": meta.get("ETag", '"etag-123"'),
            "LastModified": meta.get("LastModified"),
            "ContentType": meta.get("ContentType"),
        }

    def delete_object(self, **kwargs) -> dict:
        self.calls.append(("delete_object", kwargs))
        self._fail("delete_object")
        self.objects.pop(kwargs["Key"], None)  # idempotent by contract
        return {}

    def generate_presigned_url(self, ClientMethod: str, Params: dict, ExpiresIn: int) -> str:
        self.calls.append((ClientMethod, {**Params, "ExpiresIn": ExpiresIn}))
        return (
            f"https://signed.example/{Params['Bucket']}/{Params['Key']}"
            f"?X-Amz-Expires={ExpiresIn}&X-Amz-Signature=tok"
        )


@pytest.fixture
def fake_s3() -> FakeS3Client:
    return FakeS3Client()


@pytest.fixture
def s3_store(fake_s3) -> S3Store:
    return S3Store(
        bucket="docs-bucket",
        access_key_id="AKID-EXAMPLE",
        secret_access_key="wJalrXUtnFEMI-example-secret",
        client=fake_s3,
    )


@pytest.fixture
def local_store(tmp_path) -> LocalDiskStore:
    return LocalDiskStore(str(tmp_path / "store"))


SECRET = "wJalrXUtnFEMI-example-secret"


# --- S3 adapter specifics --------------------------------------------------------


def test_s3_save_uses_server_generated_key_and_no_public_acl(s3_store, fake_s3):
    key = s3_store.save(b"payload", ".pdf")
    assert is_valid_key(key)
    op, kwargs = fake_s3.calls[0]
    assert op == "put_object"
    assert kwargs["Bucket"] == "docs-bucket" and kwargs["Key"] == key
    assert "ACL" not in kwargs  # private by default; never grants public read
    assert "WebsiteRedirectLocation" not in kwargs


def test_s3_save_applies_server_side_encryption_when_configured(fake_s3):
    store = S3Store(
        bucket="b", access_key_id="a", secret_access_key="s",
        server_side_encryption="AES256", client=fake_s3,
    )
    key = store.save(b"x", ".pdf")
    _, kwargs = fake_s3.calls[0]
    assert kwargs["ServerSideEncryption"] == "AES256"
    assert store.exists(key)


def test_s3_get_bytes_roundtrip_and_integrity(s3_store):
    data = b"%PDF-1.4 exact-bytes-roundtrip \x00\xff"
    key = s3_store.save(data, ".pdf")
    fetched = s3_store.get_bytes(key)
    assert fetched == data  # byte-exact
    assert hashlib.sha256(fetched).hexdigest() == hashlib.sha256(data).hexdigest()


def test_s3_missing_object_raises_missing(s3_store):
    with pytest.raises(MissingObjectError):
        s3_store.get_bytes("2026/09/" + "a" * 32 + ".pdf")


def test_s3_backend_failure_maps_to_storage_error_without_leaking(s3_store, fake_s3):
    fake_s3.fail_on.update({"put_object", "get_object", "head_object", "delete_object"})
    with pytest.raises(StorageError) as exc_info:
        s3_store.save(b"x", ".pdf")
    assert SECRET not in str(exc_info.value)
    assert SECRET not in repr(s3_store)
    with pytest.raises(StorageError):
        s3_store.get_bytes("2026/09/" + "a" * 32 + ".pdf")
    with pytest.raises(StorageError):
        s3_store.exists("2026/09/" + "a" * 32 + ".pdf")
    with pytest.raises(StorageError):
        s3_store.delete("2026/09/" + "a" * 32 + ".pdf")


def test_s3_delete_is_idempotent(s3_store):
    key = s3_store.save(b"gone", ".pdf")
    s3_store.delete(key)
    s3_store.delete(key)  # missing object: still a successful no-op
    assert not s3_store.exists(key)
    with pytest.raises(MissingObjectError):
        s3_store.get_bytes(key)


def test_s3_stat_returns_safe_metadata(s3_store, fake_s3):
    data = b"meta-bytes"
    key = s3_store.save(data, ".pdf")
    meta = s3_store.stat(key)
    assert meta is not None
    assert meta.key == key
    assert meta.size_bytes == len(data)
    assert meta.etag == "etag-123"
    assert s3_store.stat("2026/09/" + "b" * 32 + ".pdf") is None


@pytest.mark.parametrize(
    "bad_key",
    ["../escape.pdf", "/etc/passwd", "2026/09/../../etc/passwd.pdf", "nodate.pdf", ""],
)
def test_invalid_keys_rejected_before_any_backend_call(s3_store, fake_s3, bad_key):
    for operation in (
        lambda: s3_store.get_bytes(bad_key),
        lambda: s3_store.exists(bad_key),
        lambda: s3_store.delete(bad_key),
        lambda: s3_store.stat(bad_key),
        lambda: s3_store.open_path(bad_key),
        lambda: s3_store.presign_get(bad_key, 300),
    ):
        with pytest.raises(InvalidStorageKey):
            operation()
    assert fake_s3.calls == []  # never reached the backend


def test_s3_presign_ttl_is_clamped_and_url_is_short_lived(s3_store, fake_s3):
    key = s3_store.save(b"x", ".pdf")
    fake_s3.calls.clear()
    url = s3_store.presign_get(key, 100000)
    assert url is not None and "X-Amz-Signature" in url
    _, kwargs = fake_s3.calls[0]
    assert kwargs["ExpiresIn"] == 3600  # clamped to the maximum window
    fake_s3.calls.clear()
    s3_store.presign_get(key, 5)
    assert fake_s3.calls[0][1]["ExpiresIn"] == 30  # clamped to the minimum window


def test_local_store_presign_is_unsupported(local_store):
    key = local_store.save(b"x", ".pdf")
    assert local_store.presign_get(key, 300) is None  # caller must stream


def test_factory_builds_s3_backend_from_env(monkeypatch, fake_s3):
    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_bucket", "env-bucket")
    import app.services.storage as storage_pkg

    real_s3_init = S3Store.__init__
    captured: dict = {}

    def spy(self, **kwargs):
        captured.update(kwargs)
        real_s3_init(self, client=fake_s3, **{k: v for k, v in kwargs.items() if k != "client"})

    monkeypatch.setattr(S3Store, "__init__", spy)
    reset_store()
    store = storage_pkg.get_store()
    assert isinstance(store, S3Store)
    assert store.bucket == "env-bucket"
    assert captured["access_key_id"] == settings.s3_access_key_id
    reset_store()


# --- shared contract for both backends -------------------------------------------


@pytest.mark.parametrize("store_name", ["local_store", "s3_store"])
def test_contract_upload_download_delete_metadata(store_name, request):
    store: DocumentStore = request.getfixturevalue(store_name)
    data = f"contract-{store_name}".encode()

    key = store.save(data, ".pdf")  # upload
    assert is_valid_key(key)
    assert store.exists(key) is True
    assert store.get_bytes(key) == data  # download + integrity
    assert hashlib.sha256(store.get_bytes(key)).hexdigest() == hashlib.sha256(data).hexdigest()

    meta = store.stat(key)  # metadata
    assert meta is not None and meta.size_bytes == len(data) and meta.key == key

    store.delete(key)  # delete
    assert store.exists(key) is False
    with pytest.raises(MissingObjectError):
        store.get_bytes(key)
    assert store.stat(key) is None


@pytest.mark.parametrize("store_name", ["local_store", "s3_store"])
def test_contract_keys_are_uncollidable_and_server_generated(store_name, request):
    store: DocumentStore = request.getfixturevalue(store_name)
    key_a = store.save(b"1", ".pdf")
    key_b = store.save(b"2", ".pdf")
    assert key_a != key_b


def test_local_open_path_stays_within_root(local_store):
    key = local_store.save(b"local-bytes", ".pdf")
    path = local_store.open_path(key)
    assert path.is_file() and path.read_bytes() == b"local-bytes"
    assert str(path).startswith(str(local_store.root))
    with pytest.raises(InvalidStorageKey):
        local_store.open_path("../escape.pdf")


def test_s3_open_path_materialises_temp_file_and_discards(s3_store):
    key = s3_store.save(b"temp-materialisation", ".pdf")
    assert s3_store.ephemeral_paths is True
    path = s3_store.open_path(key)
    try:
        assert path.read_bytes() == b"temp-materialisation"
    finally:
        s3_store.discard_path(path)
    assert not path.exists()
