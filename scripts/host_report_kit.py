"""Package only reviewed Windows scripts/docs; never collect private files."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "deploy/docker/host-preflight.ps1": "deploy/docker/host-preflight.ps1",
    "deploy/docker/host-preflight.sh": "deploy/docker/host-preflight.sh",
    "deploy/docker/send-host-report.ps1": "deploy/docker/send-host-report.ps1",
    "deploy/docker/check-and-send.ps1": "deploy/docker/check-and-send.ps1",
    "deploy/docker/check-and-send.cmd": "deploy/docker/check-and-send.cmd",
    "deploy/docker/club-report.example.json": "private/club-report.example.json",
    "docs/host-report-upload.md": "README.md",
}


def create_kit(output: Path) -> dict:
    output = output.resolve()
    if not output.is_relative_to(ROOT / "data") or output.suffix != ".zip":
        raise ValueError("Output must be a fresh .zip below this repository's data directory")
    payload = {destination: (ROOT / source).read_bytes() for source, destination in FILES.items()}
    # Windows PowerShell 5.1 interprets UTF-8 scripts without a BOM as ANSI.
    for name, content in payload.items():
        if name.endswith(".ps1") and not content.startswith(b"\xef\xbb\xbf"):
            payload[name] = b"\xef\xbb\xbf" + content
    payload["CHECK-AND-SEND.cmd"] = b'@echo off\r\ncall "%~dp0deploy\\docker\\check-and-send.cmd" %*\r\n'
    manifest = {"kind": "host-report-kit", "contains_credentials": False,
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payload.items())}}
    payload["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(payload.items()):
            archive.writestr(name, content)
    return {"archive": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "files": len(payload), "contains_credentials": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(json.dumps(create_kit(parser.parse_args().output)))


if __name__ == "__main__":
    main()
