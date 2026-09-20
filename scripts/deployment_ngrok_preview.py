"""Authorized public synthetic HTTPS preview; never print or log the ngrok token."""
import argparse
import json
from ipaddress import ip_network
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "data/deployment-ngrok-evidence-20260920"
KIT = ROOT / "data/deployment-release-20260920-r9"
PROJECT = "fucheng-ngrok-preview-20260920"


def run(*args, input=None, ok=True):
    result = subprocess.run(args, cwd=ROOT, input=input, capture_output=True)
    if ok and result.returncode:
        # Agent errors can contain configuration values; only expose codes and local action.
        codes = re.findall(rb"ERR_NGROK_\d+", result.stdout + result.stderr)
        raise SystemExit(f"Command failed ({args[0]}), exit={result.returncode}, ngrok_codes={list(set(x.decode() for x in codes))}")
    return result


def compose():
    return ["docker", "compose", "--env-file", str(E / "release.env"), "-f", str(KIT / "compose.yaml"), "-f", str(KIT / "compose.ngrok.yaml"), "--profile", "ngrok"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["discover", "initialize"])
    args = parser.parse_args()
    if args.action == "discover":
        if E.exists():
            raise SystemExit("Evidence/config directory exists; inspect rather than overwrite")
        networks = json.loads(run("docker", "network", "inspect", *run("docker", "network", "ls", "-q").stdout.decode().split()).stdout)
        assert not any(ip_network(c["Subnet"]).overlaps(ip_network("172.30.106.0/24")) for n in networks for c in (n["IPAM"].get("Config") or []) if c.get("Subnet"))
        names = run("docker", "ps", "-a", "--format", "{{.Names}}").stdout.decode()
        assert PROJECT not in names
        source = Path(os.environ["LOCALAPPDATA"]) / "ngrok/ngrok.yml"
        match = re.search(r"^\s*authtoken\s*:\s*(.+?)\s*$", source.read_text(encoding="utf-8"), re.M)
        if not match:
            raise SystemExit("No local ngrok token; human must configure it locally")
        E.mkdir()
        secret = E / "ngrok-secret.yml"
        secret.write_text('version: 3\nagent:\n  authtoken: ' + match.group(1) + '\n  web_addr: false\n  inspect_db_size: -1\n  remote_management: false\n  update_check: false\n  log: stdout\n  log_format: json\n  log_level: info\nendpoints:\n  - name: fucheng\n    upstream:\n      url: http://app:8000\n', encoding="utf-8")
        release = json.loads((KIT / "release.json").read_text())
        env = f"COMPOSE_PROJECT_NAME={PROJECT}\nFUCHENG_IMAGE={release['image']}\nFUCHENG_PUBLIC_ORIGIN=https://bootstrap.invalid\nFUCHENG_PROXY_KIND=ngrok\nFUCHENG_SUBNET=172.30.106.0/24\nFUCHENG_APP_IP=172.30.106.2\nFUCHENG_PROXY_IP=172.30.106.3\nFUCHENG_NGROK_CONFIG_FILE={secret.as_posix()}\nFUCHENG_BACKUP_INTERVAL=86400\nFUCHENG_BACKUP_KEEP=14\n"
        (E / "release.env").write_text(env, encoding="utf-8")
        checked = run("docker", "run", "--rm", "--network", "none", "--mount", f"type=bind,source={secret},target=/config.yml,readonly", "local/fucheng-support-ngrok:14d80d083e5b5314", "config", "check", "--config", "/config.yml", ok=False)
        if checked.returncode:
            raise SystemExit("ngrok configuration validation failed; no token output")
        run(*compose(), "up", "-d", "--no-deps", "ngrok")
        url = None
        codes = set()
        for _ in range(20):
            logs = run("docker", "logs", PROJECT + "-ngrok-1", ok=False)
            text = (logs.stdout + logs.stderr).decode("utf-8", "replace")
            codes.update(re.findall(r"ERR_NGROK_\d+", text))
            for line in text.splitlines():
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                candidate = record.get("url", "")
                if record.get("msg") == "started tunnel" and candidate.startswith("https://"):
                    url = candidate
            if url or codes:
                break
            time.sleep(1)
        if not url:
            run(*compose(), "stop", "ngrok", ok=False)
            (E / "discovery.json").write_text(json.dumps({"status": "FAILED", "ngrok_error_codes": sorted(codes)}))
            raise SystemExit(f"No HTTPS endpoint assigned; own agent stopped; codes={sorted(codes)}")
        parsed = urlsplit(url)
        assert parsed.scheme == "https" and parsed.hostname and not parsed.path and not parsed.query
        (E / "release.env").write_text(env.replace("https://bootstrap.invalid", url), encoding="utf-8")
        secret.write_text(secret.read_text(encoding="utf-8").replace("  - name: fucheng\n", f"  - name: fucheng\n    url: {url}\n"), encoding="utf-8")
        (E / "discovery.json").write_text(json.dumps({"status": "PASS", "url": url, "ngrok_token_present": True, "local_existing_agent_count": 0, "remote_account_sessions_not_enumerated": True, "configuration_valid": True}, indent=2))
        print(json.dumps({"status": "PASS", "url": url, "configuration": "private local file; token not displayed"}))
    else:
        origin = json.loads((E / "discovery.json").read_text())["url"]
        if (E / "synthetic-admin.json").exists():
            raise SystemExit("Initialization already attempted; inspect existing synthetic project")
        run(*compose(), "run", "--rm", "ops", "init")
        account = {"username": "ngrok-preview-admin", "password": secrets.token_urlsafe(24)}
        (E / "synthetic-admin.json").write_text(json.dumps(account), encoding="utf-8")
        run(*compose(), "run", "--rm", "-T", "ops", "admin", account["username"], input=(account["password"] + "\n" + account["password"] + "\n").encode())
        run(*compose(), "up", "-d", "--wait", "--wait-timeout", "90", "app", "backup", "ngrok")
        print(json.dumps({"status": "initialized", "url": origin, "credentials_file": str(E / "synthetic-admin.json")}))


if __name__ == "__main__":
    main()
