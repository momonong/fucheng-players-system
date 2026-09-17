# 部署、更新、備份與還原

以下是 Linux + systemd 的建議配置。系統沒有 Docker；Node.js 只在開發機或建置階段使用。

## 目錄與帳號

```text
/opt/fucheng/releases/<版本>/  唯讀程式與前端成品
/opt/fucheng/current           指向目前版本的 symlink
/opt/fucheng/venv              已鎖定的 Python 虛擬環境
/var/lib/fucheng/fucheng.db    執行資料
/etc/fucheng/fucheng.env       秘密及環境設定（0600）
/var/backups/fucheng/          備份（不在發布目錄）
```

建立專用、不可登入的 `fucheng` 系統帳號，讓 `/var/lib/fucheng` 屬於該帳號。不要使用 root 執行網站服務。先在建置機執行 `npm ci && npm run build`，把含 `src/fucheng/static` 的發布內容送到新 release 目錄；主機不需要常駐 Node.js。

安裝時以 release 目錄中的 lockfile 建立固定虛擬環境（不在 systemd 啟動階段安裝）：

```bash
cd /opt/fucheng/releases/2026-09-16
UV_PROJECT_ENVIRONMENT=/opt/fucheng/venv uv sync --locked --no-dev
install -m 600 deploy/fucheng.env.example /etc/fucheng/fucheng.env
sudo -u fucheng /opt/fucheng/venv/bin/alembic upgrade head
sudo -u fucheng /opt/fucheng/venv/bin/fucheng create-admin <管理員帳號>
```

依現場路徑修改環境檔與 service，複製 `deploy/fucheng.service` 後執行 `systemd-analyze verify`、`daemon-reload`、`enable --now`。`FUCHENG_COOKIE_SECURE=true` 不得在公開 HTTPS 環境關閉。

## 更新

1. 將新版本放入新的 `/opt/fucheng/releases/<版本>`，先建置前端並執行測試。
2. 對仍在運作的資料庫執行一致性備份：`/opt/fucheng/venv/bin/fucheng backup /var/backups/fucheng/pre-update.db --force`。
3. 從新 release 執行 `UV_PROJECT_ENVIRONMENT=/opt/fucheng/venv uv sync --locked --no-dev`。
4. 停止服務；載入 `/etc/fucheng/fucheng.env` 後，從新 release 執行 Alembic `upgrade head`。
5. 原子切換 `current` symlink，再啟動服務，檢查 `/api/health`、登入與公開名單。

資料庫遷移後不可假設程式 symlink 回退就等於安全回退；需要還原時使用更新前備份，並保留故障資料庫供調查。

第二階段 migration `0002_competition_registration` 只新增比賽、報名與稽核表，不重建會員表。正式資料套用前仍必須先用 Backup API 備份，再把備份還原到新路徑，在副本執行 `alembic upgrade head`、核對會員／管理員／稽核筆數與 `integrity_check`，最後才安排停機遷移正式庫。本次本機案例副本驗證不等於正式資料庫已遷移。

## 一致性備份與還原

不要把直接複製正在寫入的 SQLite 主檔當成唯一備份。工具使用 SQLite Backup API，完成後執行 `integrity_check`，再原子放置檔案。

```bash
FUCHENG_DATABASE_URL=sqlite:////var/lib/fucheng/fucheng.db \
  /opt/fucheng/venv/bin/fucheng backup /var/backups/fucheng/manual.db

/opt/fucheng/venv/bin/fucheng restore /var/backups/fucheng/manual.db /var/lib/fucheng/restored.db
```

還原先寫入新的乾淨檔案。驗證 `PRAGMA integrity_check`、資料筆數與應用程式讀取後，停止服務，再以受控的檔案切換取代正式資料庫；保留原檔以便回復。`deploy/fucheng-backup.timer` 是每日排程範例，會產生時間戳備份；另需依磁碟容量設定保留政策與異地備份。

## Cloudflare Tunnel（僅記錄，未建立）

1. 在 Cloudflare 管理介面建立 tunnel、網域及 DNS；這些是外部變更，本專案不代建。
2. 將憑證放在 cloudflared 專用秘密目錄，依 `deploy/cloudflared-config.yml.example` 填入 tunnel ID、credentials 與 hostname。
3. Tunnel 只轉送至 `http://127.0.0.1:8000`；瀏覽器看到的公開入口必須是 HTTPS，才能使用 Secure session cookie。
4. 啟用前驗證登入、登出、CSRF、來源 IP／日誌策略及 Cloudflare 存取控制需求。
