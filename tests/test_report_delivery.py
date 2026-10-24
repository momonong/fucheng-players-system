"""Exercise the real stdlib HTTP helper and the parent process hard deadline."""
import hashlib
import io
import json
import ssl
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import pytest
from fucheng import report_delivery, report_transport
from fucheng.models import now_utc


@pytest.mark.parametrize('mode', ['normal','redirect','invalid_json','oversize','reject'])
def test_real_https_helper_fixed_request_and_no_redirect(tmp_path,monkeypatch,mode):
    key,cert=tmp_path/'private-key',tmp_path/'certificate'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],check=True,capture_output=True)
    request_id=str(uuid4())
    raw='{"synthetic":true}'
    token='ab'*32
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            content=self.rfile.read(int(self.headers['Content-Length']))
            requests.append((self.path,content,self.headers.get('Origin'),self.headers.get('X-Fucheng-Report-Token')))
            if mode=='redirect':
                self.send_response(307);self.send_header('Location','/never-follow');self.end_headers();return
            if mode=='reject':
                self.send_response(422);self.end_headers();return
            body=json.dumps({'report_id':request_id,'device_id':'synthetic','digest':hashlib.sha256(content).hexdigest(),'received_at':now_utc().isoformat()}).encode()
            if mode=='invalid_json': body=b'{not-json'
            if mode=='oversize': body=b'x'*4097
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
    server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    # Module-local test injection; production exposes no endpoint/TLS/proxy option.
    monkeypatch.setattr(report_transport,'ENDPOINT',f'https://localhost:{server.server_port}/api/deployment-reports')
    import urllib.request
    original=urllib.request.build_opener
    trust=ssl.create_default_context(cafile=str(cert))
    monkeypatch.setattr(urllib.request,'build_opener',lambda *args:original(*args,urllib.request.HTTPSHandler(context=trust)))
    payload={'action':'send','report_id':request_id,'token':token,'report':raw}
    monkeypatch.setattr(sys,'stdin',type('Input',(),{'buffer':io.BytesIO(json.dumps(payload).encode())})())
    try:
        result=report_transport.main()
        assert result['outcome']==('received' if mode=='normal' else 'unknown' if mode in {'oversize','invalid_json'} else 'rejected')
        assert len(requests)==1
        assert requests[0]==('/api/deployment-reports/'+request_id,raw.encode(),'https://momonong.me',token)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)


@pytest.mark.parametrize('stage',['dns','slow_body'])
def test_real_child_deadline_kills_blocking_dns_or_slow_body(tmp_path,monkeypatch,stage):
    # A trusted test bootstrap blocks the actual helper at the named stdlib boundary.
    # The production parent still calls subprocess.run, waits its deadline, kills and reaps.
    import fucheng.report_transport
    script=tmp_path/'blocked-helper.py'
    module_path=report_transport.__file__
    script.write_text('import importlib.util,time,socket,urllib.request\n'
        +f'spec=importlib.util.spec_from_file_location("transport",{module_path!r});m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\n'
        +( 'socket.getaddrinfo=lambda *a,**k:time.sleep(30)\n' if stage=='dns' else
           'class Body:\n def __enter__(self): return self\n def __exit__(self,*a): pass\n status=200\n def read(self,*a): time.sleep(30)\nclass Opener:\n def open(self,*a,**k): return Body()\nurllib.request.build_opener=lambda *a:Opener()\n')
        +'m.main()\n')
    original=subprocess.run
    def launch(args,**kwargs):
        return original([sys.executable,'-I',str(script)],**kwargs)
    monkeypatch.setattr(subprocess,'run',launch)
    start=time.monotonic()
    with pytest.raises(TimeoutError):
        report_delivery._helper({'action':'send','report_id':str(uuid4()),'token':'ab'*32,'report':'{}'},0.3)
    assert time.monotonic()-start<2


def test_actual_fixed_helper_handles_invalid_input_without_secret_output():
    completed=subprocess.run([sys.executable,'-I',report_transport.__file__],input=b'{"token":"never-print-this"}',capture_output=True,timeout=3)
    assert completed.returncode==0
    assert json.loads(completed.stdout)=={'outcome':'unknown'}
    assert completed.stderr==b'' and b'never-print-this' not in completed.stdout


@pytest.mark.parametrize('failed',['none','region2','timeout'])
def test_fixed_tcp_probes_both_regions_partial_failure_and_timeout(monkeypatch,failed):
    import socket
    calls=[]
    class Connected:
        def __enter__(self): return self
        def __exit__(self,*args): pass
    def connection(address,timeout):
        calls.append((address,timeout))
        if failed=='timeout': raise TimeoutError()
        if failed=='region2' and address[0].startswith('region2'): raise OSError()
        return Connected()
    monkeypatch.setattr(socket,'create_connection',connection)
    # HTTPS transport is separately tested with trusted real local TLS above.
    class Head:
        status=200
        def __enter__(self): return self
        def __exit__(self,*args): pass
    class Opener:
        def open(self,*args,**kwargs): return Head()
    import urllib.request
    monkeypatch.setattr(urllib.request,'build_opener',lambda *args:Opener())
    monkeypatch.setattr(sys,'stdin',type('Input',(),{'buffer':io.BytesIO(b'{"action":"probe"}')})())
    result=report_transport.main()
    assert result['cloudflare_tcp_7844']==(failed=='none')
    assert result['cloudflare_tcp_regions']=={'region1':failed!='timeout','region2':failed=='none'}
    assert {address for address,_ in calls}=={('region1.v2.argotunnel.com',7844),('region2.v2.argotunnel.com',7844)}
    assert all(timeout<=3 for _,timeout in calls)
    assert 'cloudflare_udp_7844' not in result


def test_probe_budget_preserves_completed_results_when_one_dns_stalls(monkeypatch):
    import socket
    release=threading.Event()
    finished=threading.Event()
    class Connected:
        def __enter__(self): return self
        def __exit__(self,*args): pass
    def connection(address,timeout):
        if address[0].startswith('region2'):
            release.wait(timeout=2);finished.set();raise TimeoutError()
        return Connected()
    monkeypatch.setattr(socket,'create_connection',connection)
    class Head:
        status=200
        def __enter__(self): return self
        def __exit__(self,*args): pass
    class Opener:
        def open(self,*args,**kwargs): return Head()
    import urllib.request
    monkeypatch.setattr(urllib.request,'build_opener',lambda *args:Opener())
    monkeypatch.setattr(report_transport,'PROBE_BUDGET',0.1)
    monkeypatch.setattr(sys,'stdin',type('Input',(),{'buffer':io.BytesIO(b'{"action":"probe"}')})())
    try:
        result=report_transport.main()
        assert result['cloudflare_https'] is True and result['registry_https'] is True
        assert result['cloudflare_tcp_regions']=={'region1':True,'region2':False}
        assert result['cloudflare_tcp_7844'] is False
    finally:
        release.set();finished.wait(timeout=2)
