"""The Linux runtime's DB and media backup contract on an isolated synthetic store."""
import importlib.util
import io
import json
import sqlite3
import sys
import types
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image


def runtime_module(monkeypatch):
    # The backup helpers are platform neutral; only the serving flock is Linux-only.
    monkeypatch.setitem(sys.modules, "fcntl", types.SimpleNamespace())
    path = Path(__file__).resolve().parents[1] / "deploy" / "docker" / "runtime.py"
    spec = importlib.util.spec_from_file_location("synthetic_runtime", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backup_carries_immutable_photo_and_rejects_tampering(app, client, auth, tmp_path, monkeypatch):
    created = client.post("/api/admin/announcements", headers=auth, json={
        "title": "合成照片", "body": "合成內容", "is_published": True,
        "is_pinned": False, "request_id": str(uuid4()),
    }).json()
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(buffer, format="PNG")
    uploaded = client.post(f"/api/admin/announcements/{created['id']}/photo", headers=auth,
        data={"version": "1", "request_id": str(uuid4())},
        files={"photo": ("synthetic.png", buffer.getvalue(), "image/png")}).json()
    source = Path(app.state.engine.url.database)
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        db.execute("INSERT INTO alembic_version VALUES ('0009_announcement_media')")
    runtime = runtime_module(monkeypatch)
    runtime.DATA = tmp_path
    runtime.MEDIA = tmp_path / "announcement-media"
    runtime.BACKUPS = tmp_path / "backups"
    runtime.atomic_json = lambda path, value: path.write_text(json.dumps(value))
    saved = runtime.snapshot(source, "manual")
    backup = runtime.BACKUPS / saved["file"]
    archive = runtime.verified_media_archive(backup, saved)
    assert archive is not None
    restored_media = tmp_path / "restored" / "announcement-media"
    runtime.MEDIA = restored_media
    runtime.restore_media(archive)
    with sqlite3.connect(backup) as db:
        filename, digest = db.execute("SELECT filename, sha256 FROM announcement_media WHERE id=?",
            (uploaded["photo_id"],)).fetchone()
    assert (restored_media / filename).is_file()
    import hashlib
    assert hashlib.sha256((restored_media / filename).read_bytes()).hexdigest() == digest
    archive.write_bytes(archive.read_bytes() + b"tampered")
    with pytest.raises(SystemExit, match="checksum"):
        runtime.verified_media_archive(backup, json.loads(backup.with_suffix(".json").read_text()))
