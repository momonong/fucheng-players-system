"""Trusted subprocess entry point. No caller supplied URL, command, TLS or proxy settings."""
import json
import sys
import socket
import threading
import time
import urllib.error
import urllib.request
from uuid import UUID

ENDPOINT = 'https://momonong.me/fucheng/api/deployment-reports'
PROBE_ENDPOINTS = {'cloudflare_https': 'https://www.cloudflare.com/',
                   'registry_https': 'https://registry-1.docker.io/v2/'}
TCP_REGIONS = {'region1': 'region1.v2.argotunnel.com', 'region2': 'region2.v2.argotunnel.com'}
PROBE_BUDGET = 7


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _https_probe(opener, key, url):
    try:
        with opener.open(urllib.request.Request(url, method='HEAD'), timeout=3) as response:
            return response.status == 200
    except urllib.error.HTTPError as error:
        success = key == 'registry_https' and error.code == 401
        error.close()
        return success
    except Exception:
        return False


def _tcp_probe(host):
    try:
        with socket.create_connection((host, 7844), timeout=3):
            return True
    except Exception:
        return False


def _network_probes(opener):
    # Daemon workers let the child return completed results at the total budget,
    # even if libc DNS has not returned. Parent still kills/reaps at 10 seconds.
    deadline = time.monotonic() + PROBE_BUDGET
    values = {key: False for key in (*PROBE_ENDPOINTS, *TCP_REGIONS)}
    lock = threading.Lock()
    def record(key, probe, *args):
        value = probe(*args)
        with lock:
            values[key] = value
    workers = [threading.Thread(target=record, args=(key, _https_probe, opener, key, url), daemon=True)
               for key, url in PROBE_ENDPOINTS.items()]
    workers += [threading.Thread(target=record, args=(key, _tcp_probe, host), daemon=True)
                for key, host in TCP_REGIONS.items()]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=max(0, deadline-time.monotonic()))
    with lock:
        snapshot = values.copy()
    regions = {key: snapshot[key] for key in TCP_REGIONS}
    return {key: snapshot[key] for key in PROBE_ENDPOINTS} | {
        'cloudflare_tcp_7844': all(regions.values()), 'cloudflare_tcp_regions': regions}


def main():
    payload = json.loads(sys.stdin.buffer.read(300_000))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    if payload['action'] == 'probe':
        return _network_probes(opener)
    if payload['action'] != 'send':
        return {'outcome': 'unknown'}
    key = str(UUID(payload['report_id']))
    request = urllib.request.Request(ENDPOINT+'/'+key, data=payload['report'].encode('utf-8'), method='POST',
        headers={'Content-Type':'application/json', 'Origin':'https://momonong.me',
                 'X-Fucheng-Report-Token':payload['token']})
    try:
        with opener.open(request, timeout=5) as response:
            raw = response.read(4097)
            if response.status != 200 or len(raw) > 4096:
                return {'outcome':'unknown'}
            return {'outcome':'received', 'receipt':json.loads(raw)}
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        return {'outcome':'rejected','status':status} if 300 <= status < 500 else {'outcome':'unknown'}
    except Exception:
        return {'outcome':'unknown'}


if __name__ == '__main__':
    try:
        result = main()
    except Exception:
        result = {'outcome':'unknown'}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
