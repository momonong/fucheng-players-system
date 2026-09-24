"""Public club information and administrator-owned announcements."""
import hashlib
import io
import json
import os
import re
import warnings
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

import bleach
from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Announcement, AnnouncementAudit, AnnouncementMedia, Competition, new_id, now_utc
from .registrations import _begin_immediate, _changes
from .schemas import AuditEntry


class AnnouncementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=10000)
    body_format: Literal["plain", "html"] = "plain"
    is_published: bool = False
    is_pinned: bool = False
    request_id: str = Field(min_length=8, max_length=64)

    @field_validator("title", "body")
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("內容不可空白")
        return value

class AnnouncementUpdate(AnnouncementInput):
    version: int = Field(ge=1)


class PhotoRemoval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=64)


class PublicAnnouncement(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    body: str
    body_format: str
    photo_id: str | None
    is_pinned: bool
    published_at: datetime
    updated_at: datetime


class AdminAnnouncement(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    body: str
    body_format: str
    photo_id: str | None
    is_pinned: bool
    is_published: bool
    version: int
    published_at: datetime | None
    updated_at: datetime


class InlineImageUpload(BaseModel):
    announcement: AdminAnnouncement
    media_id: str


class InlineMediaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "figure":
            self.ids.append(dict(attrs).get("data-media-id", ""))


def inline_media_ids(body: str) -> list[str]:
    parser = InlineMediaParser()
    parser.feed(body)
    return parser.ids


def _safe_attribute(tag: str, name: str, value: str) -> bool:
    if tag == "a" and name == "href":
        try:
            url = urlsplit(value)
        except ValueError:
            return False
        return url.scheme in {"http", "https"} and bool(url.netloc)
    if tag == "figure" and name == "data-media-id":
        try:
            return str(UUID(value)) == value
        except ValueError:
            return False
    return name == "data-align" and tag in {"p", "div", "h1", "h2", "h3", "h4", "figure"} and value in {"left", "center", "right"}


def clean_announcement_html(body: str) -> tuple[str, list[str]]:
    cleaned = bleach.clean(body,
        tags={"h1", "h2", "h3", "h4", "p", "div", "ul", "ol", "li", "strong", "b", "em", "i", "u", "br", "a", "figure"},
        attributes=_safe_attribute, protocols={"http", "https"}, strip=True).strip()
    figures = re.findall(r"<figure\b[^>]*>.*?</figure>", cleaned, flags=re.DOTALL)
    if cleaned.count("<figure") != len(figures):
        raise HTTPException(422, "圖片區塊格式不正確")
    ids: list[str] = []
    def canonical(match):
        figure = match.group()
        media = re.search(r'data-media-id="([0-9a-f-]{36})"', figure)
        if not media:
            raise HTTPException(422, "圖片區塊缺少有效媒體")
        ids.append(media.group(1))
        align = re.search(r'data-align="(left|center|right)"', figure)
        return f'<figure data-media-id="{media.group(1)}" data-align="{align.group(1) if align else "center"}"></figure>'
    cleaned = re.sub(r"<figure\b[^>]*>.*?</figure>", canonical, cleaned, flags=re.DOTALL)
    if len(ids) > 20 or len(ids) != len(set(ids)):
        raise HTTPException(422, "公告圖片不可超過 20 張或重複使用")
    if (not bleach.clean(cleaned, tags=set(), strip=True).strip() and not ids) or len(cleaned) > 10000:
        raise HTTPException(422, "公告內容不可空白或過長")
    return cleaned, ids


class ScheduleItem(BaseModel):
    id: str
    name: str
    competition_date: date
    registration_deadline: datetime
    status: Literal["open", "closed", "ended", "cancelled"]
    notes: str | None


def save_announcement(db, auth, payload, announcement_id=None):
    admin_id = _begin_immediate(db, auth)
    fingerprint = hashlib.sha256(json.dumps(
        {"target": announcement_id, **payload.model_dump(exclude={"request_id"})},
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    previous = db.scalar(select(AnnouncementAudit).where(AnnouncementAudit.request_id == payload.request_id))
    if previous:
        if previous.admin_id != admin_id or previous.fingerprint != fingerprint:
            raise HTTPException(409, "請重新送出這次操作")
        return db.get(Announcement, previous.announcement_id)
    values = payload.model_dump(exclude={"request_id", "version"})
    media_ids = []
    if values["body_format"] == "html":
        values["body"], media_ids = clean_announcement_html(values["body"])
    before = {}
    row = db.get(Announcement, announcement_id) if announcement_id else None
    if announcement_id:
        if not row:
            raise HTTPException(404, "找不到公告")
        if row.version != payload.version:
            raise HTTPException(409, "公告已被其他管理員更新，請重新載入後再編輯；目前輸入已保留")
        if media_ids:
            owned = set(db.scalars(select(AnnouncementMedia.id).where(
                AnnouncementMedia.announcement_id == row.id, AnnouncementMedia.id.in_(media_ids))))
            if owned != set(media_ids):
                raise HTTPException(422, "公告圖片不屬於此公告")
        before = {key: getattr(row, key) for key in values}
        row.version += 1
        for key, value in values.items():
            setattr(row, key, value)
    else:
        if media_ids:
            raise HTTPException(422, "請先儲存公告草稿，再插入圖片")
        row = Announcement(**values)
        db.add(row)
    if values["is_published"] and not before.get("is_published"):
        row.published_at = now_utc()
    row.updated_at = now_utc()
    db.flush()
    db.add(AnnouncementAudit(announcement_id=row.id, admin_id=admin_id,
        action="update" if announcement_id else "create",
        changes_json=json.dumps(_changes(before, values), ensure_ascii=False),
        request_id=payload.request_id, fingerprint=fingerprint))
    db.commit()
    return row


MAX_PHOTO_BYTES = 5 * 1024 * 1024


def media_directory(app) -> Path:
    settings = app.state.settings
    data = settings.data_dir or Path(app.state.engine.url.database).parent
    return data / "announcement-media"


def normalized_photo(raw: bytes) -> tuple[bytes, str, str]:
    if not raw or len(raw) > MAX_PHOTO_BYTES:
        raise HTTPException(422, "照片大小須介於 1 位元組與 5 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(raw))
        with image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise HTTPException(422, "僅接受 PNG、JPEG 或 WebP 照片")
            if image.width * image.height > 20_000_000:
                raise HTTPException(422, "照片尺寸過大")
            image.load()
            transparent = image.mode in {"RGBA", "LA"} or "transparency" in image.info
            output = io.BytesIO()
            if transparent:
                image.convert("RGBA").save(output, format="PNG", optimize=True)
                mime, suffix = "image/png", ".png"
            else:
                image.convert("RGB").save(output, format="JPEG", quality=88, optimize=True)
                mime, suffix = "image/jpeg", ".jpg"
            result = output.getvalue()
            if len(result) > MAX_PHOTO_BYTES:
                raise HTTPException(422, "轉換後照片超過 5 MB")
            return result, mime, suffix
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, "檔案不是有效的照片") from None


def install_website_routes(app, get_db, current_auth, require_csrf):
    Db = Annotated[Session, Depends(get_db)]
    Auth = Annotated[tuple, Depends(current_auth)]
    Write = Annotated[tuple, Depends(require_csrf)]

    @app.get("/api/public/announcements", response_model=list[PublicAnnouncement])
    def announcements(db: Db):
        return list(db.scalars(select(Announcement).where(Announcement.is_published.is_(True))
            .order_by(Announcement.is_pinned.desc(), Announcement.published_at.desc(), Announcement.id)))

    @app.get("/api/public/schedule", response_model=list[ScheduleItem])
    def schedule(db: Db):
        # Drafts stay private. Clock-derived closure agrees with registration enforcement.
        rows = db.scalars(select(Competition).where(Competition.deleted_at.is_(None), Competition.status != "draft")
            .order_by(Competition.competition_date.desc(), Competition.id))
        now = now_utc()
        return [ScheduleItem(id=row.id, name=row.name, competition_date=row.competition_date,
            registration_deadline=row.registration_deadline, notes=row.notes,
            status="closed" if row.status == "open" and row.registration_deadline <= now else row.status)
            for row in rows]

    @app.get("/api/admin/announcements", response_model=list[AdminAnnouncement])
    def admin_announcements(db: Db, _auth: Auth):
        return list(db.scalars(select(Announcement).order_by(Announcement.updated_at.desc(), Announcement.id)))

    @app.post("/api/admin/announcements", response_model=AdminAnnouncement, status_code=201)
    def create(payload: AnnouncementInput, db: Db, auth: Write):
        return save_announcement(db, auth, payload)

    @app.put("/api/admin/announcements/{announcement_id}", response_model=AdminAnnouncement)
    def update(announcement_id: str, payload: AnnouncementUpdate, db: Db, auth: Write):
        return save_announcement(db, auth, payload, announcement_id)

    def change_photo(db, auth, announcement_id: str, version: int, request_id: str,
                     content: tuple[bytes, str, str] | None, request: Request):
        admin_id = _begin_immediate(db, auth)
        digest = hashlib.sha256(content[0]).hexdigest() if content else None
        fingerprint = hashlib.sha256(json.dumps({"target": announcement_id, "version": version,
            "photo_sha256": digest}, sort_keys=True).encode()).hexdigest()
        previous = db.scalar(select(AnnouncementAudit).where(AnnouncementAudit.request_id == request_id))
        if previous:
            if previous.admin_id != admin_id or previous.fingerprint != fingerprint:
                raise HTTPException(409, "請重新送出這次操作")
            return db.get(Announcement, previous.announcement_id)
        row = db.get(Announcement, announcement_id)
        if not row:
            raise HTTPException(404, "找不到公告")
        if row.version != version:
            raise HTTPException(409, "公告已被其他管理員更新，照片與輸入已保留")
        old_id = row.photo_id
        path = None
        try:
            if content:
                photo_bytes, mime, suffix = content
                media_id = new_id()
                filename = f"{media_id}{suffix}"
                directory = media_directory(request.app)
                directory.mkdir(parents=True, exist_ok=True)
                path = directory / filename
                with path.open("xb") as stream:
                    stream.write(photo_bytes)
                    stream.flush()
                    os.fsync(stream.fileno())
                db.add(AnnouncementMedia(id=media_id, announcement_id=row.id,
                    filename=filename, mime_type=mime, size=len(photo_bytes), sha256=digest))
                db.flush()
                row.photo_id = media_id
            else:
                row.photo_id = None
            row.version += 1
            row.updated_at = now_utc()
            db.flush()
            db.add(AnnouncementAudit(announcement_id=row.id, admin_id=admin_id,
                action="photo", changes_json=json.dumps({"photo_id": {"before": old_id, "after": row.photo_id}}),
                request_id=request_id, fingerprint=fingerprint))
            db.commit()
            return row
        except BaseException:
            db.rollback()
            if path:
                path.unlink(missing_ok=True)
            raise

    @app.post("/api/admin/announcements/{announcement_id}/photo", response_model=AdminAnnouncement)
    async def upload_photo(announcement_id: str, request: Request, db: Db, auth: Write,
                           version: int = Form(...), request_id: str = Form(...), photo: UploadFile = File(...)):
        if version < 1 or not 8 <= len(request_id) <= 64:
            raise HTTPException(422, "照片請求格式不正確")
        raw = await photo.read(MAX_PHOTO_BYTES + 1)
        content = normalized_photo(raw)
        return change_photo(db, auth, announcement_id, version, request_id, content, request)

    @app.post("/api/admin/announcements/{announcement_id}/images", response_model=InlineImageUpload)
    async def upload_inline_image(announcement_id: str, request: Request, db: Db, auth: Write,
                                  version: int = Form(...), request_id: str = Form(...), photo: UploadFile = File(...)):
        if version < 1 or not 8 <= len(request_id) <= 64:
            raise HTTPException(422, "圖片請求格式不正確")
        content = normalized_photo(await photo.read(MAX_PHOTO_BYTES + 1))
        admin_id = _begin_immediate(db, auth)
        digest = hashlib.sha256(content[0]).hexdigest()
        fingerprint = hashlib.sha256(json.dumps({"target": announcement_id, "version": version,
            "photo_sha256": digest, "mode": "inline"}, sort_keys=True).encode()).hexdigest()
        previous = db.scalar(select(AnnouncementAudit).where(AnnouncementAudit.request_id == request_id))
        if previous:
            if previous.admin_id != admin_id or previous.fingerprint != fingerprint or previous.action != "inline_photo":
                raise HTTPException(409, "請重新送出這次操作")
            return InlineImageUpload(announcement=AdminAnnouncement.model_validate(db.get(Announcement, announcement_id)),
                media_id=json.loads(previous.changes_json)["inline_media_id"]["after"])
        row = db.get(Announcement, announcement_id)
        if not row:
            raise HTTPException(404, "找不到公告")
        if row.version != version:
            raise HTTPException(409, "公告已被其他管理員更新，圖片與輸入已保留")
        media_id = new_id()
        filename = f"{media_id}{content[2]}"
        directory = media_directory(request.app)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename
        try:
            with path.open("xb") as stream:
                stream.write(content[0])
                stream.flush()
                os.fsync(stream.fileno())
            db.add(AnnouncementMedia(id=media_id, announcement_id=row.id,
                filename=filename, mime_type=content[1], size=len(content[0]), sha256=digest))
            row.version += 1
            row.updated_at = now_utc()
            db.flush()
            db.add(AnnouncementAudit(announcement_id=row.id, admin_id=admin_id,
                action="inline_photo", changes_json=json.dumps({"inline_media_id": {"after": media_id}}),
                request_id=request_id, fingerprint=fingerprint))
            db.commit()
            return InlineImageUpload(announcement=AdminAnnouncement.model_validate(row), media_id=media_id)
        except BaseException:
            db.rollback()
            path.unlink(missing_ok=True)
            raise

    @app.delete("/api/admin/announcements/{announcement_id}/photo", response_model=AdminAnnouncement)
    def remove_photo(announcement_id: str, payload: PhotoRemoval, request: Request, db: Db, auth: Write):
        return change_photo(db, auth, announcement_id, payload.version, payload.request_id, None, request)

    def serve_photo(db, request, media_id: str, *, public: bool):
        media = db.get(AnnouncementMedia, media_id)
        if not media:
            raise HTTPException(404, "找不到照片")
        row = db.get(Announcement, media.announcement_id)
        if not row or (public and (not row.is_published or
            (row.photo_id != media_id and media_id not in inline_media_ids(row.body)))):
            raise HTTPException(404, "找不到照片")
        directory = media_directory(request.app).resolve()
        if not re.fullmatch(r"[0-9a-f-]{36}\.(?:jpg|png)", media.filename):
            raise HTTPException(503, "照片檔名無法驗證")
        path = (directory / media.filename).resolve()
        if not path.is_relative_to(directory):
            raise HTTPException(503, "照片路徑無法驗證")
        if not path.is_file() or path.stat().st_size != media.size or hashlib.sha256(path.read_bytes()).hexdigest() != media.sha256:
            raise HTTPException(503, "照片檔案無法驗證")
        return FileResponse(path, media_type=media.mime_type,
            headers={"Content-Disposition": "inline"})

    @app.get("/api/public/announcement-media/{media_id}")
    def public_photo(media_id: str, request: Request, db: Db):
        return serve_photo(db, request, media_id, public=True)

    @app.get("/api/admin/announcement-media/{media_id}")
    def admin_photo(media_id: str, request: Request, db: Db, _auth: Auth):
        return serve_photo(db, request, media_id, public=False)

    @app.get("/api/admin/announcements/{announcement_id}/history", response_model=list[AuditEntry])
    def history(announcement_id: str, db: Db, _auth: Auth):
        if not db.get(Announcement, announcement_id):
            raise HTTPException(404, "找不到公告")
        rows = db.scalars(select(AnnouncementAudit).where(AnnouncementAudit.announcement_id == announcement_id)
            .order_by(AnnouncementAudit.created_at.desc(), AnnouncementAudit.id))
        return [AuditEntry(id=row.id, action=row.action, changes=json.loads(row.changes_json),
            admin_username=row.admin.username, created_at=row.created_at) for row in rows]
