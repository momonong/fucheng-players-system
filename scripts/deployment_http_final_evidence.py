"""Read-only final HTTP preview/package evidence; excludes credentials and member rows."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "data/deployment-http-evidence-20260920"
KIT = ROOT / "data/deployment-release-20260920-r9"


def run(*args):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    releases = {}
    for version in (7, 8, 9):
        directory = ROOT / f"data/deployment-release-20260920-r{version}"
        for line in (directory / "SHA256SUMS.txt").read_text().splitlines():
            expected, name = line.split("  ", 1)
            assert Path(name).name == name and sha(directory / name) == expected
        releases[str(version)] = {"all_checksums": "PASS", "checksum_list_sha256": sha(directory / "SHA256SUMS.txt")}
    release = json.loads((KIT / "release.json").read_text())
    manifest = json.loads((KIT / "source-manifest.json").read_text())
    assert sha(KIT / "source-manifest.json") == release["source_manifest_sha256"]
    with zipfile.ZipFile(KIT / "source-snapshot.zip") as z:
        for name, digest in manifest["files"].items():
            assert sha(ROOT / name) == sha(KIT / "build-context" / name) == digest
            assert hashlib.sha256(z.read(name)).hexdigest() == digest
    app = json.loads(run("docker", "inspect", "fucheng-http-synthetic-20260920-app-1"))[0]
    assert app["Image"] == release["image_id"] and app["State"]["Health"]["Status"] == "healthy"
    assert {v["HostIp"] for v in app["NetworkSettings"]["Ports"]["8000/tcp"]} == {"127.0.0.1", "::1"}
    assert app["HostConfig"]["ReadonlyRootfs"]
    https = json.loads(run("docker", "inspect", "fucheng-portable-20260920-app-1"))[0]
    assert https["Image"] == "sha256:9c9debe226d721af860a96a11de90eb0128f54f9d9965f69c28712773e665d3d"
    assert https["State"]["Health"]["Status"] == "healthy"
    paths = {}
    for flag in ("-4", "-6"):
        paths[flag] = run("curl.exe", flag, "--noproxy", "*", "--max-time", "8", "-sS", "-o", "NUL", "-w", "%{http_code}", "http://localhost:8450/")
        assert paths[flag] == "200"
    assert json.loads((E / "protected-final.json").read_text()) == json.loads((ROOT / "data/deployment-evidence-20260919/protected-before.json").read_text())
    iab = json.loads((E / "iab-evidence.json").read_text())
    assert all(iab[k] for k in ("home", "login", "member_edit_saved", "competitions_page", "logout_to_login"))
    api = json.loads((E / "http-api-evidence.json").read_text())
    api["browser_acceptance_at_api_run"] = api["browser_acceptance"]
    api["browser_acceptance"] = "PASS; superseded by subsequent actual CUA IAB evidence in iab-evidence.json"
    report = {
        "status": "local HTTP engineering and actual IAB validation PASS; human acceptance pending",
        "url": "http://localhost:8450/", "project": "fucheng-http-synthetic-20260920",
        "credentials_file": str(E / "synthetic-admin.json"), "kit": str(KIT), "release": release,
        "archive_bytes": (KIT / "fucheng-images.tar").stat().st_size, "releases": releases,
        "ipv4_ipv6": paths, "iab": iab, "api": api,
        "evidence_index": {"final_browser_result": "iab-evidence.json: PASS", "earlier_api_snapshot": "http-api-evidence.json records PENDING only at the earlier API step; resolved by iab-evidence.json", "session_isolation": "cookie-isolation.json: PASS"},
        "cookies": json.loads((E / "cookie-isolation.json").read_text()),
        "protected_original_inventory_identical": True,
        "https_original_image_and_healthy": True, "https_container_id": https["Id"],
        "http_container_id": app["Id"], "mounts": [{"name": m.get("Name"), "destination": m["Destination"]} for m in app["Mounts"]],
        "network": app["NetworkSettings"]["Networks"],
        "head": run("git", "rev-parse", "HEAD"), "branch": run("git", "branch", "--show-current"),
        "worktrees": run("git", "worktree", "list"), "git_status": run("git", "status", "--short"),
        "running_services": run("docker", "ps", "--format", "{{.Names}} {{.Status}} {{.Ports}}").splitlines(),
        "stop_command": f'powershell.exe -NoProfile -File "{KIT / "local-http.ps1"}" Stop -EnvFile "{E / "local-http.env"}"',
        "tests": "78 passed / 2 existing upstream warnings; actual IAB UI and separate API cookie-jar evidence",
        "limits": ["synthetic-only local preview", "no outbound isolation on standalone bridge", "no public Tunnel/LAN exposure", "no real-data migration", "no commit/merge/push", "no human acceptance claim"],
    }
    (E / "http-final.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "PASS", "report": str(E / "http-final.json"), "url": report["url"], "archive_sha256": release["archive_sha256"]}))


if __name__ == "__main__":
    main()
