"""Administrator report storage, validation, secrecy, and downloads."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from fucheng.deployment_report import REQUIRED_CHECKS
from fucheng.models import DeploymentReport, DeploymentReportAudit


def report():
    return {
        "schema_version": 1,
        "checked_at": datetime.now(UTC).isoformat(),
        "host": {"name": "Synthetic-Pro", "windows": "Windows 11 Pro", "build": "26200",
                 "install_drive_free_gib": 80.5, "docker_platform": "linux/x86_64",
                 "docker_server_version": "28.5.1"},
        "scope": {"read_only_probes": True, "created_report_directory": True,
                  "external_network_opt_in": False, "container_execution": False,
                  "live_volume_access": False, "compose_project": None, "test_port": 8052,
                  "proposed_docker_subnet": "172.30.98.0/24"},
        "summary": {"PASS": len(REQUIRED_CHECKS), "WARN": 0, "FAIL": 0, "NOT_TESTED": 0},
        "checks": [{"id": item, "status": "PASS", "reason": "Synthetic check",
                    "evidence": "synthetic only", "next_action": "Inspect host"}
                   for item in sorted(REQUIRED_CHECKS)],
        "recommendations": [{"candidate": "Tunnel", "status": "NOT_TESTED",
                             "reason": "No real network was tested", "next_action": "Check on host"}],
        "sources": ["https://example.org/docs"],
    }


def upload(client, payload, *, headers=None, version=0):
    return client.post(f"/api/admin/deployment-report?version={version}",
                       content=json.dumps(payload).encode(),
                       headers={"Content-Type": "application/json", **(headers or {})})


def test_admin_upload_download_and_audit(app, client, auth):
    with TestClient(app) as visitor:
        assert visitor.get('/api/admin/deployment-report').status_code == 401
        assert visitor.get('/api/admin/deployment-report/json').status_code == 401
        assert visitor.get('/api/admin/deployment-report/markdown').status_code == 401
        assert upload(visitor, report()).status_code == 401
    assert upload(client, report()).status_code == 403  # logged in but missing CSRF
    assert client.get('/api/admin/deployment-report').json()['version'] == 0
    saved = upload(client, report(), headers=auth)
    assert saved.status_code == 200, saved.text
    assert saved.json()['version'] == 1
    assert saved.json()['report']['host']['name'] == 'Synthetic-Pro'
    assert saved.headers['Cache-Control'] == 'no-store'
    assert client.get('/api/admin/deployment-report').json()['version'] == 1
    for format in ('json', 'markdown'):
        response = client.get(f'/api/admin/deployment-report/{format}')
        assert response.status_code == 200
        assert response.headers['Cache-Control'] == 'no-store'
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
        assert 'attachment;' in response.headers['Content-Disposition']
        assert 'Synthetic-Pro' in response.text
    with app.state.session_factory() as db:
        row = db.get(DeploymentReport, 1)
        audits = db.scalars(select(DeploymentReportAudit)).all()
        assert row.version == 1 and len(audits) == 1
        assert row.sha256 == audits[0].sha256 and audits[0].version == 1


def test_invalid_oversized_conflict_and_xss_preserve_previous(app, client, auth):
    first = report()
    assert upload(client, first, headers=auth).status_code == 200
    marker = '<img src=x onerror="alert(1)">'
    evil = report()
    evil['host']['name'] = marker
    assert upload(client, evil, headers=auth, version=0).status_code == 409
    assert client.get('/api/admin/deployment-report').json()['report']['host']['name'] == 'Synthetic-Pro'
    bad = report()
    bad['summary']['PASS'] = 1
    assert upload(client, bad, headers=auth, version=1).status_code == 422
    bad = report()
    bad['checks'][0]['status'] = 'EXECUTE'
    assert upload(client, bad, headers=auth, version=1).status_code == 422
    bad = report()
    bad['host']['unexpected'] = 'path'
    assert upload(client, bad, headers=auth, version=1).status_code == 422
    assert client.post('/api/admin/deployment-report?version=1', content=b'x' * (256 * 1024 + 1),
                       headers={'Content-Type': 'application/json', **auth}).status_code == 413
    assert client.post('/api/admin/deployment-report?version=1', content=b'{"schema_version":1,"schema_version":1}',
                       headers={'Content-Type': 'application/json', **auth}).status_code == 422
    assert client.get('/api/admin/deployment-report').json()['version'] == 1
    assert upload(client, evil, headers=auth, version=1).status_code == 200
    view = client.get('/api/admin/deployment-report').json()
    assert view['report']['host']['name'] == marker
    assert marker not in view['markdown']
    markdown = client.get('/api/admin/deployment-report/markdown').text
    assert marker not in markdown and '&lt;img' in markdown
    with app.state.session_factory() as db:
        assert len(db.scalars(select(DeploymentReportAudit)).all()) == 2


def test_report_survives_new_app_instance(app, client, auth):
    assert upload(client, report(), headers=auth).status_code == 200
    from fucheng.app import create_app
    reopened = create_app(app.state.settings)
    try:
        with TestClient(reopened) as other:
            other.cookies.update(client.cookies)
            result = other.get('/api/admin/deployment-report')
            assert result.status_code == 200
            assert result.json()['report']['host']['name'] == 'Synthetic-Pro'
    finally:
        reopened.state.engine.dispose()
