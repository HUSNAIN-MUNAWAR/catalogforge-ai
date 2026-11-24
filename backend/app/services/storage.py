from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO
import os
import uuid


class ObjectStorage(ABC):
    """Storage boundary shared by local demo and S3-compatible deployments."""

    @abstractmethod
    def put(self, key: str, stream: BinaryIO) -> str:
        """Store a binary stream and return a durable storage key."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return whether a source object is available."""


class LocalObjectStorage(ObjectStorage):
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_target(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("Storage key must remain inside the configured object root")
        return candidate

    def put(self, key: str, stream: BinaryIO) -> str:
        target = self._safe_target(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as output:
                while chunk := stream.read(1024 * 1024):
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return str(target)

    def exists(self, key: str) -> bool:
        return self._safe_target(key).exists()


class S3CompatibleObjectStorage(ObjectStorage):
    """Intentional production interface. Wire boto3/minio client in a deployment package."""

    def __init__(self, bucket: str) -> None:
        self.bucket = bucket

    def put(self, key: str, stream: BinaryIO) -> str:
        raise NotImplementedError("Configure an S3 client adapter for production object storage.")

    def exists(self, key: str) -> bool:
        raise NotImplementedError("Configure an S3 client adapter for production object storage.")
