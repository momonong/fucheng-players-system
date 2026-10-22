# 球館健檢回傳候選驗證（2026-10-22）

起點 `f5e17259b6c25a9e8ba2b3ca87a155a932ca82ca`，分支 `feat/club-report-upload`，版本保留 0.4.2；本輪為未提交 source snapshot。沒有 Git 提交／推送／發布、正式部署、實站資料讀寫或清理。

- Linux 後端完整回歸 **269 passed**，74.06 秒；兩項既有 Starlette／anyio deprecation warnings。命令為 `UV_CACHE_DIR=.uv-cache uv run --locked --no-sync pytest -q -p no:cacheprovider --basetemp .test-tmp-device-full tests --ignore=tests/test_host_report_sender.py`。唯讀 sandbox 的 TestClient 曾停滯，後依正式 escalation 執行；測試僅使用獨立合成 SQLite。
- 報告 API／原手動報告／schema／Origin 局部 **39 passed**。根路徑及 `/fucheng` 均驗：預設 disabled、缺／錯／重複 token 拒絕、未知欄位／重複 JSON key／NaN／超大 body 拒絕、slow body 408、admission/rate、同 UUID 同內容回相同 receipt、不同內容／device 409、server 新實例後重試、防止 device token 讀任何 admin API、admin JSON／Markdown下載、no-store／nosniff、手動報告不被取代、容量滿保留舊報告、分頁。
- `0011 → 0012` 測試先在舊 schema 建立合成 admin、session、會員、場次、報名及稽核／舊手動報告，保存原 **21 張表**全部欄位／列；migration 後逐表完全一致，只新增空的 device report table／索引／不可 UPDATE、DELETE triggers。`alembic check`、integrity、FK 通過。既有 runtime schema guard／maintenance／writer lock 測試也包含在完整回歸，沒有變更 serve 的遷移政策。
- 使用管理者核對官方 asset SHA-256 的 **portable PowerShell 7.6.6 / Linux** 真實執行傳輸測試，**6 passed**，8.44 秒。runtime 來源證據在 `data/club-report-20261021/powershell-runtime/provenance.json`。命令：設定 `FUCHENG_TEST_PWSH` 指向該 `runtime/pwsh` 後，執行 `UV_CACHE_DIR=.uv-cache uv run --locked --no-sync pytest -q -p no:cacheprovider --basetemp .test-tmp-sender-approved3 tests/test_host_report_sender.py`。
- 上述傳輸測試以真實 wrapper＋合成 host-probe fixture 建立 JSON／Markdown，再執行真實 sender 到隔離 loopback HTTPS 的實際 FastAPI receiver；測成功收據及不再送出、server 已 commit 但斷線後原 UUID／原 body 重試只存一份、307 不跟隨、HTTP 錯誤不印 raw body／token、錯收據 unknown、原 JSON 變更拒送、未受信任 TLS 不送 HTTP。只在子程序 `SSL_CERT_FILE` 指定隔離測試 CA，沒有改全域 trust、TLS bypass 或實站操作。
- 真實 PowerShell 測試找到並修正兩項跨 .NET 行為：buffered request stream 無 WriteTimeout setter，改共用 deadline＋Begin/End bounded waits；`File.Replace` 的 null 參數需明確 `NullString.Value`，以原子保存 status。原 operation 與 receipt 仍是 CreateNew，不覆寫。
- 固定 allowlist 的非秘密工具 ZIP 包含 9 檔，PS1 帶 UTF-8 BOM、逐檔 SHA manifest；測試拒絕覆寫 ZIP，並證明不納入私密 token／data。最終檔案與 ZIP SHA 由 `data/club-report-20261021/core-freeze.json` 記錄。
- `git diff --check` 通過；沒有前端變更、依賴更新或重建現用 dist。一般 `uv run --locked` 嘗試因 sandbox cache 唯讀／受限 DNS 無法重新取得 hatchling；既有 project `.venv` 的 no-sync 測試通過，未修改全域環境。

**尚未驗證**：Windows PowerShell 5.1／Windows Docker Desktop 真實主機探測、雙擊 CMD、球館網路、真正 UDP／Tunnel／外部入站、實體手機、斷電或重開機。Linux fixture 不代替上述證據。接收站是否正式啟用、正式 migration／原資料保留與入口驗證由目標負責者另行操作並記錄；本報告不宣稱已部署或人工接受。
