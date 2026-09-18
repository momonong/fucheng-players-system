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
5. 原子切換 `current` symlink，再啟動服務，檢查 `/api/health`、管理員登入及免登入報名入口。

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


## 第三階段免登入報名（正式庫尚未套用）

目標 revision 是 `0003_public_registration`，來源為 `0002_competition_registration`。舊帳號方案未提交的 revision 已撤下，只保留本機封存及舊合成預覽庫；不得直接把舊帳號版預覽資料庫交給新版服務。

1. 核對實際庫路徑、revision 及程式版本，使用 CLI Backup API 備份。
2. 還原到新路徑，在副本執行 `uv run --locked alembic upgrade head`，逐欄核對會員、管理員、比賽、正取／候補／取消、候補順序及稽核，執行 integrity_check／foreign_key_check。
3. 再次備份及還原副本，確認可回復。準備鎖定 release 與前端。
4. 取得正式部署授權後安排停機、再次備份，對正式庫套 migration，切換新版再啟動。驗證搜尋／報名、管理員取消／遞補與公開資料邊界。

Migration 用顯式 SQLite 交易保護 batch DDL，提交前檢查外鍵；出錯回滾 schema 及 revision。一般連線 FK 設定不變。不提供破壞性 downgrade，需從升級前備份還原至新檔、驗證、受控切換，同時保留故障庫；不能只回退程式。

只有管理員要登入，使用者不需帳密。正式同源入口必須 HTTPS，保留 cookie Secure=true；反向代理需正確還原 scheme／host 並只信任明確的代理來源。使用者選名字不證明本人，可能代報，錯誤由管理員更正；速率限制不能代替身分驗證。共享代理或球館網路可能共用 IP 額度，部署前確認預期流量。

systemd 範本使用 `--no-access-log`；代理與 APM 也不要保存 body、Cookie、Set-Cookie 或 CSRF。仍採 Linux＋systemd＋SQLite，沒有新增分散式服務。

合成預覽為 data/public-preview.db、8032、frontend/dist-public；只有管理員測試帳號存於 data/public-preview-admin.json。啟停命令見 README。原 8012 與原會員／9/20 案例庫保留。本次未執行正式遷移、Linux/systemd 或 HTTPS 實機部署。

## 球館網站整合版（0004_club_website）

最新 revision 為 `0004_club_website`，新增公告／公告稽核表。原始資料仍未套用新版；在授權的 `data/club-preview.db` 副本完成 0002 → 0003 → 0004、原資料逐欄保留、備份還原及 Alembic metadata check。啟停與帳密位置見 README「球館網站整合預覽」。8032 現在使用原會員副本，舊合成 `public-preview.db` 保留但不使用。

正式套用仍需另行授權：核對原庫實際 revision、備份並還原演練、停止正式寫入、套用 `alembic upgrade head`、建置／切換 release、檢查首頁、公開分級無敏感欄位、公告草稿不外露、管理員登入與比賽報名。恢復時使用更新前備份，不能只回退程式。`0004` 不提供刪除公告稽核的 downgrade。

整合預覽僅綁定 127.0.0.1；Linux/systemd、外網 HTTPS 與球館現場手機尚未驗收。原會員副本不是自動測試資料庫，不可交給 E2E 重建腳本。

## 80 人匯入後的本機預覽服務

本輪沒有新 migration，schema 保持 0004_club_website。8032 保持原程序運作，批次匯入 API 使用額外 8033 程序，兩者同為 data/club-preview.db。可在原 8032 管理頁查看 9/20 的 80 人；8033 的 PID、日誌分別在 data/roster-import.pid、data/roster-import.*.log，停止前核對程序身分。原會員與 9/20 來源庫仍不回寫，只有授權副本新增 15 會員與 80 報名。正式環境仍須另行授權部署。

## 比賽刪除版本（0005_competition_deletion）

最新 revision 為 `0005_competition_deletion`，只新增 competitions.deleted_at。既有原始庫及 8032／8033 使用的 club-preview.db 尚未套用；8034 使用獨立的 club-delete-preview.db 及 frontend/dist-delete，啟停方式與帳密位置見 README。副本完整保留 342 會員、2 場比賽與 81 報名，舊欄位逐欄一致，升級後備份還原與 Alembic metadata check 通過。

不能讓舊版服務與新版共用已升級的可寫庫：舊版不知道 deleted_at，可能顯示或接受已刪除場次的寫入。正式套用前須另行取得部署授權、備份與還原演練，安排停止所有舊版寫入、套用 alembic upgrade head、切換同一新版前後端，再驗證登入、公開時程、確認刪除與還原。不可直接啟動目前程式搭配尚未升級的舊庫。禁止以刪除欄位方式 downgrade，需還原升級前備份並受控切換。

8034 是本機試用副本，8032／8033 與它不會互相同步；後續驗收統一使用 8034，整合時先確認是否有各副本新增操作，不能任選一份覆蓋。本輪沒有停止現有服務、永久刪除比賽或修改 9/20 原始案例庫。
