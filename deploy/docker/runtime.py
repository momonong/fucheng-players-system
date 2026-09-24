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
import re
import signal
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
import uuid
from fucheng.backup_schedule import latest_weekly_due

DATA = Path(os.getenv("FUCHENG_DATA_DIR", "/data"))
BACKUPS = Path(os.getenv("FUCHENG_BACKUP_DIR", "/backups"))
ACTIVE = DATA / "active.json"
MAINTENANCE = DATA / "maintenance.json"
MEDIA = DATA / "announcement-media"
MEDIA_NAME = re.compile(r"[0-9a-f-]{36}\.(?:jpg|png)\Z")


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


def snapshot(source, prefix, *, scheduled_for=None):
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
    with closing(sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='announcement_media'").fetchone():
            for filename, sha256, size in db.execute("SELECT filename, sha256, size FROM announcement_media"):
                path = MEDIA / filename
                if not MEDIA_NAME.fullmatch(filename) or not path.is_file() or path.stat().st_size != size or hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
                    raise SystemExit("Announcement media does not match database; backup stopped")
    media_archive = target.with_suffix(".media.tar")
    media_tmp = media_archive.with_suffix(".partial")
    with tarfile.open(media_tmp, "w") as bundle:
        if MEDIA.is_dir():
            for path in sorted(MEDIA.iterdir()):
                if not path.is_file() or not MEDIA_NAME.fullmatch(path.name):
                    raise SystemExit("Unexpected announcement media path; backup stopped")
                bundle.add(path, arcname=path.name, recursive=False)
    media_tmp.replace(media_archive)
    tmp.replace(target)
    info.update(file=target.name, sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                media_file=media_archive.name, media_sha256=hashlib.sha256(media_archive.read_bytes()).hexdigest(),
                created_at=time.time(), scheduled_for=scheduled_for,
                restore_config={"image_ref": os.getenv("FUCHENG_IMAGE_REF"),
                                "public_origin": os.getenv("FUCHENG_RESTORE_PUBLIC_ORIGIN") or os.getenv("FUCHENG_PUBLIC_ORIGIN"),
                                "proxy_kind": os.getenv("FUCHENG_RESTORE_PROXY_KIND") or os.getenv("FUCHENG_PROXY_KIND", "local"),
                                "source_manifest_sha256": hashlib.sha256(Path("/app/source-manifest.json").read_bytes()).hexdigest()
                                if Path("/app/source-manifest.json").is_file() else None})
    atomic_json(target.with_suffix(".json"), info)
    return info


def verified_media_archive(db_path, metadata):
    name = metadata.get("media_file")
    if not name:
        return None
    if name != db_path.with_suffix(".media.tar").name:
        raise SystemExit("Media archive name does not match backup")
    path = db_path.with_suffix(".media.tar")
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != metadata.get("media_sha256"):
        raise SystemExit("Media archive checksum mismatch")
    with tarfile.open(path, "r") as bundle:
        for member in bundle.getmembers():
            if not member.isfile() or not MEDIA_NAME.fullmatch(member.name) or member.size > 5 * 1024 * 1024:
                raise SystemExit("Invalid media archive member")
    return path


def restore_media(archive):
    if archive is None:
        return
    MEDIA.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r") as bundle:
        for member in bundle.getmembers():
            target = MEDIA / member.name
            source = bundle.extractfile(member)
            if source is None:
                raise SystemExit("Missing media archive member")
            content = source.read()
            if target.exists():
                if target.read_bytes() != content:
                    raise SystemExit("Existing media filename has different bytes")
            else:
                with target.open("xb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())


def expire_restored_sessions(database):
    # The archive preserves forensic state, but a newly restored live database
    # must never make old administrator browser cookies valid again.
    with closing(sqlite3.connect(database)) as restored:
        restored.execute("PRAGMA foreign_keys=ON")
        restored.execute("DELETE FROM login_sessions")
        restored.commit()


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


def completed_weekly(due):
    prefix = f"weekly-{due:%Y%m%d}-"
    for metadata in sorted(BACKUPS.glob(prefix + "*.json"), reverse=True):
        try:
            info = json.loads(metadata.read_text())
            database = metadata.with_suffix(".db")
            if (info.get("scheduled_for") != due.isoformat() or info.get("file") != database.name
                    or not database.is_file() or hashlib.sha256(database.read_bytes()).hexdigest() != info.get("sha256")):
                continue
            verified_media_archive(database, info)
            inspect_db(database)
            return info
        except (OSError, ValueError, KeyError, SystemExit):
            continue
    return None


def newest_completed_weekly():
    for metadata in sorted(BACKUPS.glob("weekly-*.json"), reverse=True):
        try:
            due = datetime.fromisoformat(json.loads(metadata.read_text())["scheduled_for"])
            if completed_weekly(due):
                return due
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def backup_failure():
    path = DATA / "backup-status.json"
    try:
        previous = json.loads(path.read_text())
    except (OSError, ValueError):
        previous = {}
    atomic_json(path, {"ok": False, "failed_at": time.time(),
                       "last_success_at": previous.get("last_success_at"),
                       "last_schedule": previous.get("last_schedule")})


def backup_once(*, automatic=False, due=None):
    with lock("backup.lock"):
        if MAINTENANCE.exists():
            raise SystemExit("Maintenance active; scheduled backup postponed")
        keep = int(os.getenv("FUCHENG_BACKUP_KEEP", "8"))
        if keep < 2:
            raise SystemExit("Retention must keep at least two weekly backups")
        if automatic and due is None:
            raise SystemExit("Scheduled backup requires a calendar due time")
        if automatic:
            previous = completed_weekly(due)
            if previous:
                return previous
        prefix = f"weekly-{due:%Y%m%d}" if automatic else "manual"
        result = snapshot(active_path(), prefix, scheduled_for=due.isoformat() if due else None)
        # Only verified weekly groups are retained/deleted. Manual, pre-update,
        # pre-restore, exports, and historical daily archives are untouched.
        if automatic:
            complete = []
            for candidate in sorted(BACKUPS.glob("weekly-*.db"), reverse=True):
                try:
                    info = json.loads(candidate.with_suffix(".json").read_text())
                    if (info.get("file") == candidate.name and
                            hashlib.sha256(candidate.read_bytes()).hexdigest() == info.get("sha256")):
                        verified_media_archive(candidate, info)
                        complete.append(candidate)
                except (OSError, ValueError, KeyError, SystemExit):
                    continue
            for old in complete[keep:]:
                metadata = old.with_suffix(".json")
                if not metadata.is_file() or not old.with_suffix(".media.tar").is_file():
                    continue
                old.unlink()
                old.with_suffix(".media.tar").unlink()
                metadata.unlink()
        if automatic:
            atomic_json(DATA / "backup-status.json", dict(ok=True, timestamp=time.time(),
                last_success_at=time.time(), last_schedule=due.isoformat(), **result))
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
        due = latest_weekly_due(datetime.now(UTC))
        last_schedule = value.get("last_schedule")
        if not value["ok"] or not last_schedule or datetime.fromisoformat(last_schedule) < due:
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
            media_source = verified_media_archive(source, meta)
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
            if media_source:
                shutil.copyfile(media_source, target.with_suffix(".media.tar"))
                verified_media_archive(target, meta)
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
                    media_archive = verified_media_archive(path, info)
                    for item in (path, metadata, *((media_archive,) if media_archive else ())):
                        entries[item.name] = hashlib.sha256(item.read_bytes()).hexdigest()
                        bundle.add(item, arcname=item.name, recursive=False)
            temporary.replace(archive)
            result = {"archive": archive.name, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                      "checkpoint": checkpoint["file"], "files": entries}
            atomic_json(archive.with_suffix(".json"), result)
            print(json.dumps(result))
        return
    if args.action == "backup-loop":
        completed = newest_completed_weekly()
        while True:
            now = datetime.now(UTC)
            due = latest_weekly_due(now)
            if completed is None or due > completed:
                previous = completed_weekly(due)
                if previous:
                    completed = due
                    atomic_json(DATA / "backup-status.json", dict(ok=True, timestamp=time.time(),
                        last_success_at=previous["created_at"], last_schedule=due.isoformat(), **previous))
                else:
                    try:
                        backup_once(automatic=True, due=due)
                        completed = due
                    except (Exception, SystemExit):
                        backup_failure()
                        print("BACKUP FAILED: inspect maintenance state, disk, and volume permissions", file=sys.stderr, flush=True)
            # Recompute civil time at least once per minute. A clock jump,
            # restart, or busy maintenance cannot defer a due week indefinitely.
            time.sleep(60)
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
                media_archive = verified_media_archive(source, meta)
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
                expire_restored_sessions(target)
                inspect_db(target, match=True)
                restore_media(media_archive)
                with closing(sqlite3.connect(f"file:{target}?mode=ro", uri=True)) as check:
                    if check.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='announcement_media'").fetchone():
                        for filename, digest, size in check.execute("SELECT filename, sha256, size FROM announcement_media"):
                            path = MEDIA / filename
                            if not path.is_file() or path.stat().st_size != size or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                                raise SystemExit("Restored announcement media validation failed")
                atomic_json(ACTIVE, {"database": target.name})
                record("restore", database=target.name, previous=previous.name if previous else None, backup=source.name, **info)
            MAINTENANCE.unlink()
            print(json.dumps({"action": args.action, "database": active_path().name, **info}))


if __name__ == "__main__":
    main()
