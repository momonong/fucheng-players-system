"""A narrowly scoped device credential may append bounded reports, never read data."""
import hashlib
import hmac
import json
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request, Response
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from .deployment_report import MAX_REPORT_BYTES, Report, HostReport, parse_report, render_markdown
from .models import DeviceDeploymentReport, now_utc

TOKEN_HEADER = "X-Fucheng-Report-Token"


def canonical_report(report: Report) -> str:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def receipt(row: DeviceDeploymentReport) -> dict:
    return {"report_id": row.report_id, "device_id": row.device_id, "digest": row.digest,
            "received_at": row.received_at.isoformat()}


def install_device_report_routes(app, get_db, current_auth, settings):
    Db = Annotated[Session, Depends(get_db)]
    Auth = Annotated[tuple, Depends(current_auth)]

    def require_device(request: Request):
        if not settings.report_upload_enabled:
            raise HTTPException(404, "報告回傳尚未啟用")
        values = request.headers.getlist(TOKEN_HEADER)
        supplied = values[0] if len(values) == 1 else ""
        # Hash to a fixed length before constant-time comparison, including invalid input.
        expected = hashlib.sha256(settings.report_upload_token.encode("ascii")).digest()
        actual = hashlib.sha256(supplied.encode("utf-8")).digest()
        if not hmac.compare_digest(expected, actual):
            raise HTTPException(401, "報告回傳憑證無效")

    @app.post("/api/deployment-reports/{report_id}", dependencies=[Depends(require_device)])
    async def upload(report_id: UUID, request: Request, db: Db):
        if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
            raise HTTPException(415, "請傳送 JSON 報告")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_REPORT_BYTES:
                raise HTTPException(413, "報告超過 256 KiB 上限；請保留原報告")
        report = parse_report(bytes(raw))
        canonical = canonical_report(report)
        encoded = canonical.encode("utf-8")
        if len(encoded) > MAX_REPORT_BYTES:
            raise HTTPException(413, "標準化報告超過 256 KiB 上限；請保留原報告")
        digest = hashlib.sha256(encoded).hexdigest()
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
        try:
            existing = db.get(DeviceDeploymentReport, str(report_id))
            if existing:
                if existing.device_id != settings.report_upload_device_id or existing.digest != digest:
                    raise HTTPException(409, "此 report_id 已綁定其他內容；請保留原請求並人工核對")
                result = receipt(existing)
                db.commit()
                return result
            count, used = db.execute(select(func.count(), func.coalesce(func.sum(DeviceDeploymentReport.size_bytes), 0))
                                    .select_from(DeviceDeploymentReport)).one()
            if count >= settings.report_upload_max_reports or used + len(encoded) > settings.report_upload_max_bytes:
                raise HTTPException(507, "報告儲存空間已滿；舊報告保留，請保留本機報告並聯絡管理者")
            timestamp = now_utc()
            recent = db.scalar(select(func.count()).select_from(DeviceDeploymentReport).where(
                DeviceDeploymentReport.device_id == settings.report_upload_device_id,
                DeviceDeploymentReport.received_at > timestamp - timedelta(hours=1)))
            if recent >= settings.report_upload_hourly_limit:
                raise HTTPException(429, "本裝置每小時報告數已達上限；請稍候以相同 ID 重試",
                                    headers={"Retry-After": "3600"})
            row = DeviceDeploymentReport(report_id=str(report_id), device_id=settings.report_upload_device_id,
                digest=digest, report_json=canonical, size_bytes=len(encoded), received_at=timestamp)
            db.add(row)
            db.commit()
            return receipt(row)
        except BaseException:
            db.rollback()
            raise

    @app.get("/api/admin/deployment-reports")
    def list_reports(db: Db, _auth: Auth, limit: int = Query(20, ge=1, le=100), before: UUID | None = None):
        statement = select(DeviceDeploymentReport)
        if before:
            cursor = db.get(DeviceDeploymentReport, str(before))
            if not cursor:
                raise HTTPException(404, "找不到報告分頁位置")
            statement = statement.where(or_(DeviceDeploymentReport.received_at < cursor.received_at,
                and_(DeviceDeploymentReport.received_at == cursor.received_at,
                     DeviceDeploymentReport.report_id < cursor.report_id)))
        rows = list(db.scalars(statement.order_by(DeviceDeploymentReport.received_at.desc(),
                               DeviceDeploymentReport.report_id.desc()).limit(limit + 1)))
        items = []
        for row in rows[:limit]:
            report = parse_report(row.report_json.encode("utf-8"))
            items.append(receipt(row) | {"checked_at": report.checked_at.isoformat(),
                "claimed_host_name": report.host.name if isinstance(report, HostReport) else report.runtime.name, "summary": report.summary.model_dump()})
        return {"items": items, "next_before": rows[limit - 1].report_id if len(rows) > limit else None}

    def download(report_id: UUID, db: Session, markdown: bool):
        row = db.get(DeviceDeploymentReport, str(report_id))
        if not row:
            raise HTTPException(404, "找不到報告")
        report = parse_report(row.report_json.encode("utf-8"))
        content = render_markdown(report) if markdown else report.model_dump_json(indent=2) + "\n"
        suffix, media = ("md", "text/markdown") if markdown else ("json", "application/json")
        return Response(content.encode("utf-8"), media_type=media, headers={
            "Content-Disposition": f'attachment; filename="host-report-{row.report_id}.{suffix}"',
            "X-Fucheng-Report-Digest": row.digest,
            "Content-Type": f"{media}; charset=utf-8"})

    @app.get("/api/admin/deployment-reports/{report_id}/json")
    def download_json(report_id: UUID, db: Db, _auth: Auth):
        return download(report_id, db, False)

    @app.get("/api/admin/deployment-reports/{report_id}/markdown")
    def download_markdown(report_id: UUID, db: Db, _auth: Auth):
        return download(report_id, db, True)
