"""Fresh synthetic HTTP preview setup and API/volume isolation evidence, no UI claims."""
import hashlib
import argparse
import json
from pathlib import Path
import secrets
import subprocess

import httpx

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data/deployment-http-evidence-20260920"
KIT = ROOT / "data/deployment-release-20260920-r9"
PROJECT = "fucheng-http-synthetic-20260920"
ORIGIN = "http://localhost:8450"


def command(*args, input=None, ok=True):
    result = subprocess.run(args, cwd=ROOT, input=input, capture_output=True)
    if (result.returncode == 0) != ok:
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    EVIDENCE.mkdir(exist_ok=True)
    credentials = EVIDENCE / "synthetic-admin.json"
    if credentials.exists() and not args.verify_existing:
        raise SystemExit("Fresh drill only; existing credentials and volumes must be preserved")
    image = json.loads((KIT / "release.json").read_text())["image"]
    env = EVIDENCE / "local-http.env"
    env.write_text(f"FUCHENG_HTTP_PROJECT={PROJECT}\nFUCHENG_HTTP_PORT=8450\nFUCHENG_IMAGE={image}\n")
    compose = ["docker", "compose", "--env-file", str(env), "-f", str(KIT / "compose.local-http.yaml"), "--profile", "local-http"]
    config = json.loads(command(*compose, "config", "--format", "json").stdout)
    assert set(config["services"]) == {"app", "ops"}
    assert config["networks"]["local_preview"]["driver"] == "bridge"
    assert {p["host_ip"] for p in config["services"]["app"]["ports"]} == {"127.0.0.1", "::1"}
    existing = command("docker", "volume", "ls", "--format", "{{.Name}}").stdout.decode().splitlines()
    if not args.verify_existing:
        assert not any(v.startswith(PROJECT) for v in existing)
        command(*compose, "run", "--rm", "ops", "init")
        account = {"username": "http-preview-admin", "password": secrets.token_urlsafe(24)}
        credentials.write_text(json.dumps(account), encoding="utf-8")
        command(*compose, "run", "--rm", "-T", "ops", "admin", account["username"], input=(account["password"] + "\n" + account["password"] + "\n").encode())
    else:
        account = json.loads(credentials.read_text())
    command(*compose, "up", "-d", "--wait", "--wait-timeout", "90", "app")
    statuses = {}
    with httpx.Client(base_url=ORIGIN, trust_env=False) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/auth/me").status_code == 401
        assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
        assert client.post("/api/auth/login", json=account).status_code == 403
        assert client.post("/api/auth/login", json=account, headers={"Origin": "http://evil.example"}).status_code == 403
        for header in ["Forwarded", "X-Forwarded-For", "X-Forwarded-Proto", "X-Forwarded-Host", "CF-Connecting-IP"]:
            assert client.get("/api/health", headers={header: "spoofed"}).status_code == 400
        response = client.post("/api/auth/login", json=account, headers={"Origin": ORIGIN})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert "fucheng_http_preview_session=" in cookie and "Secure" not in cookie and "HttpOnly" in cookie
        h = {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}
        for name, level in [("HTTP合成甲", 3), ("HTTP合成乙", 5), ("HTTP合成丙", 7)]:
            assert client.post("/api/admin/members", headers=h, json={"name": name, "level": level, "diet": "unset", "is_active": True, "distinguishing_note": "本機HTTP合成預覽"}).status_code == 201
        assert client.post("/api/admin/competitions", headers=h, json={"name": "HTTP合成驗收場次", "competition_date": "2099-09-20", "registration_deadline": "2099-09-19T00:00:00+08:00", "capacity": 4, "status": "open", "notes": "純合成預覽，無真實會員資料"}).status_code == 201
        assert client.post("/api/auth/logout", headers={"Origin": ORIGIN}).status_code == 403
        # Even deliberately putting the HTTP token under the HTTPS cookie name cannot authenticate to the separate DB.
        http_token = client.cookies.get("fucheng_http_preview_session")
        with httpx.Client(verify=False, trust_env=False) as https:
            assert https.get("https://localhost:8448/api/auth/me", headers={"Cookie": "fucheng_session=" + http_token}).status_code == 401
        assert client.post("/api/auth/logout", headers=h).status_code == 204
        assert client.get("/api/auth/me").status_code == 401
    for action in ["restore", "import-backup", "migrate"]:
        result = command(*compose, "run", "--rm", "ops", action, "synthetic.db", ok=False)
        assert b"fresh synthetic initialization only" in result.stderr
        statuses[action + "_blocked"] = True
    # New HTTPS runtime cannot consume the marked HTTP volume (read-only check, no writes).
    result = command("docker", "run", "--rm", "--network", "none", "-v", PROJECT + "_synthetic_data:/data:ro", "-e", "FUCHENG_PUBLIC_ORIGIN=https://club.example", image, "inspect", ok=False)
    assert b"cannot be used for HTTPS deployment" in result.stderr
    statuses["http_volume_rejected_by_https"] = True
    # An unmarked fresh volume cannot be served as HTTP or imported into it.
    result = command("docker", "run", "--rm", "--network", "none", "-e", "FUCHENG_LOCAL_HTTP_PREVIEW=true", "-e", "FUCHENG_PUBLIC_ORIGIN=" + ORIGIN, "-e", "FUCHENG_COOKIE_SECURE=false", image, "serve", ok=False)
    assert b"Not a local HTTP synthetic preview volume" in result.stderr
    statuses["unmarked_volume_rejected"] = True
    results = {"origin": ORIGIN, "project": PROJECT, "credentials_file": str(credentials), "image": image,
               "api_boundary_and_cookie_checks": "PASS", "fresh_synthetic_members": 3,
               "fresh_synthetic_competitions": 1, "isolated_config": True, "volume_guards": statuses,
               "browser_acceptance": "PENDING actual CUA IAB", "compose_sha256": hashlib.sha256((KIT / "compose.local-http.yaml").read_bytes()).hexdigest()}
    (EVIDENCE / "http-api-evidence.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS", "evidence": str(EVIDENCE / "http-api-evidence.json"), "origin": ORIGIN}))


if __name__ == "__main__":
    main()
