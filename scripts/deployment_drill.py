"""Synthetic-only Docker acceptance. Refuses existing projects on fresh setup.

Never runs against workspace databases. All operations target its own named volumes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data/deployment-evidence-20260919"
PROJECT = "fucheng-deploytest-20260919"
ENVFILE = EVIDENCE / "compose.env"
COMPOSE = ["docker", "compose", "--env-file", str(ENVFILE), "-f", str(ROOT / "deploy/docker/compose.yaml")]
events = []


def call(argv, *, input=None, success=True):
    # Bytes avoid Windows CRLF translation adding a literal carriage return to a Linux password.
    result = subprocess.run(argv, cwd=ROOT, input=input.encode() if input is not None else None, capture_output=True)
    result.stdout = result.stdout.decode("utf-8", errors="replace")
    result.stderr = result.stderr.decode("utf-8", errors="replace")
    events.append({"command": argv, "exit": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
    if (result.returncode == 0) != success:
        raise RuntimeError(f"Unexpected exit {result.returncode}: {argv}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def compose(*args, **kw):
    return call(COMPOSE + list(args), **kw)


def code(script, *, image=None, volume=None, success=True):
    image = image or json.loads((EVIDENCE / "drill-state.json").read_text())["image"]
    return call(["docker", "run", "--rm", "--pull", "never", "--network", "none", "--user", "10001:10001",
                 "-v", f"{volume or PROJECT + '_data'}:/data", "-v", f"{PROJECT}_backups:/backups",
                 "--entrypoint", "python", image, "-c", script], success=success)


def set_image(image):
    lines = ENVFILE.read_text().splitlines()
    ENVFILE.write_text("\n".join(f"FUCHENG_IMAGE={image}" if x.startswith("FUCHENG_IMAGE=") else x for x in lines) + "\n")


def old_image(release):
    # Genuine HEAD 0005 app/frontend/migrations with the new deployment boundary retrofitted.
    # This is a synthetic rollback fixture, not a previously deployed production release.
    directory = EVIDENCE / "old-release-context"
    directory.mkdir(exist_ok=False)
    paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=ROOT, text=True).splitlines()
    from deployment_package import source_files
    wanted = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in source_files()}
    for path in list(wanted):
        if path.startswith(("src/fucheng/", "frontend/src/", "migrations/versions/")):
            del wanted[path]
    for path in paths:
        if path.startswith(("src/fucheng/", "frontend/src/", "migrations/versions/")) and Path(path).suffix in {".py", ".ts", ".tsx", ".css"}:
            wanted[path] = subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT)
    wanted["src/fucheng/proxy.py"] = (ROOT / "src/fucheng/proxy.py").read_bytes()
    wanted["src/fucheng/config.py"] = (ROOT / "src/fucheng/config.py").read_bytes()
    old_app = wanted["src/fucheng/app.py"].decode()
    old_app = old_app.replace("    app.state.settings = settings\n", "    app.state.settings = settings\n    if settings.public_origin:\n        from .proxy import DeploymentBoundary\n        app.add_middleware(DeploymentBoundary, settings=settings)\n")
    wanted["src/fucheng/app.py"] = old_app.encode()
    manifest = {"kind": "synthetic-rollback-fixture-HEAD-0005-plus-deployment-boundary", "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "files": {p: hashlib.sha256(b).hexdigest() for p, b in sorted(wanted.items())}}
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    wanted["deploy/docker/source-manifest.json"] = manifest_bytes
    for path, value in wanted.items():
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    tag = f"local/fucheng-drill:0005-{digest[:16]}"
    call(["docker", "build", "--platform", "linux/amd64", "--build-arg", f"SOURCE_SHA256={digest}", "-t", tag, str(directory)])
    return tag


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["setup", "persistence", "upgrade", "recovery", "backup"])
    parser.add_argument("--release", default="data/deployment-release-20260920-r7/release.json")
    args = parser.parse_args()
    EVIDENCE.mkdir(exist_ok=True)
    try:
        if args.action == "setup":
            release = json.loads((ROOT / args.release).read_text())
            if ENVFILE.exists():
                raise RuntimeError("Drill already set up; refusing existing resources")
            existing = call(["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={PROJECT}", "-q"])
            assert not existing
            ENVFILE.write_text(f"COMPOSE_PROJECT_NAME={PROJECT}\nFUCHENG_IMAGE={release['image']}\nFUCHENG_PUBLIC_ORIGIN=https://localhost:8447\nFUCHENG_PROXY_KIND=local\nFUCHENG_TEST_CERT_DIR={EVIDENCE.as_posix()}/test-tls\nFUCHENG_BACKUP_INTERVAL=5\nFUCHENG_BACKUP_KEEP=2\n")
            state = {"image": release["image"], "project": PROJECT}
            (EVIDENCE / "drill-state.json").write_text(json.dumps(state))
            compose("run", "--rm", "ops", "serve", success=False)
            compose("run", "--rm", "ops", "init")
            compose("run", "--rm", "ops", "init", success=False)
            credentials = {"username": "deployment-synthetic-admin", "password": secrets.token_urlsafe(24)}
            (EVIDENCE / "synthetic-admin.json").write_text(json.dumps(credentials))
            compose("run", "--rm", "-T", "ops", "admin", credentials["username"], input=credentials["password"] + "\n")
            compose("--profile", "https-test", "up", "-d", "--wait", "app", "backup", "https-test")
            compose("run", "--rm", "ops", "migrate", success=False)
            compose("run", "--rm", "ops", "serve", success=False)
            compose("run", "--rm", "ops", "backup")
            print("Fresh init/admin/HTTPS/backup started; singleton and live migration rejection passed")
        elif args.action == "persistence":
            before = code("import runtime,json,sqlite3; p=runtime.active_path(); d=sqlite3.connect(p); print(json.dumps({'path':str(p),'members':d.execute('select count(*) from members').fetchone()[0],'registrations':d.execute('select count(*) from competition_registrations').fetchone()[0]}))")
            compose("up", "-d", "--force-recreate", "--wait", "app", "backup")
            after = code("import runtime,json,sqlite3; p=runtime.active_path(); d=sqlite3.connect(p); print(json.dumps({'path':str(p),'members':d.execute('select count(*) from members').fetchone()[0],'registrations':d.execute('select count(*) from competition_registrations').fetchone()[0]}))")
            assert before == after and json.loads(after)["registrations"] >= 1
            print("Force-recreate retained synthetic member, registration and active pointer")
        elif args.action == "upgrade":
            state = json.loads((EVIDENCE / "drill-state.json").read_text())
            old = old_image(state)
            state["old_image"] = old
            (EVIDENCE / "drill-state.json").write_text(json.dumps(state))
            # A second isolated project/volume runs old source at schema 0005.
            upgrade_project = PROJECT + "-upgrade"
            upgrade_env = EVIDENCE / "upgrade.env"
            upgrade_env.write_text(ENVFILE.read_text().replace(PROJECT, upgrade_project).replace(state["image"], old)
                                   + "FUCHENG_SUBNET=172.30.99.0/24\nFUCHENG_APP_IP=172.30.99.2\nFUCHENG_PROXY_IP=172.30.99.3\n")
            base = ["docker", "compose", "--env-file", str(upgrade_env), "-f", str(ROOT / "deploy/docker/compose.yaml")]
            call(base + ["run", "--rm", "ops", "init"])
            code("""import runtime
from datetime import date,datetime,UTC
from fucheng.database import create_db_engine,make_session_factory
from fucheng.models import Member,Competition,CompetitionRegistration
factory=make_session_factory(create_db_engine('sqlite:///'+str(runtime.active_path())))
with factory.begin() as db:
    c=Competition(name='Synthetic old-schema event',competition_date=date(2099,9,20),registration_deadline=datetime(2099,9,19,tzinfo=UTC),capacity=2,status='open',next_sequence=4)
    db.add(c); db.flush()
    for n,status in enumerate(['confirmed','waitlisted','cancelled'],1):
        m=Member(name='Synthetic old-schema member '+str(n),level=n,diet='unset')
        db.add(m); db.flush()
        db.add(CompetitionRegistration(competition_id=c.id,member_id=m.id,status=status,diet='vegetarian',hard_level_snapshot=n,queue_sequence=n,created_by_kind='system',updated_by_kind='system'))
print('Seeded three old-schema synthetic registrations')""", image=old, volume=upgrade_project + "_data")
            code("import runtime,sqlite3; d=sqlite3.connect(runtime.active_path()); d.execute('create table drill_evidence(label text)'); d.execute(\"insert into drill_evidence values ('before-update')\"); d.commit()", volume=upgrade_project + "_data")
            call(base + ["up", "-d", "--wait", "app"])
            call(base + ["run", "--rm", "ops", "migrate"], success=False)
            call(base + ["stop", "app"])
            upgrade_env.write_text(upgrade_env.read_text().replace(old, state["image"]))
            call(base + ["run", "--rm", "ops", "serve"], success=False)
            call(base + ["run", "--rm", "ops", "migrate"])
            checked = json.loads(code("import runtime,sqlite3,json; d=sqlite3.connect(runtime.active_path()); print(json.dumps(d.execute('select status,hard_level_snapshot,competition_level,queue_sequence from competition_registrations order by queue_sequence').fetchall()))", volume=upgrade_project + "_data"))
            assert checked == [['confirmed',1,1,1],['waitlisted',2,2,2],['cancelled',3,3,3]]
            call(base + ["up", "-d", "--wait", "app"])
            # Add actual post-upgrade writes, then confirm they survive in the retained old file.
            code("import runtime,sqlite3; d=sqlite3.connect(runtime.active_path()); d.execute(\"insert into drill_evidence values ('after-update')\"); d.commit()", volume=upgrade_project + "_data")
            call(base + ["stop", "app"])
            upgraded_path = code("import runtime; print(runtime.active_path().name)", volume=upgrade_project + "_data")
            upgrade_env.write_text(upgrade_env.read_text().replace(state["image"], old))
            call(base + ["run", "--rm", "ops", "serve"], success=False)
            checkpoint = call(base + ["run", "--rm", "--entrypoint", "python", "ops", "-c", "from pathlib import Path; print(sorted(Path('/backups').glob('pre-update-*.db'))[-1].name)"])
            call(base + ["run", "--rm", "ops", "restore", checkpoint])
            call(base + ["up", "-d", "--wait", "app"])
            verify = code(f"import runtime,sqlite3,json; a=sqlite3.connect(runtime.active_path()); b=sqlite3.connect('/data/{upgraded_path}'); print(json.dumps({{'active':a.execute('select * from drill_evidence').fetchall(),'retained':b.execute('select * from drill_evidence').fetchall(),'schema':runtime.inspect_db(runtime.active_path())}}))", volume=upgrade_project + "_data")
            result = json.loads(verify)
            assert result["active"] == [["before-update"]] and result["retained"] == [["before-update"], ["after-update"]]
            assert result["schema"]["revision"] == "0005_competition_deletion"
            call(base + ["stop", "app"])
            print("0005 genuine old-source fixture -> 0006 -> old-image + 0005 backup rollback passed; post-update writes retained")
        elif args.action == "recovery":
            compose("stop", "app", "backup", "https-test")
            checkpoint = json.loads(compose("run", "--rm", "ops", "backup"))["file"]
            # Force a valid SQLite but incompatible/missing revision: migration fails and marker persists.
            code("import runtime,sqlite3; d=sqlite3.connect(runtime.active_path()); d.execute(\"update alembic_version set version_num='synthetic_unknown_revision'\"); d.commit()")
            compose("run", "--rm", "ops", "migrate", success=False)
            compose("run", "--rm", "ops", "serve", success=False)
            compose("run", "--rm", "ops", "restore", checkpoint)
            # Now simulate corruption with a new corrupt active target. Good original file remains untouched.
            code("import runtime; p=runtime.DATA/'synthetic-corrupt.db'; p.write_bytes(b'not-a-sqlite-file'); runtime.atomic_json(runtime.ACTIVE,{'database':p.name})")
            compose("run", "--rm", "ops", "restore", checkpoint)
            assert code("import runtime; print((runtime.DATA/'synthetic-corrupt.db').read_bytes().decode())") == "not-a-sqlite-file"
            code("import runtime; runtime.atomic_json(runtime.ACTIVE,{'database':'synthetic-missing.db'})")
            compose("run", "--rm", "ops", "restore", checkpoint)
            # Interrupted first init has an explicit recovery command on a separate synthetic volume.
            volume = PROJECT + "_interrupted-" + str(time.time_ns())
            code("import runtime; runtime.maintenance('init'); (runtime.DATA/'failed-init.db').write_bytes(b'failed-init')", volume=volume)
            image = json.loads((EVIDENCE / "drill-state.json").read_text())["image"]
            base = ["docker", "run", "--rm", "--network", "none", "-v", volume + ":/data", "-v", PROJECT + "_backups:/backups", image]
            call(base + ["init"], success=False)
            call(base + ["recover-init"])
            assert code("import runtime; print((runtime.DATA/'failed-init.db').read_bytes().decode())", volume=volume) == "failed-init"
            compose("--profile", "https-test", "up", "-d", "--wait", "app", "backup", "https-test")
            print("Failed migration fail-closed, corrupt/missing active restore, interrupted-init recovery passed")
        elif args.action == "backup":
            time.sleep(16)
            data = json.loads(code("import runtime,json; print(json.dumps({'scheduled':len(list(runtime.BACKUPS.glob('scheduled-*.db'))),'manual':len(list(runtime.BACKUPS.glob('manual-*.db'))),'status':json.loads((runtime.DATA/'backup-status.json').read_text())}))"))
            assert data["scheduled"] == 2 and data["manual"] >= 1 and data["status"]["ok"]
            compose("stop", "backup")
            # An isolated backup process with a read-only destination fails visibly and becomes unhealthy.
            image = json.loads((EVIDENCE / "drill-state.json").read_text())["image"]
            name = PROJECT + "-backup-failure"
            call(["docker", "run", "-d", "--name", name, "--network", "none", "--read-only", "--tmpfs", "/tmp", "-e", "FUCHENG_BACKUP_DIR=/unwritable", "-e", "FUCHENG_BACKUP_INTERVAL=5", "-v", PROJECT + "_data:/data", image, "backup-loop"])
            time.sleep(2)
            call(["docker", "exec", name, "python", "/app/runtime.py", "backup-health"], success=False)
            assert "BACKUP FAILED" in call(["docker", "logs", name]) or "BACKUP FAILED" in events[-1]["stderr"]
            call(["docker", "stop", name])
            compose("run", "--rm", "ops", "backup")
            compose("up", "-d", "--wait", "backup")
            print("Scheduled retention and manual checkpoint preservation passed; backup failure was visible")
    finally:
        report = EVIDENCE / f"drill-{args.action}-{time.time_ns()}.json"
        report.write_text(json.dumps(events, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
