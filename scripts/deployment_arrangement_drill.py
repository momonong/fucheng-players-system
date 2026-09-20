"""Isolated 0006 -> 0007 image/volume rehearsal using an authorized synthetic backup.

No host ports, tunnels, real databases, cleanup, or implicit migration. A failed
run retains all resources and evidence; inspect them before choosing a new run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://arrangement-drill.invalid"

FINGERPRINT = """import json,sqlite3,hashlib
from pathlib import Path
root=Path('/data'); pointer=json.loads((root/'active.json').read_text())['database']
p=root/(ARG or pointer)
db=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True)
db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
tables={}
for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
 rows=db.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall()
 tables[name]={'count':len(rows),'sha256':hashlib.sha256(''.join(sorted(hashlib.sha256(repr(row).encode()).hexdigest() for row in rows)).encode()).hexdigest()}
print(json.dumps({'database':p.name,'tables':tables,'revision':db.execute('SELECT version_num FROM alembic_version').fetchone()[0]}))
db.close()
"""

API_WRITES = """import json,sys,urllib.request,http.cookies,uuid
account=json.load(sys.stdin);origin='https://arrangement-drill.invalid'
headers={'Host':'arrangement-drill.invalid','Origin':origin,'Content-Type':'application/json'}
def call(path,payload=None,method=None):
 req=urllib.request.Request('http://127.0.0.1:8000'+path,headers=headers,data=json.dumps(payload).encode() if payload is not None else None,method=method)
 with urllib.request.urlopen(req,timeout=15) as response:
  body=response.read();return json.loads(body) if body else None,response.headers
auth,response_headers=call('/api/auth/login',account)
cookies=http.cookies.SimpleCookie();cookies.load(response_headers['Set-Cookie'])
headers['Cookie']='; '.join(key+'='+value.value for key,value in cookies.items())
headers['X-CSRF-Token']=auth['csrf_token']
competitions,_=call('/api/admin/competitions');assert len(competitions)==1
prefix='/api/admin/competitions/'+competitions[0]['id']+'/arrangement'
state,_=call(prefix);assert state['latest'] is None
state,_=call(prefix+'/initialize',{},'POST');assert state['latest']['sequence']==0
row=state['rows'][0];target=10 if row['competition_level']!=10 else 9
call('/api/admin/registrations/'+row['registration_id']+'/level',{'version':row['version'],'competition_level':target,'request_id':str(uuid.uuid4())},'PUT')
state,_=call(prefix)
receipt,_=call(prefix+'/versions',{'request_id':str(uuid.uuid4()),'state_token':state['state_token'],'base_version_id':state['latest']['id']},'POST')
assert receipt['sequence']==1
call('/api/auth/logout',{},'POST')
print(json.dumps({'baseline_sequence':0,'saved_sequence':1,'post_upgrade_level_write':True,'transport':'container loopback only; not public TLS evidence'}))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--new-release', type=Path, required=True)
    parser.add_argument('--synthetic-checkpoint', type=Path, required=True)
    parser.add_argument('--synthetic-credentials', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--project', default='fucheng-arrangement-drill-20260920-r11')
    args = parser.parse_args()
    if not args.project.startswith('fucheng-arrangement-drill-') or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.project):
        raise SystemExit('Expected a distinct synthetic drill project name')
    evidence = args.evidence.resolve()
    if not evidence.is_relative_to(ROOT / 'data') or evidence.exists():
        raise SystemExit('Use a new evidence directory below data/')
    checkpoint = args.synthetic_checkpoint.resolve()
    # Explicitly restrict intake to checkpoints from the already-authorized ngrok synthetic project.
    if not checkpoint.parent.name.startswith('deployment-ngrok-') or not checkpoint.is_relative_to(ROOT / 'data'):
        raise SystemExit('Only an explicitly selected ngrok synthetic checkpoint is accepted')
    metadata_path = checkpoint.with_suffix('.json')
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    if metadata['file'] != checkpoint.name or metadata['revision'] != '0006_competition_level' or hashlib.sha256(checkpoint.read_bytes()).hexdigest() != metadata['sha256']:
        raise SystemExit('Checkpoint metadata/hash/revision mismatch')
    with sqlite3.connect(f'file:{checkpoint.as_posix()}?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchall():
            raise SystemExit('Checkpoint failed integrity checks')
    old = json.loads((ROOT / 'data/deployment-release-20260920-r10/release.json').read_text(encoding='utf-8'))
    new = json.loads(args.new_release.read_text(encoding='utf-8'))
    new_manifest = json.loads((args.new_release.parent / 'source-manifest.json').read_text(encoding='utf-8'))
    if new['image_id'] == old['image_id'] or 'migrations/versions/0007_arrangement_versions.py' not in new_manifest['files']:
        raise SystemExit('Expected a distinct new release containing schema 0007')
    credentials = json.loads(args.synthetic_credentials.read_text(encoding='utf-8'))
    events = []

    def save(name, value):
        (evidence / name).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')

    def run(argv, *, expected=0, private_input=None, reject_text=None):
        result = subprocess.run(argv, cwd=ROOT, input=private_input, capture_output=True, timeout=120)
        stdout = result.stdout.decode('utf-8', 'replace')
        stderr = result.stderr.decode('utf-8', 'replace')
        # Input credentials are deliberately omitted from all evidence and errors.
        for value in (credentials.get('password'),):
            if value:
                stdout = stdout.replace(value, '[redacted]'); stderr = stderr.replace(value, '[redacted]')
        events.append({'argv':argv,'exit':result.returncode,'stdout':stdout,'stderr':stderr})
        if evidence.exists(): save('commands.json', events)
        valid = result.returncode == 0 if expected == 0 else result.returncode != 0
        if not valid or (reject_text and reject_text not in stdout + stderr):
            raise RuntimeError('Unexpected command result; inspect retained commands.json, do not retry blindly')
        return stdout.strip()

    for release in (old, new):
        actual = json.loads(run(['docker','image','inspect',release['image']]))[0]
        if actual['Id'] != release['image_id']: raise SystemExit('Release image identity mismatch')
    volume_names = [args.project+'_data', args.project+'_backups']
    existing = set(run(['docker','volume','ls','--format','{{.Name}}']).splitlines())
    if existing.intersection(volume_names) or run(['docker','ps','-a','-q','--filter',f'label=com.docker.compose.project={args.project}']):
        raise SystemExit('Drill resources already exist; inspect instead of reusing')
    evidence.mkdir()
    incoming = evidence / 'incoming'; incoming.mkdir()
    shutil.copyfile(checkpoint, incoming/checkpoint.name)
    shutil.copyfile(metadata_path, incoming/metadata_path.name)
    for name in volume_names:
        run(['docker','volume','create','--label',f'com.docker.compose.project={args.project}',name])
    options = ['--pull','never','--network','none','--user','10001:10001','--read-only',
        '--tmpfs','/tmp:size=16m,mode=1777','--cap-drop','ALL','--security-opt','no-new-privileges:true',
        '--label',f'com.docker.compose.project={args.project}',
        '-v',volume_names[0]+':/data','-v',volume_names[1]+':/backups',
        '-e','FUCHENG_PUBLIC_ORIGIN='+ORIGIN,'-e','FUCHENG_COOKIE_SECURE=true','-e','FUCHENG_PROXY_KIND=local']

    def ops(image, action, *extra, expected=0, reject_text=None, incoming_mount=False):
        mount = ['--mount',f'type=bind,source={incoming},target=/incoming,readonly'] if incoming_mount else []
        return run(['docker','run','--rm',*options,*mount,image,action,*extra],expected=expected,reject_text=reject_text)

    def fingerprint(image, filename=None):
        script = 'ARG='+repr(filename)+'\n'+FINGERPRINT
        return json.loads(run(['docker','run','--rm',*options,'--entrypoint','python',image,'-c',script]))

    def start(image, suffix):
        name=args.project+'-'+suffix
        run(['docker','run','-d',*options,'--health-interval','2s','--health-timeout','5s',
            '--health-start-period','2s','--name',name,image,'serve'])
        for _ in range(30):
            status=json.loads(run(['docker','inspect',name]))[0]['State']
            if status.get('Health',{}).get('Status')=='healthy': return name
            if not status['Running']: raise RuntimeError('Drill service exited; keep resources and inspect')
            time.sleep(1)
        raise RuntimeError('Drill health deadline reached')

    ops(old['image'],'import-backup',checkpoint.name,incoming_mount=True)
    ops(old['image'],'restore',checkpoint.name)
    before=fingerprint(old['image']);save('before.json',before)
    old_server=start(old['image'],'old')
    ops(new['image'],'migrate',expected=1,reject_text='volume lock')
    run(['docker','stop',old_server])
    ops(new['image'],'serve',expected=1,reject_text='Schema mismatch')
    ops(new['image'],'migrate')
    after=fingerprint(new['image']);save('after-migrate.json',after)
    assert after['revision']=='0007_arrangement_versions' and after['tables']['arrangement_versions']['count']==0
    assert all(after['tables'][name]==value for name,value in before['tables'].items() if name!='alembic_version')
    new_server=start(new['image'],'new')
    write_result=json.loads(run(['docker','exec','-i',new_server,'python','-c',API_WRITES],private_input=json.dumps(credentials).encode()))
    save('post-upgrade-api-writes.json',write_result)
    run(['docker','stop',new_server])
    retained=fingerprint(new['image']);save('retained-0007.json',retained)
    assert retained['tables']['arrangement_versions']['count']==2
    ops(old['image'],'serve',expected=1,reject_text='Schema mismatch')
    preupdate=run(['docker','run','--rm',*options,'--entrypoint','python',old['image'],'-c',
        "from pathlib import Path;print(sorted(Path('/backups').glob('pre-update-*.db'))[-1].name)"])
    ops(old['image'],'restore',preupdate)
    restored=fingerprint(old['image']);save('restored-0006.json',restored)
    assert restored['database']!=retained['database'] and restored['tables']==before['tables']
    assert fingerprint(new['image'],retained['database'])==retained
    rollback_server=start(old['image'],'rollback')
    run(['docker','stop',rollback_server])
    save('final.json',{'status':'PASS','project':args.project,'old_release':old,'new_release':new,
        'old_tables_preserved':True,'migration_did_not_create_baseline':True,'live_migration_rejected':True,
        'schema_mismatch_serve_rejected_both_directions':True,'post_upgrade_writes_preserved':True,
        'rollback_new_target':restored['database'],'retained_0007':retained['database'],
        'volumes_retained':volume_names,'containers_stopped_retained':[old_server,new_server,rollback_server],
        'host_ports':[],'tunnel':False,'cleanup':False})
    print('PASS: isolated migration/rollback; resources retained, drill servers stopped')


if __name__ == '__main__':
    main()
