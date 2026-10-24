"""Bound DNS, TLS and slow HTTP bodies with a killable, fixed stdlib helper."""
import json
import subprocess
import sys
from pathlib import Path

ENDPOINT = 'https://momonong.me/fucheng/api/deployment-reports'
PROBE_ENDPOINTS = {'cloudflare_https': 'https://www.cloudflare.com/',
                   'registry_https': 'https://registry-1.docker.io/v2/'}


class DeliveryRejected(Exception):
    def __init__(self, status: int):
        self.status = status
        super().__init__('接收站明確拒收')


def _helper(payload: dict, timeout: float):
    try:
        completed = subprocess.run(
            [sys.executable, '-I', str(Path(__file__).with_name('report_transport.py'))],
            input=json.dumps(payload, ensure_ascii=False).encode('utf-8'), stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=timeout, check=False, shell=False)
        if completed.returncode or len(completed.stdout) > 8192:
            raise ValueError('invalid helper result')
        return json.loads(completed.stdout)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        raise TimeoutError('網路結果未確認；請保留原報告 ID 重送') from None


def probe_network() -> dict:
    try:
        return _helper({'action': 'probe'}, 10)
    except TimeoutError:
        return {key: False for key in PROBE_ENDPOINTS} | {'cloudflare_tcp_7844': False, 'cloudflare_tcp_regions': {'region1': False, 'region2': False}}


def deliver_report(report_id: str, device_id: str, raw: bytes, token: str) -> dict:
    # Token goes through stdin only, never command line, environment or exception text.
    result = _helper({'action': 'send', 'report_id': report_id,
                      'token': token, 'report': raw.decode('utf-8')}, 15)
    if result.get('outcome') == 'rejected':
        raise DeliveryRejected(int(result['status']))
    if result.get('outcome') != 'received':
        raise TimeoutError('回傳結果未確認')
    return result['receipt']
