"""Admin-only container diagnostics, immutable local reports and recoverable delivery."""
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import sys
import threading
import time
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Annotated
from uuid import UUID
from urllib.parse import urlsplit, unquote

from fastapi import Depends, HTTPException
from pydantic import AwareDatetime, Field, StrictBool, StrictInt, StrictStr
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from .deployment_report import (CONTAINER_CHECKS, HOST_ONLY_CHECKS, ContainerReport,
                                StrictModel, _state, parse_report)
from .device_reports import canonical_report
from .models import DeploymentDiagnosticRun, DeploymentReport, DeploymentReportAudit, now_utc
from .registrations import _begin_immediate
from .report_delivery import ENDPOINT, DeliveryRejected, deliver_report, probe_network

MAX_RUNS = 500
MAX_RUN_BYTES = 64 * 1024 * 1024


class RunRequest(StrictModel):
    version: Annotated[StrictInt, Field(ge=0)]
    request_id: Annotated[UUID, Field(strict=False)]
    probe_network: StrictBool


class Receipt(StrictModel):
    report_id: StrictStr
    device_id: StrictStr
    digest: Annotated[StrictStr, Field(pattern=r'^[0-9a-f]{64}$')]
    received_at: AwareDatetime


def read_regular(path: Path, limit: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('invalid bounded file')
        raw = stream.read(limit+1)
        if len(raw) > limit:
            raise ValueError('unbounded file')
        return raw


def sender_credentials(settings):
    if not settings.report_send_enabled or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', settings.report_send_device_id or ''):
        return None
    try:
        token = read_regular(settings.report_send_token_file, 256).decode('ascii').strip()
        if not re.fullmatch(r'(?:[0-9a-f]{2}){32,64}', token):
            return None
        return settings.report_send_device_id, token
    except (OSError, UnicodeError, ValueError, TypeError):
        return None


def collect_report(settings, db: Session, network: bool) -> ContainerReport:
    checks = {key: {'id':key, 'status':'NOT_TESTED',
        'reason':'app／Linux 容器無法驗證 Windows 主機、Docker daemon 或外部部署狀態。',
        'evidence':'沒有主機權限、Docker socket 或主機命令代理。',
        'next_action':'需要時在目標主機執行額外檢查；不得視為通過。'} for key in CONTAINER_CHECKS}
    def result(key, status, reason, evidence, action='依現場需求核對；本報告不代表完整部署驗收。'):
        checks[key] = {'id':key,'status':status,'reason':reason,'evidence':evidence,'next_action':action}
    result('runtime','PASS','已取得目前 app 的 Python／平台資訊。','僅目前執行環境；不含主機名稱或私密路徑。')
    try:
        html = read_regular(settings.static_dir/'index.html', 262144).decode('utf-8')
        references = re.findall(r"(?:src|href)=[\"']([^\"']+)[\"']", html)
        assets = []
        valid_assets = True
        static_root = settings.static_dir.resolve()
        for reference in references:
            parsed = urlsplit(reference)
            path = unquote(parsed.path)
            if parsed.scheme or parsed.netloc:
                continue
            prefixes = ('./assets/', 'assets/', '/assets/', settings.base_path+'/assets/')
            prefix = next((prefix for prefix in prefixes if path.startswith(prefix)), None)
            if prefix:
                tail = path[len(prefix):]
                relative = Path(tail)
                if not tail or relative.is_absolute() or tail.startswith(('/', '\\')) or '\\' in tail or '..' in relative.parts:
                    valid_assets = False
                    continue
                asset = (static_root / 'assets' / relative).resolve()
                if not asset.is_relative_to(static_root):
                    valid_assets = False
                    continue
                assets.append(asset)
        ready = valid_assets and bool(assets) and all(asset.is_file() for asset in assets)
        result('static_assets','PASS' if ready else 'FAIL','靜態入口及引用成品存在。' if ready else '靜態成品缺漏或無法辨識。','僅檢查檔案存在，不代表所有瀏覽器流程通過。')
    except (OSError, ValueError, UnicodeError):
        result('static_assets','FAIL','目前靜態入口無法讀取。','未揭露檔案位置或內容。','重新核對同批前後端 image。')
    try:
        with db.get_bind().connect() as connection:
            raw = connection.connection.driver_connection
            deadline = time.monotonic()+5
            raw.set_progress_handler(lambda: int(time.monotonic()>deadline), 1000)
            try:
                tables = set(connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").scalars())
                healthy = connection.exec_driver_sql('PRAGMA quick_check(1)').scalar() == 'ok'
                foreign_ok = connection.exec_driver_sql('PRAGMA foreign_key_check').first() is None
                metadata = DeploymentDiagnosticRun.metadata
                expected = set(metadata.tables)
                inspector = inspect(connection)
                ready = expected <= tables and all(
                    {column.name for column in table.columns}
                    <= {column['name'] for column in inspector.get_columns(table.name)}
                    for table in metadata.tables.values())
            finally:
                raw.set_progress_handler(None, 0)
        result('database_structure','PASS' if healthy and foreign_ok and ready else 'FAIL',
               '連線、資料表結構、SQLite quick_check 與外鍵檢查完成。',
               f'必要資料表及欄位齊備={ready}；quick_check={healthy}；外鍵完整={foreign_ok}；未查詢會員或報名內容。')
    except Exception:
        result('database_structure','FAIL','資料庫結構檢查未能完成。','未輸出 SQL、資料或例外內容。','核對明確遷移及備份；保留故障庫。')
    try:
        database = db.get_bind().url.database
        disk = shutil.disk_usage(Path(database).resolve().parent)
        gib = disk.free / 1024**3
        result('data_disk','PASS' if gib >= 5 else 'WARN' if gib >= 1 else 'FAIL',
               '資料庫所在檔案系統的可用容量。',f'目前可用 {gib:.1f} GiB；不是 Windows 主機或 Docker data-root 容量。')
    except (OSError, TypeError, ValueError):
        result('data_disk','NOT_TESTED','無法確認資料檔案系統容量。','沒有取得主機磁碟資訊。')
    try:
        from .backup_schedule import latest_weekly_due
        value=json.loads(read_regular(settings.backup_status_file, 16384))
        if not isinstance(value, dict):
            raise ValueError('backup status must be an object')
        schedule=value.get('last_schedule')
        from datetime import datetime
        current=isinstance(schedule,str) and datetime.fromisoformat(schedule)>=latest_weekly_due(now_utc())
        status='FAIL' if value.get('ok') is False else 'PASS' if current and value.get('ok') is True else 'WARN'
        result('backup_status',status,'已讀取既有備份服務狀態。','狀態目前有效。' if status=='PASS' else '狀態過期、失敗或無法確認。','仍須另做匹配版本的完整備份還原演練。')
    except (OSError, ValueError, TypeError, OverflowError):
        result('backup_status','NOT_TESTED','既有備份狀態未配置或無法確認。','本次未建立備份、未執行還原。','配置原有備份服務並另做還原演練。')
    result('ingress_configuration','WARN' if not settings.public_origin else 'PASS',
           '已核對 app 入口設定是否存在。','入口來源已設定；代理種類='+({'local':'local','cloudflare':'cloudflare','ngrok':'ngrok'}.get(settings.proxy_kind,'未知'))+'。' if settings.public_origin else '入口來源未配置；可能是本機測試環境。',
           '外部 HTTPS 可達性及 Turnstile 真人流程需另行實測。')
    net = probe_network() if network else {}
    for key in ('cloudflare_https','registry_https'):
        result(key,('PASS' if net.get(key) else 'WARN') if network else 'NOT_TESTED',
               '固定官方 HTTPS 端點的容器連線檢查。' if network else '未勾選官方網路檢查。',
               '端點回應符合預期。' if net.get(key) else '未取得預期回應；不代表主機防火牆或真實入口狀態。')
    regions = net.get('cloudflare_tcp_regions', {})
    region_status = lambda key: '已連線' if regions.get(key) is True else '未確認'
    result('cloudflare_tcp_7844', ('PASS' if net.get('cloudflare_tcp_7844') is True else 'WARN') if network else 'NOT_TESTED',
           '只檢查目前 app 容器的連線路徑至兩個官方 region 的 TCP 7844。' if network else '未勾選固定官方網路檢查；目前 app 容器的 TCP 7844 未測。',
           f'region1={region_status("region1")}；region2={region_status("region2")}；不代表 UDP、真實 Tunnel 或主機防火牆通過。',
           '現場另行核對 UDP／QUIC、cloudflared 真正連線及球館網路政策。')
    values=[checks[key] for key in sorted(checks)]
    return ContainerReport.model_validate_json(json.dumps({
        'schema_version':2,'report_type':'container_runtime','checked_at':now_utc().isoformat(),
        'runtime':{'name':'目前執行中的 app／Linux 容器','system':platform.system()+'/'+platform.machine(),'python':platform.python_version()},
        'scope':{'read_only_probes':True,'container_execution':True,'host_control':False,'business_data_read':False,'external_network_opt_in':network},
        'summary':{status:sum(c['status']==status for c in values) for status in ('PASS','WARN','FAIL','NOT_TESTED')},
        'checks':values,'recommendations':[{'candidate':'目前網站／容器','status':'NOT_TESTED','reason':'此報告保存 app 可觀察的結果；回傳成功不表示 Windows、入口或還原已通過。','next_action':'現場核對外部 HTTPS、真人驗證與匹配版本還原。'}],
        'sources':['https://docs.docker.com/engine/','https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/']},ensure_ascii=False))


def run_state(row: DeploymentDiagnosticRun) -> dict:
    return {'request_id':row.request_id,'send_state':row.send_state,'detail':row.detail,
            'device_id':row.device_id,'receipt':json.loads(row.receipt_json) if row.receipt_json else None}


def saved_state(row):
    report_row = DeploymentReport(id=1,version=row.report_version,report_json=row.report_json,
        sha256=row.digest,uploaded_by_admin_id=row.admin_id,uploaded_at=row.created_at)
    return _state(report_row,run_state(row))


@contextmanager
def operation_guard(db: Session, lock: threading.Lock, name: str):
    if not lock.acquire(blocking=False):
        raise HTTPException(409,'已有檢查或回傳進行中；請讀回原報告後再試')
    fd=None
    try:
        # The image is Linux. flock also guards another app instance on this same DB.
        import fcntl
        path=Path(db.get_bind().url.database).resolve().parent / ('.deployment-'+name+'.lock')
        fd=os.open(path,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise HTTPException(409,'已有檢查或回傳進行中；請讀回原報告後再試') from None
        yield
    finally:
        if fd is not None:
            os.close(fd)
        lock.release()


def install_diagnostic_routes(app, get_db, current_auth, require_csrf, settings):
    Db=Annotated[Session,Depends(get_db)]
    Auth=Annotated[tuple,Depends(current_auth)]
    Write=Annotated[tuple,Depends(require_csrf)]
    run_lock=threading.Lock()
    send_lock=threading.Lock()

    def find(db,key):
        row=db.get(DeploymentDiagnosticRun,str(key))
        if not row:
            raise HTTPException(404,'找不到此檢查報告；請保留原請求 ID')
        return row

    def capacity(db,extra=0):
        count,used=db.execute(select(func.count(),func.coalesce(func.sum(DeploymentDiagnosticRun.size_bytes),0))).one()
        if count>=MAX_RUNS or used+extra>MAX_RUN_BYTES:
            raise HTTPException(507,'本機檢查報告儲存已滿；舊報告保留，請聯絡管理者')

    def send_saved(db,auth,key):
        with operation_guard(db,send_lock,'send'):
            _begin_immediate(db,auth)
            try:
                row=find(db,key)
                if row.admin_id!=auth[0].id:
                    raise HTTPException(403,'僅原執行管理員可重送此報告')
                if row.send_state=='received':
                    db.commit()
                    return saved_state(row)
                credentials=sender_credentials(settings)
                if not credentials:
                    # An earlier attempted transmission stays unknown/rejected.
                    if row.device_id is None:
                        row.send_state='not_configured'
                    row.detail='報告已保存；回傳憑證尚未配置或無法使用。'
                    db.commit()
                    return saved_state(row)
                device,token=credentials
                if row.endpoint!=ENDPOINT or (row.device_id is not None and row.device_id!=device):
                    raise HTTPException(409,'此報告已綁定原接收站及裝置；請核對設定後以原 ID 重送')
                row.device_id=device
                row.send_state='unknown'
                row.detail='報告已保存；回傳結果待確認，請保留原 ID。'
                row.updated_at=now_utc()
                raw=row.report_json.encode('utf-8')
                expected_digest=row.digest
                checked_at=parse_report(raw).checked_at
                db.commit()  # Durable unknown and device binding BEFORE any HTTP.
            except BaseException:
                db.rollback()
                raise
            state,detail,receipt='unknown','報告已保存；回傳結果未確認，可用原報告重送。',None
            try:
                result=Receipt.model_validate_json(json.dumps(deliver_report(str(key),device,raw,token)))
                if (result.report_id!=str(key) or result.device_id!=device or result.digest!=expected_digest
                    or result.received_at<checked_at-timedelta(minutes=5) or result.received_at>now_utc()+timedelta(minutes=5)):
                    raise ValueError('invalid receipt')
                receipt=result.model_dump_json()
                state,detail='received','接收站已確認收到此份報告；不表示檢查全部通過。'
            except DeliveryRejected as error:
                state,detail='rejected',f'報告已保存；接收站拒收（HTTP {error.status}），請核對後重送原報告。'
            except (TimeoutError,ValueError,TypeError):
                pass
            finally:
                token=None
            _begin_immediate(db,auth)
            try:
                row=find(db,key)
                row.send_state=state
                row.detail=detail
                row.receipt_json=receipt
                row.updated_at=now_utc()
                db.commit()
                return saved_state(row)
            except BaseException:
                db.rollback()
                raise

    @app.get('/api/admin/deployment-report/runs/{request_id}')
    def read_run(request_id: UUID,db:Db,_auth:Auth):
        return saved_state(find(db,request_id))

    @app.post('/api/admin/deployment-report/runs/{request_id}/send')
    def send_run(request_id: UUID,db:Db,auth:Write):
        return send_saved(db,auth,request_id)

    @app.post('/api/admin/deployment-report/run')
    def run_report(payload:RunRequest,db:Db,auth:Write):
        key=str(payload.request_id)
        fingerprint=hashlib.sha256(payload.model_dump_json().encode('utf-8')).hexdigest()
        with operation_guard(db,run_lock,'run'):
            existing=db.get(DeploymentDiagnosticRun,key)
            if existing:
                if existing.admin_id!=auth[0].id or existing.fingerprint!=fingerprint:
                    raise HTTPException(409,'此請求 ID 已綁定其他管理員或內容；請保留原請求核對')
                return saved_state(existing)
            current=db.get(DeploymentReport,1)
            if payload.version!=(current.version if current else 0):
                raise HTTPException(409,'報告已更新；請重新載入並核對後再執行')
            capacity(db)
            db.rollback()
            report=collect_report(settings,db,payload.probe_network)
            canonical=canonical_report(report)
            encoded=canonical.encode('utf-8')
            digest=hashlib.sha256(encoded).hexdigest()
            admin_id=_begin_immediate(db,auth)
            try:
                current=db.get(DeploymentReport,1)
                if payload.version!=(current.version if current else 0):
                    raise HTTPException(409,'檢查期間報告已更新；請重新載入並核對')
                capacity(db,len(encoded))
                timestamp=now_utc()
                row=DeploymentDiagnosticRun(request_id=key,admin_id=admin_id,fingerprint=fingerprint,
                    report_version=payload.version+1,report_json=canonical,digest=digest,size_bytes=len(encoded),
                    endpoint=ENDPOINT,device_id=None,send_state='not_configured',detail='報告已保存；回傳憑證尚未配置。',
                    receipt_json=None,created_at=timestamp,updated_at=timestamp)
                db.add(row)
                if current:
                    current.version+=1
                    current.report_json=canonical
                    current.sha256=digest
                    current.uploaded_by_admin_id=admin_id
                    current.uploaded_at=timestamp
                else:
                    db.add(DeploymentReport(id=1,version=1,report_json=canonical,sha256=digest,uploaded_by_admin_id=admin_id,uploaded_at=timestamp))
                db.add(DeploymentReportAudit(version=payload.version+1,sha256=digest,admin_id=admin_id,created_at=timestamp))
                db.commit()
            except BaseException:
                db.rollback()
                raise
        return send_saved(db,auth,key)
