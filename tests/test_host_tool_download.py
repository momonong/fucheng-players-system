"""Only immutable allowlisted bytes may be downloaded, never arbitrary files."""
from dataclasses import replace
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from fucheng.app import create_app


def test_immutable_download_allowlist_hash_mismatch_and_symlink(app,tmp_path):
    directory=tmp_path/'tools';directory.mkdir()
    script=b'\xef\xbb\xbf# fixture script'
    digest=hashlib.sha256(script).hexdigest()
    (directory/'bootstrap.ps1').write_bytes(script)
    (directory/'secret.txt').write_text('fixture-only-private-file')
    application=create_app(replace(app.state.settings,host_tools_dir=directory))
    try:
        with TestClient(application) as c:
            response=c.get(f'/api/deployment-tools/{digest}/bootstrap.ps1')
            assert response.status_code==200 and response.content==script
            assert response.headers['X-Content-Type-Options']=='nosniff'
            for path in (f'/api/deployment-tools/{digest}/secret.txt',f'/api/deployment-tools/{"0"*64}/bootstrap.ps1',f'/api/deployment-tools/{digest}/tools.zip'):
                assert c.get(path).status_code==404
            (directory/'bootstrap.ps1').unlink()
            (directory/'bootstrap.ps1').symlink_to(directory/'secret.txt')
            assert c.get(f'/api/deployment-tools/{digest}/bootstrap.ps1').status_code==404
    finally:application.state.engine.dispose()


def test_download_bundle_hashes_are_resolved_and_packaged_without_credentials(tmp_path):
    import importlib.util
    import json
    import zipfile
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('download_package',root/'scripts/club_host_one_shot_package.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.ROOT=tmp_path
    for source in set(module.FILES)|module.DOWNLOAD_SOURCES:
        path=tmp_path/source;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((root/source).read_bytes())
    output=tmp_path/'data/download'
    result=module.create_download_bundle(output)
    bootstrap=(output/'bootstrap.ps1').read_bytes(); launcher=(output/'launcher.ps1').read_bytes()
    assert b'@@' not in bootstrap+launcher
    assert result['bootstrap_sha256']==hashlib.sha256(bootstrap).hexdigest()
    assert result['tools_sha256']==hashlib.sha256((output/'tools.zip').read_bytes()).hexdigest()
    assert result['bootstrap_sha256'].encode() in launcher and result['tools_sha256'].encode() in bootstrap
    with zipfile.ZipFile(output/'tools.zip') as z:
        assert 'bootstrap.ps1' not in z.namelist()
        assert not any(n.endswith('club-report.json') or n.endswith('token.txt') for n in z.namelist())
        assert z.read('deploy/docker/club-host-credential.ps1').startswith(b'\xef\xbb\xbf')
    with pytest.raises(FileExistsError):module.create_download_bundle(output)
