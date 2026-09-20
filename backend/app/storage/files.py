import hashlib
import os
import re
from pathlib import Path
from uuid import UUID, uuid4
from ..config import get_settings
from ..utils.errors import AppError

def sanitize_filename(name: str) -> str:
    name = str(name).replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:160] or "dataset.csv"

def safe_path(area: str, identity: str, suffix: str) -> Path:
    if area not in {"data/datasets", "models", "experiments"} or suffix not in {".csv", ".dill", ".json", ".html"}:
        raise AppError("invalid_path", "Unsupported storage location.")
    try:
        identity = str(UUID(str(identity)))
    except ValueError as exc:
        raise AppError("invalid_id", "Resource IDs must be UUIDs.") from exc
    base = (get_settings().root / area).resolve()
    path = (base / f"{identity}{suffix}").resolve()
    if path.parent != base:
        raise AppError("invalid_path", "Unsafe storage path.")
    return path

def storage_key(area: str, identity: str, suffix: str) -> str:
    """Return a validated object key without exposing user-controlled paths."""
    safe_path(area, identity, suffix)
    prefix = get_settings().object_storage_prefix.strip("/")
    return f"{prefix}/{area}/{UUID(str(identity))}{suffix}"

def _s3():
    settings = get_settings()
    if not all([settings.object_storage_bucket, settings.object_storage_access_key, settings.object_storage_secret_key]):
        raise AppError("storage_not_configured", "Object storage is not configured for this deployment.", 503)
    try:
        import boto3
        return boto3.client(
            "s3",
            endpoint_url=settings.object_storage_endpoint,
            aws_access_key_id=settings.object_storage_access_key,
            aws_secret_access_key=settings.object_storage_secret_key,
            region_name=settings.object_storage_region,
        )
    except Exception as exc:
        raise AppError("storage_unavailable", "Object storage could not be initialized.", 503) from exc

def save_bytes(area: str, identity: str, suffix: str, value: bytes) -> str:
    digest_value = hashlib.sha256(value).hexdigest()
    settings = get_settings()
    if settings.storage_backend == "s3":
        try:
            content_type = {".csv": "text/csv", ".json": "application/json", ".html": "text/html", ".dill": "application/octet-stream"}.get(suffix, "application/octet-stream")
            _s3().put_object(Bucket=settings.object_storage_bucket, Key=storage_key(area, identity, suffix), Body=value, ContentType=content_type)
        except AppError:
            raise
        except Exception as exc:
            raise AppError("storage_unavailable", "Object storage could not save the artifact.", 503) from exc
        return digest_value
    return atomic_bytes(safe_path(area, identity, suffix), value)

def read_bytes(area: str, identity: str, suffix: str) -> bytes:
    settings = get_settings()
    if settings.storage_backend == "s3":
        try:
            return _s3().get_object(Bucket=settings.object_storage_bucket, Key=storage_key(area, identity, suffix))["Body"].read()
        except AppError:
            raise
        except Exception as exc:
            raise AppError("artifact_missing", "The stored artifact is unavailable.", 404) from exc
    path = safe_path(area, identity, suffix)
    if not path.is_file():
        raise AppError("artifact_missing", "The stored artifact is unavailable.", 404)
    return path.read_bytes()

def delete_object(area: str, identity: str, suffix: str) -> None:
    settings = get_settings()
    if settings.storage_backend == "s3":
        try:
            _s3().delete_object(Bucket=settings.object_storage_bucket, Key=storage_key(area, identity, suffix))
        except AppError:
            raise
        except Exception as exc:
            raise AppError("storage_unavailable", "Object storage could not delete the artifact.", 503) from exc
        return
    safe_path(area, identity, suffix).unlink(missing_ok=True)

def verify_object(area: str, identity: str, suffix: str, expected: str) -> None:
    if hashlib.sha256(read_bytes(area, identity, suffix)).hexdigest() != expected:
        raise AppError("integrity_error", "Stored artifact is missing or its integrity hash has changed.", 409)

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()

def atomic_bytes(path: Path, value: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{uuid4().hex}.tmp")
    try:
        with temp.open("xb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            temp.chmod(0o600)
        except OSError:
            pass  # Windows may not implement POSIX mode semantics.
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    return hashlib.sha256(value).hexdigest()

def verify(path: Path, expected: str) -> None:
    if not path.is_file() or digest(path) != expected:
        raise AppError("integrity_error", "Stored artifact is missing or its integrity hash has changed.", 409)

def save_model(identity: str, bundle: dict) -> str:
    import dill
    return save_bytes("models", identity, ".dill", dill.dumps(bundle, protocol=5))

def load_model(identity: str, expected: str) -> dict:
    # Only application-created, hash-checked local artifacts. NEVER accept uploaded models.
    import dill
    verify_object("models", identity, ".dill", expected)
    return dill.loads(read_bytes("models", identity, ".dill"))
