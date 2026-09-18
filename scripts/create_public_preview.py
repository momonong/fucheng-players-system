"""One-time synthetic preview, separate from both live data and the earlier account preview."""
import json
import os
from datetime import timedelta
from pathlib import Path
from alembic import command
from alembic.config import Config
from fucheng.database import create_db_engine, make_session_factory
from fucheng.models import Admin, Competition, Member, now_utc
from fucheng.security import hash_password, new_token


def main():
    database=Path('data/public-preview.db').resolve()
    credentials=Path('data/public-preview-admin.json')
    if database.exists() or credentials.exists():
        raise SystemExit('合成預覽已存在，保留內容，不自動重建')
    os.environ['FUCHENG_DATABASE_URL']=f'sqlite:///{database.as_posix()}'
    command.upgrade(Config('alembic.ini'),'head')
    engine=create_db_engine(os.environ['FUCHENG_DATABASE_URL'])
    password=new_token()
    with make_session_factory(engine).begin() as db:
        db.add(Admin(username='preview-admin',password_hash=hash_password(password)))
        db.add_all([Member(name='合成王小明',distinguishing_note='東區',level=3,diet='omnivore'),
                    Member(name='合成王小明',distinguishing_note='西區',level=6,diet='vegetarian'),
                    Member(name='合成陳大文',level=5,diet='unset')])
        db.add(Competition(name='合成週末會內賽',competition_date=(now_utc()+timedelta(days=14)).date(),capacity=2,
            registration_deadline=now_utc()+timedelta(days=7),notes='測試時可搜尋「王」或「陳」。這裡只有合成資料。',status='open'))
    engine.dispose()
    credentials.write_text(json.dumps({'username':'preview-admin','password':password},indent=2),encoding='utf-8')
    print('免登入合成預覽已建立；只有管理員需要帳號，請於本機查看 data/public-preview-admin.json')


if __name__=='__main__':main()
