from __future__ import annotations

import argparse
import csv
import getpass
import json
import secrets
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from sqlalchemy import func, select

from .config import Settings
from .database import create_db_engine, make_session_factory
from .models import Admin, Member, MemberAudit, new_id, now_utc
from .schemas import MemberCreate
from .security import hash_password


def _sqlite_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise SystemExit("備份工具目前只支援 SQLite")
    return Path(database_url.removeprefix(prefix)).resolve()


def create_admin(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    factory = make_session_factory(create_db_engine(settings.database_url))
    password = args.password or getpass.getpass("密碼（至少 12 個字元）：")
    with factory.begin() as db:
        if db.scalar(select(Admin).where(Admin.username == args.username)):
            raise SystemExit("此管理員帳號已存在")
        db.add(Admin(username=args.username, password_hash=hash_password(password)))
    print(f"已建立管理員：{args.username}")


def import_members(args: argparse.Namespace) -> None:
    source = Path(args.csv_file).resolve()
    if not source.is_file():
        raise SystemExit(f"找不到匯入檔：{source}")
    rows: list[MemberCreate] = []
    try:
        with source.open(encoding="utf-8-sig", newline="") as input_file:
            reader = csv.DictReader(input_file)
            required = {"name", "level", "diet", "distinguishing_note"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise SystemExit(f"CSV 必須包含欄位：{', '.join(sorted(required))}")
            for line_number, row in enumerate(reader, start=2):
                try:
                    rows.append(MemberCreate(
                        name=row["name"],
                        level=int(row["level"]),
                        diet=row["diet"] or "omnivore",
                        distinguishing_note=row["distinguishing_note"] or None,
                        legacy_number=None,
                        is_active=True,
                    ))
                except (TypeError, ValueError) as error:
                    raise SystemExit(f"CSV 第 {line_number} 行無效：{error}") from error
    except UnicodeDecodeError as error:
        raise SystemExit("CSV 必須是 UTF-8 編碼") from error
    if not rows:
        raise SystemExit("CSV 沒有會員資料")

    settings = Settings.from_env()
    factory = make_session_factory(create_db_engine(settings.database_url))
    with factory.begin() as db:
        existing_count = db.scalar(select(func.count(Member.id))) or 0
        if existing_count:
            raise SystemExit(f"資料庫已有 {existing_count} 位會員；初始匯入已停止，避免重複資料")
        actor = db.scalar(select(Admin).where(Admin.username == args.actor))
        if actor is None:
            actor = Admin(
                username=args.actor,
                password_hash=hash_password(secrets.token_urlsafe(48)),
                is_active=False,
            )
            db.add(actor)
            db.flush()
        imported_at = now_utc()
        for payload in rows:
            values = payload.model_dump()
            member = Member(id=new_id(), **values, created_at=imported_at, updated_at=imported_at)
            db.add(member)
            changes = {key: {"before": None, "after": value} for key, value in values.items()}
            db.add(MemberAudit(
                member_id=member.id,
                admin_id=actor.id,
                action="import",
                changes_json=json.dumps(changes, ensure_ascii=False),
                created_at=imported_at,
            ))
    vegetarian_count = sum(row.diet == "vegetarian" for row in rows)
    print(f"初始匯入完成：{len(rows)} 位會員，其中素食 {vegetarian_count} 位；稽核身分：{args.actor}（停用）")


def backfill_unset_diet(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    factory = make_session_factory(create_db_engine(settings.database_url))
    with factory.begin() as db:
        actor = db.scalar(select(Admin).where(Admin.username == args.actor, Admin.is_active.is_(True)))
        if actor is None:
            raise SystemExit(f"找不到啟用中的管理員：{args.actor}")
        members = list(db.scalars(select(Member).where(Member.diet == "unset").order_by(Member.id)))
        changed_at = now_utc()
        for member in members:
            member.diet = "omnivore"
            member.version += 1
            member.updated_at = changed_at
            db.add(MemberAudit(
                member_id=member.id,
                admin_id=actor.id,
                action="update",
                changes_json=json.dumps({"diet": {"before": "unset", "after": "omnivore"}}, ensure_ascii=False),
                created_at=changed_at,
            ))
    print(f"葷素回填完成：{len(members)} 位會員由未設定改為葷食；管理員：{args.actor}")


def backup(args: argparse.Namespace) -> None:
    source = _sqlite_path(Settings.from_env().database_url)
    target = Path(args.output).resolve()
    if not source.is_file():
        raise SystemExit(f"找不到來源資料庫：{source}")
    if source == target:
        raise SystemExit("備份目的地不可與來源資料庫相同")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not args.force:
        raise SystemExit(f"備份檔已存在：{target}（需要覆寫時加 --force）")
    temporary = target.with_suffix(target.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    with closing(sqlite3.connect(source)) as source_db:
        with closing(sqlite3.connect(temporary)) as target_db:
            source_db.backup(target_db)
            result = target_db.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise SystemExit("備份完整性檢查失敗")
    temporary.replace(target)
    print(f"一致性備份完成：{target}")


def restore(args: argparse.Namespace) -> None:
    source = Path(args.input).resolve()
    target = Path(args.output).resolve()
    if not source.is_file():
        raise SystemExit(f"找不到備份檔：{source}")
    if source == target:
        raise SystemExit("還原目的地不可與來源備份相同")
    if target.exists() and not args.force:
        raise SystemExit(f"還原目標已存在：{target}（需要覆寫時加 --force）")
    with closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as source_db:
        result = source_db.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise SystemExit("來源備份完整性檢查失敗")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    shutil.copy2(source, temporary)
    temporary.replace(target)
    print(f"已還原至：{target}")


def reconcile_competition_case(args: argparse.Namespace) -> None:
    """只做逐字精確對照並產生本機報告；不建立會員、不建立比賽、不寫入來源資料庫。"""
    source = Path(args.csv_file).resolve()
    output = Path(args.output).resolve()
    if not source.is_file():
        raise SystemExit(f"找不到案例 CSV：{source}")
    if source == output:
        raise SystemExit("輸出報告不可覆寫來源 CSV")
    required = {
        "source_cell", "source_group", "source_column", "name", "diet_source",
        "recognition_status", "notes",
    }
    with source.open(encoding="utf-8-sig", newline="") as input_file:
        reader = csv.DictReader(input_file)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise SystemExit(f"案例 CSV 必須包含欄位：{', '.join(sorted(required))}")
        source_rows = list(reader)
    settings = Settings.from_env()
    database_path = _sqlite_path(settings.database_url)
    if not database_path.is_file():
        raise SystemExit(f"找不到案例資料庫副本：{database_path}")
    factory = make_session_factory(create_db_engine(settings.database_url))
    reconciled: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    with factory() as db:
        for row in source_rows:
            name = row["name"].strip()
            matches = list(db.scalars(select(Member).where(Member.name == name).order_by(Member.id)))
            recognition_status = row["recognition_status"].strip() or "clear"
            if recognition_status != "clear":
                match_status = "recognition_uncertain"
            elif len(matches) == 0:
                match_status = "no_match"
            elif len(matches) > 1:
                match_status = "multiple_exact_matches"
            elif not matches[0].is_active:
                match_status = "single_inactive_match"
            else:
                match_status = "single_active_match"
            counts[match_status] = counts.get(match_status, 0) + 1
            reconciled.append({
                **{key: row[key] for key in required},
                "name": name,
                "match_status": match_status,
                "candidates": [
                    {
                        "member_id": member.id,
                        "name": member.name,
                        "distinguishing_note": member.distinguishing_note,
                        "level": member.level,
                        "default_diet": member.diet,
                        "is_active": member.is_active,
                    }
                    for member in matches
                ],
                "proposed_case_diet": (
                    "vegetarian" if row["diet_source"].strip() == "image_vegetarian"
                    else (matches[0].diet if len(matches) == 1 else None)
                ),
                "diet_provenance": (
                    "source_image" if row["diet_source"].strip() == "image_vegetarian"
                    else ("member_default" if len(matches) == 1 else "unresolved")
                ),
            })
    report = {
        "source_csv": str(source),
        "source_image": str(Path(args.source_image).resolve()) if args.source_image else None,
        "database_copy": str(database_path),
        "matching_rule": "trimmed exact name only; no fuzzy matching and no automatic member creation",
        "source_row_count": len(reconciled),
        "summary": counts,
        "rows": reconciled,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)
    print(f"案例對照完成：{len(reconciled)} 筆；{counts}；報告：{output}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="fucheng")
    commands = parser.add_subparsers(required=True)
    admin = commands.add_parser("create-admin", help="建立管理員帳號")
    admin.add_argument("username")
    admin.add_argument("--password", help="僅供自動化；互動使用請省略")
    admin.set_defaults(func=create_admin)
    importer = commands.add_parser("import-members", help="從 UTF-8 CSV 進行一次性初始會員匯入")
    importer.add_argument("csv_file")
    importer.add_argument("--actor", default="initial-import", help="寫入稽核紀錄的停用維護身分")
    importer.set_defaults(func=import_members)
    diet_backfill = commands.add_parser("backfill-unset-diet", help="將未設定葷素的會員回填為葷食並寫入稽核")
    diet_backfill.add_argument("--actor", required=True, help="執行本次資料修正的啟用管理員帳號")
    diet_backfill.set_defaults(func=backfill_unset_diet)
    backup_parser = commands.add_parser("backup", help="以 SQLite Backup API 建立一致性備份")
    backup_parser.add_argument("output")
    backup_parser.add_argument("--force", action="store_true")
    backup_parser.set_defaults(func=backup)
    restore_parser = commands.add_parser("restore", help="驗證並還原至另一個資料庫檔")
    restore_parser.add_argument("input")
    restore_parser.add_argument("output")
    restore_parser.add_argument("--force", action="store_true")
    restore_parser.set_defaults(func=restore)
    case_parser = commands.add_parser("reconcile-competition-case", help="精確對照本機比賽圖片轉錄與會員副本")
    case_parser.add_argument("csv_file")
    case_parser.add_argument("output")
    case_parser.add_argument("--source-image")
    case_parser.set_defaults(func=reconcile_competition_case)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
