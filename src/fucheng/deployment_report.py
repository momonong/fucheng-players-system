"""Administrator-only ingestion and rendering of a bounded host preflight report."""
import hashlib
import json
import re
from html import escape
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, ValidationError, model_validator
from sqlalchemy.orm import Session

from .models import DeploymentReport, DeploymentReportAudit, now_utc
from .registrations import _begin_immediate

MAX_REPORT_BYTES = 256 * 1024
Status = Literal["PASS", "WARN", "FAIL", "NOT_TESTED"]
REQUIRED_CHECKS = frozenset((
    "windows_edition memory virtualization disk_space install_location backup_directory "
    "backup_write_and_restore docker_data_root wsl_version wsl_backend test_port direct_ports "
    "docker_service ac_sleep cold_boot_recovery hibernate_policy windows_firewall_baseline "
    "proxy_configuration firewall_egress_policy docker_engine compose_plugin app_image "
    "docker_subnet project_health lan_vpn_subnet domain_dns cloudflare_tcp_7844 "
    "cloudflare_udp_7844 cloudflare_https registry_https ngrok_tcp_443 preview_https "
    "domain_control public_ingress direct_tls"
).split())


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


ShortText = Annotated[StrictStr, Field(min_length=1, max_length=400)]
Label = Annotated[StrictStr, Field(min_length=1, max_length=120)]
NullableLabel = Annotated[StrictStr, Field(max_length=120)] | None


class ReportHost(StrictModel):
    name: Label
    windows: Label
    build: Label
    install_drive_free_gib: StrictFloat | StrictInt | None
    docker_platform: Label
    docker_server_version: Label

    @model_validator(mode="after")
    def sensible_space(self):
        value = self.install_drive_free_gib
        if value is not None and (not 0 <= value <= 1_000_000):
            raise ValueError("invalid disk capacity")
        return self


class ReportScope(StrictModel):
    read_only_probes: StrictBool
    created_report_directory: StrictBool
    external_network_opt_in: StrictBool
    container_execution: StrictBool
    live_volume_access: StrictBool
    compose_project: NullableLabel
    test_port: Annotated[StrictInt, Field(ge=1, le=65535)]
    proposed_docker_subnet: Label

    @model_validator(mode="after")
    def no_host_commands(self):
        if not self.read_only_probes or self.container_execution or self.live_volume_access:
            raise ValueError("report scope is incompatible with read-only host preflight")
        if self.compose_project and not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", self.compose_project):
            raise ValueError("invalid project")
        return self


class ReportSummary(StrictModel):
    PASS: Annotated[StrictInt, Field(ge=0, le=64)]
    WARN: Annotated[StrictInt, Field(ge=0, le=64)]
    FAIL: Annotated[StrictInt, Field(ge=0, le=64)]
    NOT_TESTED: Annotated[StrictInt, Field(ge=0, le=64)]


class ReportCheck(StrictModel):
    id: Annotated[StrictStr, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    status: Status
    reason: ShortText
    evidence: ShortText
    next_action: ShortText


class ReportRecommendation(StrictModel):
    candidate: Label
    status: Status
    reason: Annotated[StrictStr, Field(min_length=1, max_length=800)]
    next_action: ShortText


class HostReport(StrictModel):
    schema_version: Literal[1]
    checked_at: AwareDatetime
    host: ReportHost
    scope: ReportScope
    summary: ReportSummary
    checks: Annotated[list[ReportCheck], Field(min_length=len(REQUIRED_CHECKS), max_length=len(REQUIRED_CHECKS))]
    recommendations: Annotated[list[ReportRecommendation], Field(min_length=1, max_length=8)]
    sources: Annotated[list[Annotated[StrictStr, Field(min_length=8, max_length=300)]], Field(max_length=8)]

    @model_validator(mode="after")
    def consistent(self):
        ids = [item.id for item in self.checks]
        if len(set(ids)) != len(ids) or set(ids) != REQUIRED_CHECKS:
            raise ValueError("host preflight check set is incomplete or duplicated")
        counts = {status: sum(item.status == status for item in self.checks)
                  for status in ("PASS", "WARN", "FAIL", "NOT_TESTED")}
        if counts != self.summary.model_dump():
            raise ValueError("summary does not match check statuses")
        if any(not url.startswith("https://") or any(ord(c) < 32 for c in url) for url in self.sources):
            raise ValueError("invalid source URL")
        if not 2020 <= self.checked_at.year <= 2100:
            raise ValueError("invalid check time")
        return self


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def parse_report(raw: bytes) -> HostReport:
    if len(raw) > MAX_REPORT_BYTES:
        raise HTTPException(413, "報告超過 256 KiB 上限；既有報告未變更")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite number")))
        return HostReport.model_validate_json(json.dumps(value, ensure_ascii=False))
    except (UnicodeError, ValueError, TypeError, ValidationError):
        raise HTTPException(422, "部署檢查 JSON 格式或內容不正確；既有報告未變更") from None


def _markdown_text(value: object) -> str:
    """Treat every uploaded string as text, including in downloaded Markdown."""
    text = escape(str(value), quote=True).replace("\r", " ").replace("\n", " ")
    return re.sub(r"([\\`*_{}\[\]|~])", r"\\\1", text)


def render_markdown(report: HostReport) -> str:
    lines = ["# Windows Docker 主機部署檢查報告", "",
             f"- 檢查時間：{_markdown_text(report.checked_at.isoformat())}",
             f"- 報告宣稱的主機：{_markdown_text(report.host.name)}",
             f"- 系統：{_markdown_text(report.host.windows)}；build {_markdown_text(report.host.build)}",
             f"- 結果：PASS {report.summary.PASS}、WARN {report.summary.WARN}、FAIL {report.summary.FAIL}、NOT_TESTED {report.summary.NOT_TESTED}",
             "", "主機身份與檢查結果由上傳的 JSON 宣稱，伺服器沒有對主機做獨立驗證；請現場核對目標主機。", "",
             "| 檢查 | 狀態 | 理由 | 證據 | 下一步 |", "| --- | --- | --- | --- | --- |"]
    for item in report.checks:
        lines.append("| " + " | ".join(_markdown_text(value) for value in
            (item.id, item.status, item.reason, item.evidence, item.next_action)) + " |")
    lines.extend(["", "## 入口建議", ""])
    for item in report.recommendations:
        lines.append(f"- {_markdown_text(item.candidate)}（{item.status}）：{_markdown_text(item.reason)} 下一步：{_markdown_text(item.next_action)}")
    return "\n".join(lines) + "\n"


def _state(row: DeploymentReport | None):
    if row is None:
        return {"version": 0, "uploaded_at": None, "report": None, "markdown": None}
    report = HostReport.model_validate_json(row.report_json)
    return {"version": row.version, "uploaded_at": row.uploaded_at.isoformat(),
            "report": report.model_dump(mode="json"), "markdown": render_markdown(report)}


def install_deployment_report_routes(app, get_db, current_auth, require_csrf):
    Db = Annotated[Session, Depends(get_db)]
    Auth = Annotated[tuple, Depends(current_auth)]
    Write = Annotated[tuple, Depends(require_csrf)]

    @app.get("/api/admin/deployment-report")
    def read_report(db: Db, _auth: Auth):
        return _state(db.get(DeploymentReport, 1))

    @app.post("/api/admin/deployment-report")
    async def upload_report(request: Request, db: Db, auth: Write,
                            version: int = Query(..., ge=0)):
        if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
            raise HTTPException(415, "請上傳 JSON 報告")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_REPORT_BYTES:
                raise HTTPException(413, "報告超過 256 KiB 上限；既有報告未變更")
        report = parse_report(bytes(raw))
        canonical = report.model_dump_json()
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        admin_id = _begin_immediate(db, auth)
        try:
            row = db.get(DeploymentReport, 1)
            current = row.version if row else 0
            if version != current:
                raise HTTPException(409, "報告已被其他管理員更新；請重新載入後再上傳")
            timestamp = now_utc()
            if row:
                row.version += 1
                row.report_json = canonical
                row.sha256 = digest
                row.uploaded_by_admin_id = admin_id
                row.uploaded_at = timestamp
            else:
                row = DeploymentReport(id=1, version=1, report_json=canonical, sha256=digest,
                                       uploaded_by_admin_id=admin_id, uploaded_at=timestamp)
                db.add(row)
            db.add(DeploymentReportAudit(version=current + 1, sha256=digest,
                                         admin_id=admin_id, created_at=timestamp))
            db.commit()
            return _state(row)
        except BaseException:
            db.rollback()
            raise

    def download(db: Session, format: str) -> Response:
        row = db.get(DeploymentReport, 1)
        if row is None:
            raise HTTPException(404, "尚未上傳部署檢查報告")
        report = HostReport.model_validate_json(row.report_json)
        if format == "json":
            content = report.model_dump_json(indent=2) + "\n"
            media = "application/json"
        else:
            content = render_markdown(report)
            media = "text/markdown"
        return Response(content.encode("utf-8"), media_type=media,
                        headers={"Content-Disposition": f'attachment; filename="deployment-report.{format}"',
                                 "Content-Type": f"{media}; charset=utf-8"})

    @app.get("/api/admin/deployment-report/json")
    def download_json(db: Db, _auth: Auth):
        return download(db, "json")

    @app.get("/api/admin/deployment-report/markdown")
    def download_markdown(db: Db, _auth: Auth):
        return download(db, "md")
