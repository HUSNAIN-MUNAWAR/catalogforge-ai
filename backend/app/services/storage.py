from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO


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

    def put(self, key: str, stream: BinaryIO) -> str:
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as output:
            while chunk := stream.read(1024 * 1024):
                output.write(chunk)
        return str(target)

    def exists(self, key: str) -> bool:
        return (self.root / key).exists() or Path(key).exists()


class S3CompatibleObjectStorage(ObjectStorage):
    """Intentional production interface. Wire boto3/minio client in a deployment package."""

    def __init__(self, bucket: str) -> None:
        self.bucket = bucket

    def put(self, key: str, stream: BinaryIO) -> str:
        raise NotImplementedError("Configure an S3 client adapter for production object storage.")

    def exists(self, key: str) -> bool:
        raise NotImplementedError("Configure an S3 client adapter for production object storage.")
