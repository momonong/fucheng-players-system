"""Build/export an auditable dirty source snapshot; never package databases or secrets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SUPPORT_IMAGES = [
    "nginx@sha256:ef8676b33d681f272ba429b27658bdd7e640963279714c96bddf1dc76307f7b6",
    "cloudflare/cloudflared@sha256:b269e8abd07a5bf6f3f4be65d5050b2174eca89c56a0241a8ff32a16aec454e4",
    "ngrok/ngrok@sha256:14d80d083e5b53145f416bbbd36238336c9de4016c43fd950eb2eb845670583b",
]


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(*args, capture=False):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, encoding="utf-8", capture_output=capture).stdout


def source_files():
    files = [ROOT / p for p in ["Dockerfile", ".dockerignore", "pyproject.toml", "uv.lock", "alembic.ini"]]
    for pattern in ["src/fucheng/*.py", "migrations/env.py", "migrations/versions/*.py",
                    "frontend/package*.json", "frontend/index.html", "frontend/tsconfig*.json",
                    "frontend/vite.config.ts", "frontend/src/**/*.ts", "frontend/src/**/*.tsx",
                    "frontend/src/**/*.css", "deploy/docker/runtime.py"]:
        files.extend(ROOT.glob(pattern))
    return sorted(set(files))


def make_manifest():
    files = source_files()
    clean = not run("git", "status", "--porcelain", "--untracked-files=all", capture=True).strip()
    manifest = {"kind": "committed-git-release" if clean else "uncommitted-working-tree-snapshot",
                "head": run("git", "rev-parse", "HEAD", capture=True).strip(),
                "branch": run("git", "branch", "--show-current", capture=True).strip(),
                "files": {p.relative_to(ROOT).as_posix(): sha(p) for p in files}}
    path = ROOT / "deploy/docker/source-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path, files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["build", "export", "refresh-kit"])
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    # Output stays under protected, ignored data/; no accidental release over a source directory.
    if not out.is_relative_to(ROOT / "data"):
        raise SystemExit("Output must be below this repository's data directory")
    out.mkdir(parents=True, exist_ok=True)
    if args.action == "build":
        manifest_path, files = make_manifest()
        digest = sha(manifest_path)
        tag = f"local/fucheng:snapshot-{digest[:16]}"
        # Stage only explicit source files: Docker never even traverses the private workspace.
        context = out / "build-context"
        if context.exists():
            raise SystemExit("Use a fresh output directory for each build")
        for path in files + [manifest_path]:
            target = context / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        run("docker", "build", "--platform", "linux/amd64", "--build-arg", f"SOURCE_SHA256={digest}", "-t", tag, str(context))
        audit_dir = out / "context-audit"
        if audit_dir.exists():
            raise SystemExit("Use a fresh output directory for the context audit")
        run("docker", "build", "--target", "context-audit", "--output", f"type=local,dest={audit_dir}", str(context))
        actual = {p.relative_to(audit_dir).as_posix(): sha(p) for p in audit_dir.rglob("*") if p.is_file()}
        wanted = {p.relative_to(ROOT).as_posix(): sha(p) for p in files + [manifest_path]}
        if actual != wanted:
            raise SystemExit(f"Build context mismatch: extra={set(actual)-set(wanted)}, missing={set(wanted)-set(actual)}")
        image_info = json.loads(run("docker", "image", "inspect", tag, capture=True))[0]
        release = {"image": tag, "image_id": image_info["Id"], "platform": "linux/amd64", "source_manifest_sha256": digest,
                   "head_is_not_complete_source": json.loads(manifest_path.read_text(encoding="utf-8"))["kind"] != "committed-git-release",
                   "support_images": SUPPORT_IMAGES, "context_files": len(actual)}
        (out / "release.json").write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
        (out / "source-manifest.json").write_bytes(manifest_path.read_bytes())
        print(json.dumps(release))
    else:
        release = json.loads((out / "release.json").read_text())
        frozen_manifest = json.loads((out / "source-manifest.json").read_text())
        if sha(out / "source-manifest.json") != release["source_manifest_sha256"]:
            raise SystemExit("Frozen source manifest changed")
        context = out / "build-context"
        if sha(context / "deploy/docker/source-manifest.json") != release["source_manifest_sha256"]:
            raise SystemExit("Frozen context manifest changed")
        if json.loads(run("docker", "image", "inspect", release["image"], capture=True))[0]["Id"] != release["image_id"]:
            raise SystemExit("Release image tag no longer matches its verified image ID")
        for name, expected_hash in frozen_manifest["files"].items():
            if sha(context / name) != expected_hash:
                raise SystemExit(f"Frozen build context changed: {name}")
        archive = out / "fucheng-images.tar"
        if args.action == "export" and archive.exists():
            raise SystemExit("Image archive exists; do not overwrite a release")
        if args.action == "export":
            tagged = []
            for reference in SUPPORT_IMAGES:
                run("docker", "pull", "--platform", "linux/amd64", reference)
                name = reference.split("@")[0].split("/")[-1]
                alias = f"local/fucheng-support-{name}:{reference.split(':')[-1][:16]}"
                run("docker", "tag", reference, alias)
                tagged.append({"reference": reference, "tag": alias, "image_id": json.loads(run("docker", "image", "inspect", alias, capture=True))[0]["Id"]})
            release["offline_support"] = tagged
            run("docker", "save", "-o", str(archive), release["image"], *[x["tag"] for x in tagged])
            release["archive_sha256"] = sha(archive)
            (out / "release.json").write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
        else:
            tagged = release["offline_support"]
            if sha(archive) != release["archive_sha256"]:
                raise SystemExit("Image archive changed; cannot refresh kit")
        # Save/load preserves tags; use those local tags in the portable compose to avoid implicit pulls.
        for name in ["compose.yaml", "compose.cloudflare.yaml", "compose.ngrok.yaml", "compose.host-ngrok.yaml",
                     "nginx-test.conf", "nginx-host-ngrok.conf", "release.env.example", "ngrok.yml.example",
                     "operate.ps1", "preflight.ps1", "load-images.ps1", "test-tls.ps1",
                     "compose.local-http.yaml", "local-http.ps1", "local-http.env.example"]:
            text = (ROOT / "deploy/docker" / name).read_text(encoding="utf-8")
            for support in tagged:
                text = text.replace(support["reference"], support["tag"])
            (out / name).write_text(text, encoding="utf-8")
        (out / "deployment.md").write_bytes((ROOT / "docs/deployment.md").read_bytes())
        names = list(frozen_manifest["files"]) + ["deploy/docker/source-manifest.json"]
        if args.action == "export":
            with zipfile.ZipFile(out / "source-snapshot.zip", "x", compression=zipfile.ZIP_DEFLATED) as zf:
                for name in names:
                    zf.write(context / name, name)
        else:
            with zipfile.ZipFile(out / "source-snapshot.zip") as zf:
                if set(zf.namelist()) != set(names) or any(zf.read(name) != (context / name).read_bytes() for name in names):
                    raise SystemExit("Frozen source ZIP changed")
        (out / "SHA256SUMS.txt").write_text("".join(f"{sha(p)}  {p.name}\n" for p in sorted(out.iterdir()) if p.is_file() and p.name != "SHA256SUMS.txt"), encoding="utf-8")
        print(json.dumps({"archive": str(archive), "sha256": release["archive_sha256"]}))


if __name__ == "__main__":
    main()
