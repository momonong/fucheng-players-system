"""Linux container lifecycle. All writable commands share a lifetime flock.

Never run alembic/CLI directly against these volumes: use this entrypoint.
Data and backups deliberately survive image replacement.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, closing
from datetime import datetime, UTC
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
import uuid

DATA = Path(os.getenv("FUCHENG_DATA_DIR", "/data"))
BACKUPS = Path(os.getenv("FUCHENG_BACKUP_DIR", "/backups"))
ACTIVE = DATA / "active.json"
MAINTENANCE = DATA / "maintenance.json"


def stamp():
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def atomic_json(path, value):
    tmp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    with tmp.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def lock(name):
    DATA.mkdir(exist_ok=True)
    with (DATA / name).open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another server/maintenance/backup operation owns the volume lock")
        yield


def active_path():
    if not ACTIVE.is_file():
        raise SystemExit("Not initialized; run explicit init or restore first")
    name = json.loads(ACTIVE.read_text())["database"]
    if Path(name).name != name or not name.endswith(".db"):
        raise SystemExit("Invalid active database pointer")
    path = DATA / name
    if not path.is_file():
        raise SystemExit("Active database missing")
    return path


def expected():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    return ScriptDirectory.from_config(Config("/app/alembic.ini")).get_current_head()


def inspect_db(path, *, match=False, full=True, read_only=True):
    # Only an isolated imported temporary copy may open read/write, so SQLite can
    # create and clean up WAL sidecars there. The archived source stays read-only.
    uri = f"file:{path}?mode={'ro' if read_only else 'rw'}"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchall() if full else [("ok",)]
        foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall() if full else []
        revision = db.execute("SELECT version_num FROM alembic_version").fetchall()
        if integrity != [("ok",)] or foreign_keys or len(revision) != 1:
            raise SystemExit("Database integrity/schema validation failed")
        if match and revision[0][0] != expected():
            raise SystemExit(f"Schema mismatch: image={expected()}, database={revision[0][0]}; explicit maintenance required")
        return {"revision": revision[0][0], "integrity": "ok", "foreign_key_errors": 0}


def snapshot(source, prefix):
    BACKUPS.mkdir(exist_ok=True)
    target = BACKUPS / f"{prefix}-{stamp()}-{uuid.uuid4().hex[:8]}.db"
    tmp = target.with_suffix(".partial")
    with closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(tmp)) as dst:
            src.backup(dst)
            # Backup API copies the WAL header. Normalize this closed-off copy to
            # a standalone DB before validation/export; never change the live DB.
            if dst.execute("PRAGMA journal_mode=DELETE").fetchone() != ("delete",):
                raise SystemExit("Unable to finalize standalone backup journal mode")
    info = inspect_db(tmp)
    tmp.replace(target)
    info.update(file=target.name, sha256=hashlib.sha256(target.read_bytes()).hexdigest(), created_at=time.time())
    atomic_json(target.with_suffix(".json"), info)
    return info


def migrate(path):
    env = dict(os.environ, FUCHENG_DATABASE_URL=f"sqlite:///{path}")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
    return inspect_db(path, match=True)


def maintenance(action):
    atomic_json(MAINTENANCE, {"action": action, "started": stamp()})


def record(action, **details):
    directory = DATA / "operations"
    directory.mkdir(exist_ok=True)
    atomic_json(directory / f"{stamp()}-{action}.json", dict(action=action, **details))


def backup_once(*, automatic=False):
    with lock("backup.lock"):
        if MAINTENANCE.exists():
            raise SystemExit("Maintenance active; scheduled backup postponed")
        result = snapshot(active_path(), "scheduled" if automatic else "manual")
        # Only automatic backups are retained/deleted; pre-update/manual checkpoints persist.
        keep = int(os.getenv("FUCHENG_BACKUP_KEEP", "14"))
        if keep < 2:
            raise SystemExit("Retention must keep at least two automatic backups")
        for old in (sorted(BACKUPS.glob("scheduled-*.db"), reverse=True)[keep:] if automatic else []):
            old.unlink()
            old.with_suffix(".json").unlink(missing_ok=True)
        atomic_json(DATA / "backup-status.json", dict(ok=True, timestamp=time.time(), **result))
        print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "recover-init", "migrate", "serve", "health", "admin", "backup", "import-backup", "export", "backup-loop", "backup-health", "restore", "inspect"])
    parser.add_argument("argument", nargs="?")
    args = parser.parse_args()
    from fucheng.config import Settings
    settings = Settings.from_env()
    preview_marker = DATA / "local-http-synthetic.json"
    if settings.local_http_preview:
        if args.action in {"restore", "import-backup", "recover-init", "migrate"}:
            raise SystemExit("Local HTTP preview accepts fresh synthetic initialization only")
        if args.action == "init":
            if list(DATA.glob("*.db*")) or ACTIVE.exists() or MAINTENANCE.exists():
                raise SystemExit("Local HTTP preview requires a new empty volume")
        elif not preview_marker.is_file():
            raise SystemExit("Not a local HTTP synthetic preview volume")
    elif preview_marker.exists():
        raise SystemExit("Local HTTP synthetic volume cannot be used for HTTPS deployment")
    if args.action == "health":
        if MAINTENANCE.exists():
            raise SystemExit("Maintenance active")
        inspect_db(active_path(), match=True, full=False)
        import urllib.request
        from urllib.parse import urlsplit
        host = urlsplit(os.environ["FUCHENG_PUBLIC_ORIGIN"]).netloc
        req = urllib.request.Request("http://127.0.0.1:8000/api/health", headers={"Host": host})
        with urllib.request.urlopen(req, timeout=5) as response:
            assert response.status == 200
        return
    if args.action == "inspect":
        print(json.dumps(inspect_db(active_path())))
        return
    if args.action == "backup-health":
        value = json.loads((DATA / "backup-status.json").read_text())
        interval = int(os.getenv("FUCHENG_BACKUP_INTERVAL", "86400"))
        if not value["ok"] or time.time() - value["timestamp"] > interval + 300:
            raise SystemExit("Backup failed or stale; inspect backup logs/status")
        return
    if args.action == "backup":
        backup_once()
        return
    if args.action == "import-backup":
        if not args.argument or Path(args.argument).name != args.argument or not args.argument.endswith(".db"):
            raise SystemExit("Specify a DB filename in the read-only /incoming mount")
        with lock("backup.lock"):
            source = Path("/incoming") / args.argument
            meta = json.loads(source.with_suffix(".json").read_text())
            if meta["file"] != source.name or hashlib.sha256(source.read_bytes()).hexdigest() != meta["sha256"]:
                raise SystemExit("Backup import checksum/metadata mismatch")
            if any(Path(str(source) + suffix).exists() for suffix in ("-wal", "-shm")):
                raise SystemExit("Import requires a standalone consistency backup, without WAL/SHM files")
            target = BACKUPS / source.name
            metadata = target.with_suffix(".json")
            temporary = target.with_suffix(".importing")
            if target.exists() or metadata.exists() or temporary.exists():
                raise SystemExit("Import destination exists; refusing overwrite")
            with source.open("rb") as src, temporary.open("xb") as dst:
                shutil.copyfileobj(src, dst)
                dst.flush()
                os.fsync(dst.fileno())
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != meta["sha256"]:
                raise SystemExit("Copied backup checksum mismatch")
            inspected = inspect_db(temporary, read_only=False)
            if inspected["revision"] != meta["revision"]:
                raise SystemExit("Backup revision does not match metadata")
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != meta["sha256"]:
                raise SystemExit("Backup bytes changed during validation; import stopped")
            temporary.replace(target)
            atomic_json(metadata, meta)
            print(json.dumps({"imported": target.name, "sha256": meta["sha256"], "revision": meta["revision"]}))
        return
    if args.action == "export":
        with lock("backup.lock"):
            if MAINTENANCE.exists():
                raise SystemExit("Maintenance active; export postponed")
            checkpoint = snapshot(active_path(), "manual-export")
            directory = BACKUPS / "exports"
            directory.mkdir(exist_ok=True)
            archive = directory / f"export-{stamp()}.tar"
            temporary = archive.with_suffix(".partial")
            entries = {}
            with tarfile.open(temporary, "x") as bundle:
                for path in sorted(BACKUPS.glob("*.db")):
                    metadata = path.with_suffix(".json")
                    info = json.loads(metadata.read_text())
                    if hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]:
                        raise SystemExit("Backup checksum mismatch; export stopped")
                    for item in (path, metadata):
                        entries[item.name] = hashlib.sha256(item.read_bytes()).hexdigest()
                        bundle.add(item, arcname=item.name, recursive=False)
            temporary.replace(archive)
            result = {"archive": archive.name, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                      "checkpoint": checkpoint["file"], "files": entries}
            atomic_json(archive.with_suffix(".json"), result)
            print(json.dumps(result))
        return
    if args.action == "backup-loop":
        interval = int(os.getenv("FUCHENG_BACKUP_INTERVAL", "86400"))
        if interval < 5:
            raise SystemExit("Backup interval must be at least 5 seconds")
        while True:
            try:
                backup_once(automatic=True)
            except (Exception, SystemExit):
                atomic_json(DATA / "backup-status.json", {"ok": False, "timestamp": time.time()})
                print("BACKUP FAILED: inspect maintenance state, disk, and volume permissions", file=sys.stderr, flush=True)
            time.sleep(interval)
    with lock("writer.lock"):
        if args.action == "serve":
            if MAINTENANCE.exists():
                raise SystemExit("Maintenance incomplete; inspect operations and restore/retry migration")
            path = active_path()
            inspect_db(path, match=True)
            if not settings.local_http_preview and (not settings.public_origin or not settings.session_cookie_secure):
                raise SystemExit("HTTPS public origin and secure cookies required")
            env = dict(os.environ, FUCHENG_DATABASE_URL=f"sqlite:///{path}")
            child = subprocess.Popen([sys.executable, "-m", "uvicorn", "fucheng.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers", "--no-access-log"], env=env)
            def stop(_sig, _frame):
                if child.poll() is None:
                    child.terminate()
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            try:
                raise SystemExit(child.wait())
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait()
        if args.action == "admin":
            if MAINTENANCE.exists() or not args.argument:
                raise SystemExit("Maintenance active or missing username")
            path = active_path()
            inspect_db(path, match=True)
            env = dict(os.environ, FUCHENG_DATABASE_URL=f"sqlite:///{path}")
            # Password is prompted by getpass; no default or command-line password.
            subprocess.run([sys.executable, "-m", "fucheng.cli", "create-admin", args.argument], env=env, check=True)
            return
        with lock("backup.lock"):
            if args.action in {"init", "recover-init"}:
                if ACTIVE.exists() or (args.action == "init" and (list(DATA.glob("*.db")) or MAINTENANCE.exists())):
                    raise SystemExit("Initialization refuses existing data; use migration/restore")
                if args.action == "recover-init":
                    if not MAINTENANCE.exists() or json.loads(MAINTENANCE.read_text())["action"] != "init":
                        raise SystemExit("recover-init only applies to interrupted initialization without an active pointer")
                    record("recover-init", retained_files=[p.name for p in DATA.glob("*.db*")])
                maintenance("init")
                target = DATA / f"database-{stamp()}.db"
                info = migrate(target)
                if settings.local_http_preview:
                    atomic_json(preview_marker, {"purpose": "local-http-synthetic-only"})
                atomic_json(ACTIVE, {"database": target.name})
                record("init", database=target.name, **info)
            elif args.action == "migrate":
                path = active_path()
                # Backup failure must leave maintenance persisted and prevent next serve.
                maintenance("migrate")
                before = snapshot(path, "pre-update")
                record("pre-update", database=path.name, backup=before)
                info = migrate(path)
                record("migrate", database=path.name, backup=before, **info)
            elif args.action == "restore":
                if not args.argument or Path(args.argument).name != args.argument:
                    raise SystemExit("Specify a backup filename under /backups")
                source = BACKUPS / args.argument
                meta = json.loads(source.with_suffix(".json").read_text())
                if meta["file"] != source.name or hashlib.sha256(source.read_bytes()).hexdigest() != meta["sha256"]:
                    raise SystemExit("Restore backup checksum/metadata mismatch")
                # /backups is our locked, local archive copy, not the external source.
                # A writable connection lets SQLite remove legacy empty WAL sidecars.
                inspect_db(source, match=True, read_only=False)
                maintenance("restore")
                previous = None
                if ACTIVE.exists():
                    # Archive pointer evidence; never overwrite/delete the old DB/WAL/SHM.
                    pointer = ACTIVE.read_text()
                    try:
                        previous = active_path()
                        retained = snapshot(previous, "pre-restore-retained")
                        record("pre-restore", pointer=pointer, database=previous.name, backup=retained)
                    except (Exception, SystemExit):
                        retained_files = []
                        for file in DATA.glob("*.db*"):
                            if file.is_file():
                                retained_files.append({"file": file.name, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
                        record("pre-restore-damaged", pointer=pointer, retained_files=retained_files,
                               state="Original files retained in place; consistency snapshot unavailable; do not delete")
                target = DATA / f"restored-{stamp()}-{uuid.uuid4().hex[:8]}.db"
                with closing(sqlite3.connect(f"file:{source}?mode=rw", uri=True)) as src:
                    with closing(sqlite3.connect(target)) as dst:
                        src.backup(dst)
                if hashlib.sha256(source.read_bytes()).hexdigest() != meta["sha256"]:
                    raise SystemExit("Restore source bytes changed; maintenance remains active")
                info = inspect_db(target, match=True)
                atomic_json(ACTIVE, {"database": target.name})
                record("restore", database=target.name, previous=previous.name if previous else None, backup=source.name, **info)
            MAINTENANCE.unlink()
            print(json.dumps({"action": args.action, "database": active_path().name, **info}))


if __name__ == "__main__":
    main()
