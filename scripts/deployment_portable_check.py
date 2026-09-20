"""Verify the delivered kit with Windows helpers, from an independent directory.

Only named synthetic projects below are touched. No Git, uv, npm or original
source tree is required by the copied runtime kit.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "data/deployment-release-20260920-r7"
PORTABLE = ROOT / "data/deployment-portable-test-20260920-r7"
EVIDENCE = ROOT / "data/deployment-evidence-20260919"
PROJECT = "fucheng-portable-20260920"
events = []


def command(argv, *, success=True, cwd=PORTABLE):
    result = subprocess.run(argv, cwd=cwd, capture_output=True)
    stdout, stderr = result.stdout.decode("utf-8", "replace"), result.stderr.decode("utf-8", "replace")
    events.append({"command": argv, "exit": result.returncode, "stdout": stdout, "stderr": stderr})
    if (result.returncode == 0) != success:
        raise RuntimeError(f"Unexpected exit {result.returncode}: {argv}\n{stdout}\n{stderr}")
    return stdout


def operate(action, *args, success=True):
    return command(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PORTABLE / "operate.ps1"), action, *args], success=success)


def main():
    if PORTABLE.exists():
        raise SystemExit("Portable verification directory already exists; refusing overwrite")
    PORTABLE.mkdir()
    for path in KIT.iterdir():
        if path.is_file():
            shutil.copyfile(path, PORTABLE / path.name)
    command(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PORTABLE / "load-images.ps1")])
    release = json.loads((PORTABLE / "release.json").read_text())
    (PORTABLE / "release.env").write_text(f"COMPOSE_PROJECT_NAME={PROJECT}\nFUCHENG_IMAGE={release['image']}\nFUCHENG_PUBLIC_ORIGIN=https://localhost:8448\nFUCHENG_PROXY_KIND=local\nFUCHENG_SUBNET=172.30.100.0/24\nFUCHENG_APP_IP=172.30.100.2\nFUCHENG_PROXY_IP=172.30.100.3\nFUCHENG_HTTPS_PORT=8448\n")
    exported = EVIDENCE / "export-verified"
    manifest = json.loads((exported / "export-manifest.json").read_text(encoding="utf-8-sig"))
    backup = exported / manifest["checkpoint"]
    before = hashlib.sha256(backup.read_bytes()).hexdigest()
    operate("ImportBackup", "-Value", str(backup))
    operate("ImportBackup", "-Value", str(backup), success=False)
    assert "Import destination exists" in events[-1]["stderr"]
    operate("Restore", "-Value", backup.name)
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == before
    command(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PORTABLE / "test-tls.ps1"), "-Image", release["image"]])
    operate("StartTest")
    operate("Status")
    operate("Migrate", success=False)
    assert "volume lock" in events[-1]["stderr"]
    # Return an actual new, normalized single-file backup using only the copied kit.
    output = EVIDENCE / "portable-export-r7"
    operate("ExportBackups", "-Value", str(output))
    operate("ExportBackups", "-Value", str(output), success=False)
    assert "Export refuses existing" in events[-1]["stderr"]
    # Verify Windows-side rejection before Docker can import a damaged file.
    bad_dir = EVIDENCE / "portable-corrupt-import-r7"
    bad_dir.mkdir()
    bad_db = bad_dir / backup.name
    bad_db.write_bytes(backup.read_bytes() + b"synthetic-corruption")
    shutil.copyfile(backup.with_suffix(".json"), bad_db.with_suffix(".json"))
    operate("ImportBackup", "-Value", str(bad_db), success=False)
    assert "checksum mismatch" in events[-1]["stderr"]
    print("PASS: Windows PowerShell 5.1 independent kit load/import/restore/start/export and overwrite/checksum/maintenance rejection")


if __name__ == "__main__":
    try:
        main()
    finally:
        (EVIDENCE / "portable-final-operations.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
