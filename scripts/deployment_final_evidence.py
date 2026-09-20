"""Collect hashes and read-only final evidence; never print credentials or data rows."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data/deployment-evidence-20260919"
KIT = ROOT / "data/deployment-release-20260920-r8"


def run(*argv):
    result = subprocess.run(argv, cwd=ROOT, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))
    return result.stdout.decode("utf-8", "replace").strip()


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    release = json.loads((KIT / "release.json").read_text())
    checksums = {}
    for line in (KIT / "SHA256SUMS.txt").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert Path(name).name == name and sha(KIT / name) == digest
        checksums[name] = digest
    manifest = json.loads((KIT / "source-manifest.json").read_text())
    assert sha(KIT / "source-manifest.json") == release["source_manifest_sha256"]
    with zipfile.ZipFile(KIT / "source-snapshot.zip") as zf:
        for name, digest in manifest["files"].items():
            assert sha(ROOT / name) == sha(KIT / "build-context" / name) == digest
            assert hashlib.sha256(zf.read(name)).hexdigest() == digest
        assert set(zf.namelist()) == set(manifest["files"]) | {"deploy/docker/source-manifest.json"}
    image_info = json.loads(run("docker", "image", "inspect", release["image"]))[0]
    assert image_info["Id"] == release["image_id"]
    assert image_info["Config"]["User"] == "10001:10001"
    assert image_info["Config"]["Labels"]["io.fucheng.source-manifest-sha256"] == release["source_manifest_sha256"]
    image_scan = json.loads(run("docker", "run", "--rm", "--network", "none", "--entrypoint", "python", release["image"], "-c",
        "import json,pathlib,shutil,hashlib,os; print(json.dumps({'uid':os.getuid(),'node':shutil.which('node'),'databases':[str(p) for root in ['/app','/data','/backups'] for p in pathlib.Path(root).rglob('*.db')],'manifest_sha256':hashlib.sha256(pathlib.Path('/app/source-manifest.json').read_bytes()).hexdigest()}))"))
    assert image_scan["node"] is None and not image_scan["databases"] and image_scan["manifest_sha256"] == release["source_manifest_sha256"]
    live = "fucheng-portable-20260920-app-1"
    live_info = json.loads(run("docker", "inspect", live))[0]
    assert live_info["State"]["Health"]["Status"] == "healthy"
    assert not live_info["HostConfig"]["PortBindings"] and live_info["HostConfig"]["ReadonlyRootfs"]
    pragmas = json.loads(run("docker", "exec", live, "python", "-c",
        "import runtime,json; from fucheng.database import create_db_engine; e=create_db_engine('sqlite:///'+str(runtime.active_path())); c=e.connect(); print(json.dumps({x:c.exec_driver_sql('pragma '+x).scalar() for x in ['foreign_keys','busy_timeout','journal_mode','synchronous']})); c.close()"))
    assert pragmas == {"foreign_keys": 1, "busy_timeout": 10000, "journal_mode": "wal", "synchronous": 2}
    lifecycle = json.loads(run("docker", "exec", live, "python", "-c",
        "import pathlib,json; p=pathlib.Path('/backups'); print(json.dumps({'files':len(list(p.iterdir())),'temporary_sidecars':[x.name for x in p.iterdir() if x.name.endswith(('.partial-wal','.partial-shm','.importing-wal','.importing-shm'))],'backup_sidecars':[x.name for x in p.iterdir() if x.name.endswith(('.db-wal','.db-shm'))]}))"))
    assert not lifecycle["temporary_sidecars"] and not lifecycle["backup_sidecars"]
    before = json.loads((EVIDENCE / "protected-before.json").read_text())
    after = json.loads((EVIDENCE / "protected-final.json").read_text())
    assert before == after
    old_container = json.loads(run("docker", "inspect", "fucheng-deploytest-20260919-app-1"))[0]
    assert not old_container["State"]["Running"]
    baseline = json.loads((EVIDENCE / "baseline-files.json").read_text(encoding="utf-8-sig"))
    touched = [x["path"] for x in baseline if sha(ROOT / x["path"]).upper() != x["sha256"].upper()]
    preservation = {"protected_inventory_identical": True, "baseline_files_modified_this_task": touched}
    (EVIDENCE / "preservation-final.json").write_text(json.dumps(preservation, indent=2))
    containers = [json.loads(x) for x in run("docker", "ps", "-a", "--filter", "name=fucheng", "--format", "{{json .}}").splitlines()]
    volumes = [x for x in run("docker", "volume", "ls", "--format", "{{.Name}}").splitlines() if x.startswith("fucheng")]
    networks = [x for x in run("docker", "network", "ls", "--format", "{{.Name}}").splitlines() if x.startswith("fucheng")]
    directories = [{"path": str(p), "bytes": sum(f.stat().st_size for f in p.rglob("*") if f.is_file()),
                    "purpose": "final deliverable" if p == KIT else "synthetic verification or retained intermediate/failed build; not for delivery"}
                   for p in sorted((ROOT / "data").glob("deployment-*")) if p.is_dir()]
    evidence_files = ["portable-final-operations.json", "portable-roundtrip.json", "https-browser-results-8448.json", "backup-standalone-retention.json",
                      "image-network-pragmas.json", "protected-before.json", "protected-final.json", "portable-preflight-ps51.json"]
    latest_recovery = max(EVIDENCE.glob("drill-recovery-*.json"), key=lambda p:p.stat().st_mtime)
    evidence_files.append(latest_recovery.name)
    report = {
        "status": "local engineering validation complete; orchestrate/human acceptance and site deployment pending",
        "kit": str(KIT), "release": release, "archive_bytes": (KIT / "fucheng-images.tar").stat().st_size,
        "package_checksums": checksums, "image_scan": image_scan, "pragmas": pragmas, "backup_sidecars": lifecycle,
        "evidence_files": evidence_files, "preservation": preservation,
        "git": {"head": run("git", "rev-parse", "HEAD"), "branch": run("git", "branch", "--show-current"), "worktrees": run("git", "worktree", "list"), "status": run("git", "status", "--short")},
        "resources": {"containers": containers, "volumes": volumes, "networks": networks, "directories": directories,
            "old_8447_stopped": True, "new_8448_retained": True,
            "stop_preview": "powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\\projects\\fucheng-players-system\\data\\deployment-portable-test-20260920-r7\\operate.ps1 Stop",
            "old_sidecar_accumulation": "3760 pairs of .partial-wal/.partial-shm retained in fucheng-deploytest-20260919_backups; stopped old short-interval test; not broadly cleaned",
            "volume_purposes": "deploytest: historical synthetic workflows and fault evidence; upgrade: old-source rollback fixture; interrupted*: init recovery fixtures; portable-20260919: failed-import continuation; portable-20260920: final HTTPS preview; roundtrip-20260920: final returned backup restore",
            "cleanup": "No volumes, networks, image tags, failed directories or existing shared resources removed"},
        "unverified": ["real named tunnel and domain/account", "club PC/phone/power/reboot", "authoritative real data and migration authorization", "actual offsite backup custody", "human acceptance"],
        "delivery": {"commit": False, "merge": False, "push": False, "registry": False, "public_tunnel": False, "real_data_migration": False},
    }
    (EVIDENCE / "deployment-final.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "PASS", "report": str(EVIDENCE / "deployment-final.json"), "archive_sha256": release["archive_sha256"], "archive_bytes": report["archive_bytes"], "source_files": len(manifest["files"]), "volumes_retained": len(volumes)}))


if __name__ == "__main__":
    main()
