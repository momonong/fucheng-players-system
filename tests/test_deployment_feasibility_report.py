"""Active feasibility reports retain scope and device-receipt boundaries."""
import copy
import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from fucheng.deployment_report import REQUIRED_CHECKS, parse_report, render_markdown
from test_deployment_report import report as host_report, upload
from test_device_reports import HEADERS, device, send


FEASIBILITY_IDS = REQUIRED_CHECKS | set(
    'probe_image isolated_probe quick_tunnel public_https_nonce https_samples '
    'temporary_cleanup public_ip_observation static_ip_contract isp_inbound_policy'.split())


def report(*, execute=True, public=True):
    payload = host_report()
    payload['checked_at'] = payload['checked_at'].replace('+00:00', 'Z')
    payload.update(schema_version=3, report_type='deployment_feasibility')
    payload['scope'] = {
        'read_only_probes': False, 'container_execution': execute, 'host_control': False,
        'live_volume_access': False, 'temporary_public_probe': public,
        'external_network_opt_in': True,
    }
    payload['checks'] = [dict(id=key, status='NOT_TESTED', reason='Synthetic check',
        evidence='Synthetic nonce only', next_action='Check on target host')
        for key in sorted(FEASIBILITY_IDS)]
    if execute:
        for key in ('probe_image', 'isolated_probe', 'temporary_cleanup'):
            check(payload, key)['status'] = 'PASS'
    if public:
        for key in ('quick_tunnel', 'public_https_nonce', 'https_samples'):
            check(payload, key)['status'] = 'PASS'
    recount(payload)
    return payload


def check(payload, key):
    return next(item for item in payload['checks'] if item['id'] == key)


def recount(payload):
    payload['summary'] = {status: sum(item['status'] == status for item in payload['checks'])
                          for status in ('PASS', 'WARN', 'FAIL', 'NOT_TESTED')}


@pytest.mark.parametrize(('execute', 'public'), [(True, True), (True, False), (False, False)])
def test_schema3_accepts_success_and_failed_or_unstarted_probes(execute, public):
    payload = report(execute=execute, public=public)
    if not public:
        check(payload, 'quick_tunnel')['status'] = 'FAIL'
        recount(payload)
    parsed = parse_report(json.dumps(payload).encode())
    assert parsed.schema_version == 3
    assert len(parsed.checks) == 44
    assert parsed.model_dump(mode='json') == payload


@pytest.mark.parametrize('invalid', [
    'duplicate', 'missing', 'unexpected', 'summary', 'naive_time', 'source', 'extra',
    'read_only_probes', 'host_control', 'live_volume_access', 'external_network_opt_in',
    'public_without_container', 'isolated_without_container', 'tunnel_without_container',
    'nonce_without_container', 'samples_without_container', 'tunnel_without_scope',
    'nonce_without_scope', 'nonce_without_tunnel', 'samples_without_tunnel',
    'samples_without_nonce', 'static_ip_contract', 'isp_inbound_policy', 'public_ingress',
])
def test_schema3_rejects_inconsistent_or_overclaimed_reports(invalid):
    payload = report()
    if invalid == 'duplicate': payload['checks'][0]['id'] = payload['checks'][1]['id']
    elif invalid == 'missing': payload['checks'].pop()
    elif invalid == 'unexpected': payload['checks'][0]['id'] = 'unknown_check'
    elif invalid == 'summary': payload['summary']['PASS'] += 1
    elif invalid == 'naive_time': payload['checked_at'] = '2026-10-30T00:00:00'
    elif invalid == 'source': payload['sources'] = ['http://example.org/']
    elif invalid == 'extra': payload['scope']['other'] = False
    elif invalid in ('read_only_probes', 'host_control', 'live_volume_access'):
        payload['scope'][invalid] = True
    elif invalid == 'external_network_opt_in': payload['scope'][invalid] = False
    elif invalid == 'public_without_container': payload['scope']['container_execution'] = False
    elif invalid in ('isolated_without_container', 'tunnel_without_container', 'nonce_without_container', 'samples_without_container'):
        payload = report(execute=False, public=False)
        key = {'isolated_without_container': 'isolated_probe', 'tunnel_without_container': 'quick_tunnel',
               'nonce_without_container': 'public_https_nonce', 'samples_without_container': 'https_samples'}[invalid]
        check(payload, key)['status'] = 'PASS'
    elif invalid in ('tunnel_without_scope', 'nonce_without_scope'):
        payload['scope']['temporary_public_probe'] = False
    elif invalid == 'nonce_without_tunnel': check(payload, 'quick_tunnel')['status'] = 'FAIL'
    elif invalid == 'samples_without_tunnel':
        check(payload, 'quick_tunnel')['status'] = 'FAIL'
        check(payload, 'public_https_nonce')['status'] = 'FAIL'
    elif invalid == 'samples_without_nonce': check(payload, 'public_https_nonce')['status'] = 'FAIL'
    else: check(payload, invalid)['status'] = 'PASS'
    if invalid != 'summary': recount(payload)
    with pytest.raises(HTTPException) as error:
        parse_report(json.dumps(payload).encode())
    assert error.value.status_code == 422


def test_schema3_device_receipt_replay_conflict_admin_list_download_and_auth(app, admin_password):
    payload = report()
    payload['host']['name'] = '<img src=x onerror="alert(1)">'
    check(payload, 'quick_tunnel')['evidence'] = '<script>alert(1)</script> | [link](https://example.org)'
    with device(app) as client:
        key = str(uuid4())
        assert client.post('/api/deployment-reports/' + key, json=payload).status_code == 401
        first = send(client, payload, key=key)
        assert first.status_code == 200, first.text
        assert send(client, payload, key=key).json() == first.json()
        changed = copy.deepcopy(payload)
        changed['host']['name'] = 'changed'
        assert send(client, changed, key=key).status_code == 409
        for path in ('/api/admin/deployment-reports', f'/api/admin/deployment-reports/{key}/json',
                     f'/api/admin/deployment-reports/{key}/markdown'):
            assert client.get(path, headers=HEADERS).status_code == 401
        assert client.post('/api/auth/login', json={'username':'admin', 'password':admin_password}).status_code == 200
        listed = client.get('/api/admin/deployment-reports')
        assert listed.status_code == 200, listed.text
        assert listed.json()['items'][0]['claimed_host_name'] == payload['host']['name']
        assert client.get(f'/api/admin/deployment-reports/{key}/json').json() == payload
        markdown = client.get(f'/api/admin/deployment-reports/{key}/markdown')
        assert markdown.status_code == 200
        assert markdown.headers['X-Fucheng-Report-Digest'] == first.json()['digest']
        assert '<img' not in markdown.text and '<script' not in markdown.text
        assert '&lt;img' in markdown.text and r'\[link\]' in markdown.text
        assert '臨時主動測試' in markdown.text
        assert '真實資料 volume' in markdown.text and '手機外網驗收' in markdown.text


def test_schema3_manual_upload_preserves_admin_csrf_and_downloads(app, client, auth):
    payload = report(execute=False, public=False)
    with TestClient(app) as visitor:
        assert upload(visitor, payload).status_code == 401
    assert upload(client, payload).status_code == 403
    saved = upload(client, payload, headers=auth)
    assert saved.status_code == 200, saved.text
    assert saved.json()['report'] == payload
    assert client.get('/api/admin/deployment-report/json').json() == payload
    assert client.get('/api/admin/deployment-report/markdown').text == render_markdown(parse_report(json.dumps(payload).encode()))


def test_schema3_manual_upload_still_rejects_schema2(client, auth):
    generated = client.post('/api/admin/deployment-report/run', headers=auth,
        json={'version': 0, 'request_id': str(uuid4()), 'probe_network': False})
    assert generated.status_code == 200, generated.text
    payload = generated.json()['report']
    assert payload['schema_version'] == 2
    assert upload(client, payload, headers=auth, version=1).status_code == 422
    assert client.get('/api/admin/deployment-report').json()['report'] == payload
