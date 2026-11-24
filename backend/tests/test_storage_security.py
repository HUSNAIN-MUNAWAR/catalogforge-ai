import io

import pytest

from app.services.storage import LocalObjectStorage


def test_local_storage_rejects_path_escape(tmp_path):
    storage = LocalObjectStorage(tmp_path / "objects")
    with pytest.raises(ValueError, match="inside the configured object root"):
        storage.put("../outside.txt", io.BytesIO(b"secret"))


def test_local_storage_writes_atomically_and_scopes_exists(tmp_path):
    storage = LocalObjectStorage(tmp_path / "objects")
    target = storage.put("case-1/source.bin", io.BytesIO(b"payload"))
    assert storage.exists("case-1/source.bin")
    assert open(target, "rb").read() == b"payload"
    assert list((tmp_path / "objects" / "case-1").glob("*.tmp")) == []
