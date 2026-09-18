# 府城球館會員管理系統

目前提供會員／比賽管理，以及第三階段「免登入選名報名」。使用者選比賽、搜尋並確認自己的名字、選當次葷素就能報名；取消、更正及遞補由管理員處理。沒有會員帳號、密碼或啟用連結。

這是公告欄手寫報名的線上形式，選名字不代表驗證本人，可能由他人代報；管理端會標記「免登入報名（身分未驗證）」。

## 快速啟動

以下啟動僅供新環境；既有資料庫先依部署文件備份、驗證副本及安排停機。

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
uv run --locked uvicorn fucheng.app:app --host 127.0.0.1 --port 8000 --no-access-log
```

開啟 <http://127.0.0.1:8000>；首頁 `/` 提供公告與比賽時程；`/members` 是免登入會員分級名單與列印；`/competitions` 是報名入口，個別比賽位於 `/register/:id`。管理員登入後可使用 `/admin` 會員管理、`/admin/competitions` 比賽管理與 `/admin/announcements` 公告管理，舊 `/admin/roster` 入口亦保留。正式環境必須保留 `FUCHENG_COOKIE_SECURE=true`，並由 HTTPS 同源入口存取。

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

## 免登入報名與驗證

使用者從首頁或比賽報名頁選比賽，搜尋姓名後選取自己（同名時核對註記），選葷食／素食，確認報名後看到此次正取或候補結果。系統以會員 ID 識別，不自動模糊配對。餐食預設葷食，不公開會員原本的餐食資料。

搜尋只顯示最多 20 筆姓名、辨識註記與選取 ID，不提供級數、餐食、原編號或報名名單。`/api/public/members` 提供免登入分級名單，僅含 id／姓名／辨識註記／級數，沒有餐食。找不到名字、取消或更正均洽管理員，沒有免登入取消功能。

有空位且沒有候補時為正取，已有候補就排到尾端，取消不自動遞補。重複點擊／重送不重複建立有效報名；管理員取消後重新線上報名會取得新的順位。截止與會員停用仍由後端在交易內檢查。

```powershell
$env:UV_CACHE_DIR='.uv-cache'
$env:UV_PYTHON_INSTALL_DIR='.uv-python'
uv sync --locked
uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-public
Push-Location frontend
npm ci
npm audit --audit-level=high
npm run typecheck
$env:FUCHENG_BUILD_DIR='../frontend/dist-public'
npm run build
npm run test:e2e
Pop-Location
```

E2E 使用 `data/public-e2e.db`、8031、`frontend/dist-public`，每次僅重建專用合成測試庫並套用 Alembic，先檢查 port 未占用；結束時停止自己的服務。建置不覆寫原服務 static。

## 合成預覽（自動測試用途）

```powershell
uv run --locked python scripts/create_public_preview.py
$env:FUCHENG_DATABASE_URL='sqlite:///data/public-preview.db'
$env:FUCHENG_COOKIE_SECURE='false'
$env:FUCHENG_STATIC_DIR='frontend/dist-public'
uv run --locked uvicorn fucheng.app:app --host 127.0.0.1 --port 8032 --no-access-log
```

建立腳本在檔案已存在時拒絕覆寫。開啟 [免登入報名預覽](http://127.0.0.1:8032/)，選合成比賽、搜尋「王」或「陳」即可操作；一般使用者不需要帳密。[管理入口](http://127.0.0.1:8032/admin) 的帳密只在本機 `data/public-preview-admin.json`，不要貼進聊天或日誌。

前景服務使用 Ctrl+C 停止。本次背景預覽 PID 存於 `data/public-preview.pid`，核對程序後可執行 `Stop-Process -Id (Get-Content data/public-preview.pid)`。原 8012 保留；舊帳號版合成預覽資料庫保留但不再使用。

先前未提交的帳號版程式封存於 Git 忽略的 `backups/account-flow-source-before-public-registration.zip`，不含資料庫或帳密。現行第三階段 migration 為 `0003_public_registration`，直接接第二階段；不要把舊帳號版預覽庫指向新版服務。

## 文件

- [架構與資料模型](docs/architecture.md)
- [部署、更新、備份、還原與 Cloudflare Tunnel](docs/deployment.md)
- [驗收證據與未驗證事項](docs/acceptance.md)
- [共同開發指引](AGENTS.md)

資料庫、秘密設定與備份不應放在 Git 或程式發布目錄內。範例 systemd 與環境設定位於 `deploy/`。

## 球館網站整合預覽（原會員資料副本）

首頁提供已發布公告、置頂公告與比賽時程，所有公共頁面共用導覽。草稿比賽不公開；open 比賽在到達截止時間後顯示報名已截止，也不能再報名。尚未開放的預告可透過公告發布，本版沒有新增自動開放報名排程欄位。

公告由管理員在 `/admin/announcements` 新增／修改，預設未發布；勾選「發布到首頁」後立即公開，取消勾選即下架，保留紀錄。支援置頂、版本衝突、重送防重與修改歷史。內容是純文字，保留換行，不執行 HTML。

已授權建立的本機預覽：[首頁](http://127.0.0.1:8032/)、[會員分級](http://127.0.0.1:8032/members)、[管理後台](http://127.0.0.1:8032/admin)。資料庫是 `data/club-preview.db`，由 `data/competition-case.db` 以 SQLite Backup API 建立副本後升級，保留 327 位原會員、2 位原管理員與既有比賽／稽核，另加本機預覽管理員及使用說明公告。沒有編造正式比賽或參賽名單。

管理帳密只在本機 `data/club-preview-admin.json`；舊合成預覽帳號不能用於這個副本。原始 `data/fucheng.db`、`data/competition-case.db` 未套遷移、未回寫。這個副本不是正式資料庫，操作僅保存在副本；自動測試仍限合成資料。

```powershell
# 一次性建立副本；檔案已存在時拒絕覆寫，不必每次啟動執行
uv run --locked python scripts/create_club_preview.py
# 啟動既有副本
$env:FUCHENG_DATABASE_URL='sqlite:///data/club-preview.db'
$env:FUCHENG_COOKIE_SECURE='false'
$env:FUCHENG_STATIC_DIR='frontend/dist-public'
uv run --locked uvicorn fucheng.app:app --host 127.0.0.1 --port 8032 --no-access-log
```

前景用 Ctrl+C 停止；本次背景 PID 位於 `data/club-preview.pid`，確認是本次 Python／8032 程序後才執行 `Stop-Process -Id (Get-Content data/club-preview.pid)`。不要使用舊 public-preview.pid 停止新版。逐欄保留與備份還原報告在 `data/club-preview-verification.json`，遷移後備份在 `backups/club-preview-migrated.db`。該預覽仍使用 revision `0004_club_website`；最新刪除功能預覽見下節。

## 已確認正取名單的整批匯入

管理員 API `POST /api/admin/competitions/{id}/import-confirmed-roster` 可將人工核對完成的名單匯入「尚無任何報名紀錄的草稿」，完成後直接關閉報名，不經過公開 open 狀態。這是本次會內賽補登入口；尚未提供通用 CSV 上傳／人工配對的網頁表單。

輸入含 version、request_id、reason、可選 notes，以及 rows（source_ref、member_id 或 create_member=true、已確認 name／level、可選 diet）。既有會員須指定 ID，姓名與級數必須仍一致；新會員須明確確認新增，同名已存在即拒絕，沒有模糊自動綁定。新會員預設餐食 unset，當次餐食另存；未提供當次值才沿用既有會員預設。人數不可超過名額，不接受未確認候補安排。

整批共用 registrations.py 的名額／候補檢查，在同一 BEGIN IMMEDIATE 交易新增會員、會員稽核、報名、報名稽核、來源對照與關閉場次，任一筆失敗全部回滾。來源位置只用於核對，不表示真實報名先後。重送以 actor／完整 payload 綁定之 key 返回既有結果，不重複新增。

本機預覽的「2026/9/20 府城球館會內賽」已依使用者逐次確認建立 80 人正取、無候補、不開放額外報名。保留 testing 場次；原會員資料庫不回寫。匯入前備份與結果位於 data/club-tournament-0920-import-result.json 所記錄路徑，名單與確認材料均留在 Git 忽略的 data/ 下。

現有 8032 程序保留。含最新批次 API 的額外服務為 `http://127.0.0.1:8033`，使用同一份 club-preview.db，PID 在 `data/roster-import.pid`。只有新版 API 使用 8033；原 8032 仍可查看更新後的會員與報名。若要停止額外服務，先核對程序，再執行 `Stop-Process -Id (Get-Content data/roster-import.pid)`。

## 刪除比賽與還原

在管理員「比賽管理」選取場次，按「刪除比賽」，會跳出顯示名稱、日期、正取／候補／取消人數的確認視窗。預設焦點在「保留比賽」；按 Escape 或保留即可離開，必須另按「確認刪除」才會執行。

刪除後不出現在首頁時程、報名入口及「目前比賽」，並停止該場所有管理與報名寫入。會員、報名、餐食、級數快照、排序及稽核完整保留；到「已刪除」選比賽、按「還原比賽」再次確認即可恢復。還原保留原狀態，若原本報名中且尚未截止，會重新開放報名，確認視窗有明確說明。本版沒有永久刪除。

### 目前可操作的新版預覽

[新版比賽管理](http://127.0.0.1:8034/admin/competitions) 使用 `data/club-delete-preview.db`（0005），由既有 `club-preview.db` 透過 Backup API 建立快照，再遷移與逐欄核對、備份還原。保留 342 位會員、9/20 的 80 人正取及原測試場次。不是把真實名單放進自動測試庫；E2E 仍只用合成資料。

新版與 8032／8033 的資料各自獨立，不會互相同步，後續試用請統一用 8034。8032／8033 程序與其資料庫未更動，成品也未覆寫。管理員沿用 `data/club-preview-admin.json` 的帳密。

```powershell
# 一次性建立；已存在即拒絕覆寫
uv run --locked python scripts/create_deletion_preview.py
# 啟動已建立的新版副本（不要重複啟動已占用的 8034）
$env:FUCHENG_DATABASE_URL='sqlite:///data/club-delete-preview.db'
$env:FUCHENG_COOKIE_SECURE='false'
$env:FUCHENG_STATIC_DIR='frontend/dist-delete'
uv run --locked uvicorn fucheng.app:app --host 127.0.0.1 --port 8034 --no-access-log
# 背景版停止：先核對 PID 確實為上述 8034 程序
Stop-Process -Id (Get-Content data/club-delete-preview.pid)
```

驗證報告在 `data/club-delete-preview-verification.json`，備份在 `backups/club-delete-preview-migrated.db`。正式資料庫尚未套用，也未部署。現有 8032／8033 舊程式不支援 deleted_at，不可直接與新版共用升級後的可寫資料庫；後續整合需統一版本及資料入口。

### 下一段對話的接手範圍

建議另開「比賽級數與人員管理介面」。接手目錄 `D:\projects\fucheng-players-system`，從整合後的 `main` 與 AGENTS.md 接手，新實作再建立對應功能分支，先核對 Git、服務、資料庫；目前新版預覽為 8034。以已確認的 9/20、80 人全正取場次理解使用需求，所有自動測試用合成資料。先釐清「會員長期硬實力級數」、「目前報名保存的硬實力快照」與「可調整的當次比賽級數」三者關係，再設計人員搜尋、級數分區／調整與名單管理，避免調整一場比賽就改動會員原級數。分隊、軟分級與自訂表頭的範圍需另外確認，不自動擴大。保留兩場現有比賽及會員資料，不自行提交、合併、推送、部署或停止既有服務。
