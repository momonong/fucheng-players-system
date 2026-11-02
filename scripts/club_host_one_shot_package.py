"""Build an allowlisted, credential-free Windows one-shot check snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    'deploy/docker/club-host-network.ps1': 'deploy/docker/club-host-network.ps1',
    'deploy/docker/club-host-credential.ps1': 'deploy/docker/club-host-credential.ps1',
    'deploy/docker/host-preflight.ps1': 'deploy/docker/host-preflight.ps1',
    'deploy/docker/send-host-report.ps1': 'deploy/docker/send-host-report.ps1',
    'deploy/docker/club-host-one-shot.ps1': 'deploy/docker/club-host-one-shot.ps1',
    'deploy/docker/club-host-run.cmd': 'RUN-CHECK.cmd',
    'deploy/docker/club-host-new-check.cmd': 'NEW-CHECK.cmd',
    'deploy/docker/club-host-one-shot.example.json': 'private/club-report.example.json',
    'deploy/docker/launch-club-host-check.ps1': 'launch-club-host-check.ps1',
    'docs/club-host-one-shot.md': 'README.md',
}


def create_package(output: Path, *, download=False) -> dict:
    output = output.resolve()
    if not output.is_relative_to(ROOT/'data') or output.suffix != '.zip':
        raise ValueError('Output must be a fresh .zip below the repository data directory')
    payload = {}
    for source, destination in FILES.items():
        path = ROOT/source
        if path.is_symlink():
            raise ValueError('Allowlisted source must be a regular file')
        content = path.read_bytes()
        if destination.endswith('.ps1') and not content.startswith(b'\xef\xbb\xbf'):
            content = b'\xef\xbb\xbf' + content
        payload[destination] = content
    revision = None if download else subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,text=True,capture_output=True,check=False)
    manifest = {
        'schema_version':1, 'kind':'club-host-one-shot-kit', 'contains_credentials':False,
        'source_kind':'working-tree snapshot', 'base_commit':revision.stdout.strip() if revision and revision.returncode == 0 else None,
        'app_compatibility':'1.2.0',
        'files':{name:hashlib.sha256(content).hexdigest() for name,content in sorted(payload.items())},
    }
    payload['manifest.json'] = (json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,content in sorted(payload.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info,content)
    return {'archive':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'files':len(payload),'contains_credentials':False,'source_kind':'working-tree snapshot'}


ENDPOINT = 'https://momonong.me/fucheng/api/deployment-reports'
DEVICE_ID = 'club-windows-01'
DOWNLOAD_SOURCES = {'deploy/docker/club-host-bootstrap.ps1','deploy/docker/club-host-download-launcher.ps1'}


def create_download_bundle(output: Path) -> dict:
    output = output.resolve()
    if not output.is_relative_to(ROOT / 'data'):
        raise ValueError('Download bundle must stay below data/')
    output.mkdir(parents=True, exist_ok=False)
    package = create_package(output/'tools.zip', download=True)
    tools_hash = package['sha256']
    prefix = ENDPOINT.removesuffix('/deployment-reports')
    tools_url = prefix + '/deployment-tools/' + tools_hash + '/tools.zip'
    common = (ROOT/'deploy/docker/club-host-network.ps1').read_text(encoding='utf-8-sig')
    body = (ROOT/'deploy/docker/club-host-bootstrap.ps1').read_text(encoding='utf-8-sig')
    replacements = {'@@ENDPOINT@@':ENDPOINT, '@@DEVICE_ID@@':DEVICE_ID,
                    '@@ZIP_SHA256@@':tools_hash, '@@ZIP_URL@@':tools_url}
    for key,value in replacements.items():
        body = body.replace(key,value)
    bootstrap = (common+'\n'+body).encode('utf-8-sig')
    bootstrap_hash = hashlib.sha256(bootstrap).hexdigest()
    bootstrap_url = prefix + '/deployment-tools/' + bootstrap_hash + '/bootstrap.ps1'
    launcher = (ROOT/'deploy/docker/club-host-download-launcher.ps1').read_text(encoding='utf-8-sig')
    launcher = launcher.replace('@@BOOTSTRAP_URL@@',bootstrap_url).replace('@@BOOTSTRAP_SHA256@@',bootstrap_hash)
    (output/'bootstrap.ps1').write_bytes(bootstrap)
    (output/'launcher.ps1').write_text(launcher,encoding='utf-8-sig')
    result = {'schema_version':1,'contains_credentials':False,'source_kind':'working-tree snapshot',
              'tools_sha256':tools_hash,'bootstrap_sha256':bootstrap_hash,'bootstrap_url':bootstrap_url,
              'tools_url':tools_url,'launcher_sha256':hashlib.sha256((output/'launcher.ps1').read_bytes()).hexdigest()}
    (output/'download-manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--download',action='store_true')
    args=parser.parse_args()
    print(json.dumps(create_download_bundle(args.output) if args.download else create_package(args.output)))
