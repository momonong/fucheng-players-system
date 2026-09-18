from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from fucheng.database import Base
from fucheng import models  # noqa: F401

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
if database_url := os.getenv("FUCHENG_DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"timeout": 10},
    )
    with connectable.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("PRAGMA busy_timeout=10000")
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        connection.exec_driver_sql("PRAGMA synchronous=FULL")
        # PRAGMA 會在 SQLAlchemy 連線上開啟隱含交易；先結束它，否則
        # SQLite DDL 會留下但 alembic_version INSERT 會在外層離開時回滾。
        connection.commit()
        # Batch rebuild of a referenced table needs FK enforcement temporarily disabled.
        # Explicit BEGIN keeps SQLite DDL + version updates atomic; validate before commit.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
            context.run_migrations()
            if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("遷移外鍵驗證失敗")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
