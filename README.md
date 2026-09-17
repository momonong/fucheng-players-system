# 府城球館會員管理系統

目前提供會員管理，以及第二階段的「比賽建立＋管理員維護報名名單」。管理員可建立比賽、依穩定順位處理正取／候補／取消、確認遞補、保存當次餐食與硬實力快照並列印管理名單。會員自行報名、軟分級、分隊與正式版本發布不在本階段範圍。

## 快速啟動

需求：uv 0.12 以上、Node.js 24（Node 22 LTS 亦可）。目前交付基準為一般 CPython 3.14.6；3.15 的驗證狀態見 [驗收證據](docs/acceptance.md)。

```powershell
$env:UV_CACHE_DIR='.uv-cache'
$env:UV_PYTHON_INSTALL_DIR='.uv-python'
uv sync --locked
Push-Location frontend
npm ci
npm run build
Pop-Location
$env:FUCHENG_DATABASE_URL='sqlite:///data/fucheng.db'
$env:FUCHENG_COOKIE_SECURE='false' # 僅限本機 HTTP
uv run --locked alembic upgrade head
uv run --locked fucheng create-admin admin
uv run --locked uvicorn fucheng.app:app --host 127.0.0.1 --port 8000
```

開啟 <http://127.0.0.1:8000>；會員管理位於 `/admin`，比賽管理位於 `/admin/competitions`。正式環境必須保留 `FUCHENG_COOKIE_SECURE=true`，並由 HTTPS 同源入口存取。

初始會員資料可由 UTF-8 CSV 匯入；欄位為 `name,level,diet,distinguishing_note`。指令只接受尚無會員的資料庫，避免重複匯入，並在同一交易建立停用的匯入身分與稽核紀錄：

```powershell
uv run --locked fucheng import-members <csv-path> --actor <import-label>
```

若經資料負責人確認既有「未設定」都代表葷食，可用具名且啟用中的管理員執行一次性回填；每位會員都會在同一交易留下修改紀錄：

```powershell
uv run --locked fucheng backfill-unset-diet --actor <admin-username>
```

本機備份使用 SQLite Backup API；還原必須先寫到新的測試目的地，不直接覆蓋執行中的資料庫：

```powershell
$env:FUCHENG_DATABASE_URL='sqlite:///data/fucheng.db'
uv run --locked fucheng backup backups/manual.db
uv run --locked fucheng restore backups/manual.db data/restore-check.db
```

確認還原檔完整且應用程式可讀後，才依[部署文件](docs/deployment.md)的停機與受控切換流程處理正式資料。`data/` 與 `backups/` 均為 Git 忽略路徑。

## 比賽與案例對照

比賽狀態只允許 `草稿 → 報名中 → 報名截止 → 已結束`，草稿／報名中／報名截止各可轉為已取消；已結束與已取消唯讀。即使資料庫狀態仍是報名中，到截止時間後的一般操作也會停止，管理員補登、取消、遞補或修改當次餐食必須填理由。

本機圖片案例先轉成 Git 忽略的 CSV，再以資料庫副本做逐字精確對照：

```powershell
$env:FUCHENG_DATABASE_URL='sqlite:///data/competition-case.db'
uv run --locked fucheng reconcile-competition-case `
  data/competition-case-0920-source.csv `
  data/competition-case-0920-reconciliation.json `
  --source-image 'D:\Downloads\S__52502533.jpg'
```

報告會分出單一啟用匹配、停用匹配、多個同名候選、無匹配與辨識不確定；不做模糊配對、不新增會員、不寫入資料庫。完成姓名人工確認，並取得年份、正式名額、截止時間後，才從比賽管理頁建立比賽並選取會員。圖片欄位與排列只保存在來源報告，不作硬實力級數或候補順序；若沒有真實報名先後，不可用圖片順序建立候補順位。

## 常用驗證

```powershell
uv sync --locked
uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp
Push-Location frontend
npm ci
npm audit --audit-level=high
npm run typecheck
npm run build
npm run test:e2e
Pop-Location
```

## 文件

- [架構與資料模型](docs/architecture.md)
- [部署、更新、備份、還原與 Cloudflare Tunnel](docs/deployment.md)
- [驗收證據與未驗證事項](docs/acceptance.md)
- [共同開發指引](AGENTS.md)

資料庫、秘密設定與備份不應放在 Git 或程式發布目錄內。範例 systemd 與環境設定位於 `deploy/`。
