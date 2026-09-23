# 府城球館會員管理系統

部署準備採 **Windows Docker Desktop／WSL2：單一app image＋SQLite named volume**，備份／維護共用image，正式HTTPS主方案為Cloudflare named tunnel。離線包、source manifest、PowerShell工具與現場清單見[部署手冊](docs/deployment.md)。本機容器證據不代表球館實機、公開入口、正式資料或人工驗收已完成；以下開發／預覽命令保留原用途。

目前提供會員／比賽管理、免登入選名報名，以及管理員的當次比賽級數安排。使用者選比賽、搜尋並確認自己的名字、選當次葷素就能報名；取消、更正及遞補由管理員處理。沒有會員帳號、密碼或啟用連結。

這是公告欄手寫報名的線上形式，選名字不代表驗證本人，可能由他人代報；管理端會標記「免登入報名（身分未驗證）」。

## 快速啟動

### v0.2.0 來源、image 與 B 預覽發布（2026-09-23）

已推送 `main` commit `c9c4e0be1907cf6e6f2f2a54ffafba3ab4868e45` 與 Git tag `v0.2.0`。Linux/amd64 image 發布至 [Docker Hub](https://hub.docker.com/r/momonong/fucheng-players-system)，`0.2.0` 與 `latest` 指向相同 OCI index digest `sha256:bf522f2646caf936fd8c4b852789ed34367f85979a867511b3f3f5a7d2f70176`。B 原入口已更新為同一來源版本，備份、image 與服務身份見[部署紀錄](docs/deployment.md)及[驗收紀錄](docs/acceptance.md)。

此版整合精確格位選單／表頭操作、復原與重做、Excel／列印，以及大型保存後穩定列位與目前／歷史側欄精修；無新增 migration，schema 維持 0008。E2E A、B3、C2 批次通過；C3／C5 留有失敗紀錄，與先前交接摘要中的 C5 通過說法不一致，完整 C 系列不列為全通過，詳[驗收紀錄](docs/acceptance.md#v020-發布驗證2026-09-23)。公開預覽只做 health、HTML 與靜態資產唯讀檢查，未登入或執行管理操作；人工驗收、實體手機及其他 OS 驗收仍待進行。**已知限制：大型保存或重啟後偶見尾端空白列；本輪未重現、未修復，使用者同意延後；沒有加入裁切或 fallback。**

前次灰階／雙區拖曳／歷次級數版：eb24 當時更新至 `grid-interaction-20260921-120352`，app／launcher **45560／41228**，ngrok **57728**。56 檔來源摘要 `c00f5937c00291c58819e2630387d965a0bf3951f0ae9cb1a73c631ae30f83c2`；歷史證據見 `data/grid-public-runtime/grid-interaction-update.json`。

前次 axis 三項功能版發布紀錄：安全刪除布局排／文字欄、明顯的素食開啟狀態、歷史由舊到新且首次開啟定位最新。現用 listener **45612**／launcher **47980**，ngrok **57728** 不變；身份見 `data/grid-public-runtime/grid-axis-update.json`。54 檔來源及 dist-grid-axis 已凍結發布，原 DB、session、未大存安排保留；公開驗證僅查看限制／預覽取消，未實際刪除。下方版本與 PID 為歷次紀錄。

前次 grid-edit 五項表格功能版發布紀錄：邊界插入、文字／級數顯示標題編輯、矩形／手機二點選取、素食柔和標記、完整安排列印。新來源 53 檔身份見 `data/grid-edit-delivery-identity.json`，實際公開交付見 `data/grid-public-runtime/grid-edit-update.json`。B app 已受控更新為 listener **32752**／launcher **36224**，原 ngrok **57728**、網址、DB、admin 與 session 保留；下方舊 PID／身份為前次交付紀錄。重新整理可載入新前端；如原頁有未確定請求，先依原 request_id 確認結果，不重建操作。此版本仍未 commit／merge／push，等待人工驗收。

2026-09-21 拖曳修正已更新至同一 eb24 入口，重新整理即可載入。此次只切換前端 static，保留既有登入、未完整保存的安排與 app／ngrok 程序；當時前端身份見 `data/grid-public-runtime/frontend-drag-update.json`，原 `identity.json` 保留為凍結來源及初次部署紀錄。

歷史入口（eb24，已停用；現行請使用上方 b021），當時選「合成 80 人級數安排（已截止）」。沿用使用者指定的現用 admin 帳密，僅保存在 B 的 `data/grid-public-runtime/admin.json`，不在文件或 Git 公開。上方甲／乙／丙合併表頭、左側隊名與 80 人安排均可查看；「公開 B 格位驗收」版本保留指定格位拖曳結果，仍待使用者人工驗收。

B 工作目錄為 `D:\projects\fucheng-players-system-worktrees\arrangement-grid`，分支 `feat/competition-arrangement-grid`，起點 `89cae09754eaefa4dba6c3dce308482526f33ff2` 加未提交 B。公開服務使用獨立 `.venv`、凍結的 `data/grid-public-runtime/source/src`／`static`、新合成副本 `data/grid-public-preview.db`（0008），綁定 `127.0.0.1:8044`。50 個來源檔及 3 個成品檔身份見 runtime 的 `identity.json`；未提交成果不能僅用 HEAD 辨識。

本次 app listener **44424**／launcher **63012**／ngrok **57728**。在 B 工作目錄執行下列腳本，先核對 PID 建立時間、命令列、B 專用 config 及 8044 歸屬；目前只執行過 CheckOnly，服務仍保留供驗收。

```powershell
powershell -NoProfile -File data/grid-public-runtime/stop-preview.ps1 -CheckOnly
powershell -NoProfile -File data/grid-public-runtime/stop-preview.ps1
```

此公開合成入口未 commit／merge／push，沒有 B Docker image、正式資料遷移或實機觸控驗收。A 的 f9d0／8041、B 原人工預覽 8042、既有帳密及 session 保留；兩個 ngrok agent 已並行運作。詳細證據、啟停與限制見[部署手冊](docs/deployment.md#b-0008-公開合成預覽2026-09-21)及[驗收紀錄](docs/acceptance.md#b-公開入口增量驗收2026-09-21)。

### A 公開合成預覽（保留）

目前另有[新版安排公開合成預覽](https://f9d0-140-116-158-107.ngrok-free.app/admin/competitions)（2026-09-20）。首次訪問可能出現ngrok的Visit Site提示。管理員帳密只存本機 `data/arrangement-native-preview-admin.json`；選「合成 80 人級數安排（已截止）」。全新合成資料為83會員、3場、85報名，主場80正取；已保留兩個保存版供查看，人工驗收仍待使用者確認。

此為官方Windows ngrok＋原生FastAPI臨時入口，僅綁 `127.0.0.1:8041`；資料為 `data/arrangement-native-preview.db`（0007），成品為 `data/arrangement-native-runtime/static`，逐檔hash複製自已驗證的 `frontend/dist-arrangement`。沒有新Docker image。48個來源與3個成品檔身份見同runtime目錄 `identity.json`，未提交版本不能只用HEAD辨識。

app listener PID **64348**、Python launcher **60996**、ngrok **50144**；身份時間／私有設定／日誌在 `data/arrangement-native-runtime/`。停止腳本先核對PID建立時間、命令列及8041歸屬，只停止本入口並保留資料：

```powershell
powershell -NoProfile -File data/arrangement-native-runtime/stop-preview.ps1 -CheckOnly
powershell -NoProfile -File data/arrangement-native-runtime/stop-preview.ps1
```

舊Docker／ngrok與r11升級仍hold，本次零Docker／GPU操作；8037、8039及舊資料／成品保留。此入口沒有開機服務、排程或自動重啟保證。完整邊界與證據見[部署手冊](docs/deployment.md)及[驗收紀錄](docs/acceptance.md)。

本合成預覽另依使用者指定新增 `admin` 登入，密碼僅在上述ignored帳密檔保存；既有管理員及歷史actor保留。最終密碼依既有hash_password的正常12字元規則設定；先前短密碼已失效，該admin舊sessions已撤銷，程式預設不變。

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

## 當次比賽級數與完整安排

「比賽管理」預設進入排級數：1～10 級橫向欄、緊湊姓名格，只呈現正取安排。比賽設定、刪除、報名名單與逐次操作稽核在「報名與設定」入口。右上搜尋圖示展開姓名／辨識註記篩選；右側歷史按需開啟。原圖僅參考格線布局，沒有匯入圖中姓名；欄位維持 1～10 級。

滑鼠拖動姓名，手機長按小把手約 350ms 再拖曳；把手外可正常水平捲動，拖到表格邊缘會自動捲至遠欄。單擊姓名選格、雙擊／連點兩下查看資料並選目的級數，支援 Tab／Enter 查看、Space 選格；Escape 或 touchCancel 取消未送出的拖曳。姓名格不常駐完整資訊或多顆動作鈕，長姓名可雙擊開啟查看。

每次放下立即自動儲存，**不用填原因／備註**。只取消調級的原因必填，其他報名管理規則不變。逐次稽核保留真正帳號、時間、前後值；沒有填的原因留空。會員 `level`、報名快照 `hard_level_snapshot`、當次 `competition_level` 各自獨立。候補／取消不出現在排級表，但原管理入口保留；取消後重報用新報名 ID 和新快照，候補遞補沿用自己的當次級數。只限未刪除 open／closed 場次正取可調整，其他場次唯讀。

同一姓名格直到寫入及讀回確認完成才可再移動；其他格可獨立儲存。網路或 5xx 結果不確定時，保留原目的、version 及 request_id，只能原樣確認重試。409 不覆寫，核對後放棄未完成操作再移動。已存但讀回失敗時只重讀，不重送調級。原因不會由系統捏造。

首次進入合法可編輯安排時，以明確且有驗證的 POST 保存當下持久化正取名單為「起始基準」；直接調級 API 也會在第一筆異動前同交易建立。只建立一次；GET 與 migration 不建立基準或假造過往時間。

姓名格的橙色／數字前後值表示相較最近保存版改級，綠色／加號表示新增，右側歷史清單的灰色項表示移出。5→4→6 留兩筆逐次紀錄，淨差為5→6；回5消色但保留紀錄。基準是完整保存版，**不是報名快照**。更名不捏造級數轉換，同名或重報依報名 ID 比較。

按「保存完整安排」可直接採用預設版本名稱與登入帳號作顯示編輯者，也可修改；顯示編輯者支援選用先前名稱，備註選填。真正操作帳號另列且不可冒充，時間由伺服器記錄到秒。同一版保存完整正取快照（姓名、辨識、報名 ID、順序、級數等）。沒有淨差時不新增版本；僅改姓名／備註不算安排變更。

所有逐次儲存須確認後才能大存；伺服器也核對所見完整名單及最新版本，別人的改級、取消、遞補、重報、更名或另存會令過期請求409。大存在途或結果未知時，該場暫停拖動與再存；切場仍保留原請求。已成功但回應遺失的重試只確認原保存版，不重複新增，也不把它覆寫成目前名單／基準。確認後重新讀取最新工作及最新保存版；若已被別人接續修改，顯示提示並重算淨差。沒有後續異動時，保存後淨差色清除。失敗的名稱／顯示編輯者／備註保留，核對後可沿用。

歷史版本是唯讀完整名單，首個保存版對起始基準，之後各版對直接前版，以同色及右側前後值呈現。回「目前安排」只切換顯示，不還原資料。未完成請求及未送出欄位只保留在當前頁面記憶體；離開提醒不等於跨瀏覽器或重開頁面保存。

固定表頭可選取、合併相鄰標題及編輯文字；顯示合併不改變 1～10 級欄位身份，且不可跨表頭、標題列與資料區合併。桌面右鍵／Shift+F10 與觸控 ⋯ 開啟同一操作選單，點擊表格外或 Escape 關閉。白色是明確底色覆寫；沒有局部底色時才沿用列／欄底色。「整張表格」的復原依伺服器收據核對，與編輯器文字復原分開。

### 獨立合成預覽與驗證（8039／8040）

[8039 安排預覽](http://127.0.0.1:8039/admin/competitions)：選「合成 80 人級數安排（已截止）」。資料 `data/arrangement-preview.db`、成品 `frontend/dist-arrangement`、schema `0007_arrangement_versions`；帳密只存本機 `data/arrangement-preview-admin.json`。83 位合成會員、3 場比賽、85 筆報名；主場80正取，另外報名狀態只在管理入口查看。初始1→3示例會相較示例異動前基準顯色。沒有複製真實資料。

```powershell
# 僅首次建立；已有 DB／帳密／備份／還原檔會拒絕覆寫
uv run --locked python scripts/create_level_preview.py --variant arrangement
# 勿覆寫正在使用的成品；既有舊 dist 全部保留
Push-Location frontend
npm run build -- --outDir ../frontend/dist-arrangement
Pop-Location
# 已有8039運作時不重複啟動
$env:FUCHENG_DATABASE_URL='sqlite:///data/arrangement-preview.db'
$env:FUCHENG_COOKIE_SECURE='false'
$env:FUCHENG_STATIC_DIR='frontend/dist-arrangement'
uv run --locked uvicorn fucheng.app:app --host 127.0.0.1 --port 8039 --no-access-log
```

listener／launcher PID 分存 `data/arrangement-preview.pid`／`arrangement-preview-launcher.pid`，日誌同前綴 `.stdout.log`／`.stderr.log`。停止前用 `netstat -ano` 確認 127.0.0.1:8039 的 PID，再用 `Get-Process` 核對 Python 身分，才執行 `Stop-Process -Id (Get-Content data/arrangement-preview.pid)`；不可使用其他預覽 PID 檔。

```powershell
# E2E 一定使用專用測試DB，不能指向人工預覽
Push-Location frontend
$env:FUCHENG_E2E_STATIC_DIR='frontend/dist-arrangement'
$env:FUCHENG_E2E_DATABASE_URL='sqlite:///data/arrangement-e2e.db'
$env:FUCHENG_E2E_PORT='8040'
$env:PYTHONUTF8='1'
npm run test:e2e -- --output test-results/arrangement
Pop-Location
```

初始備份／還原檢查 `data/arrangement-preview-verification.json`；完整證據及手機模擬限制見 `docs/acceptance.md`。舊8037、8448／8450、ngrok與r7～r10包未隨本輪程式更新。正式或舊預覽升級須依 `docs/deployment.md` 停寫、備份與明確migration；不能直接套用新程式到舊schema。

自訂甲乙丙欄頭、當次安排列印、編隊／隊長／循環賽不在本輪範圍。原報名管理列印仍以報名快照為準。


## B：精確格位安排表（0008，本機合成驗收）

選手拖到哪一格就保存哪一格，同級換列也會自動儲存。有人格採插入向下讓位，先保留來源空格；必要時延伸資料列。文字／合併區保留，讓位選手跳過這些格子，不壓縮其他空格。未指定格位的點選／鍵盤移動放到目標級數欄最後已有內容之後。會員長期級數和報名 hard snapshot 不受影響。

數字級數標頭上方可新增文字標題列，選空白格後編輯「甲組」等文字、選範圍合併；左方插文字欄可放與選手同列的隊名。這些都是布局文字，不建立隊伍或對戰。表格實際邊界提供＋與插入線預覽，選取後才浮現文字／合併操作；浮動操作不推動表格。插行列保留原穩定ID，現有選手分組不會因顯示列號改變而變動。最多500列／50欄，文字每格500字，沒有公式或Office匯入。

合併只允許文字／空白，範圍有選手、多段非空文字、既有合併或跨越數字級數標頭時明確拒絕。底格文字位置不刪除，解除即恢復；合併格可直接改字，保留原非空文字來源格；原區全空白才用左上格。

單擊姓名選取儲存格；雙擊／連點兩下查看本場餐食、當次與長期級數。素食按鈕以本場報名餐食計數並加柔和強調及不遮住姓名的「素」標記，不影響橙色異動。搜尋只顯示匹配姓名，非匹配選手顯示「已占用」但保留格位；拖入這些格仍按真正占用插入，不會覆蓋選手。

橙色表示自最新保存版以來的格位或級數異動，移回原格／原級即清色；文字、行列、合併差異另外記錄，完整保存後建立新基準。開啟歷史後，左側「該版本變動」以緊湊卡片列出淨差、顯示正確比較版本並獨立捲動；右側「版本紀錄」與「目前安排」控制亦獨立捲動，兩側標題固定。卡片可用鍵盤／觸控定位選手變動前後仍存在的 stable 格位；舊版未存座標或來源軸已刪除時會說明限制，不猜測位置、不改布局或送出寫入。純結構差異仍可保存，不另顯示泛用結構提示，也不誤報沒有變更。固定級數表頭 hover 顯示格位游標。每次小存／大存在途、結果未知或成功待讀回時，該場暫停布局修改，仍可切場。未知重送原請求，409先重讀核對；文字草稿與大存名稱／顯示編輯者／備註會保留於本次頁面工作區。頁面重載不保留未確認的記憶體草稿，離頁會提示。

0007 舊歷史沒有座標，明示「未記錄儲存格位置」，僅按級數／順位檢視；未保存餐食／長期級數為未知。啟用B時以合法POST記錄當下位置基準，不補造舊歷史，也不清除A尚未大存的級數差。首次B完整保存後，位置與級數皆對新完整版比較。歷史唯讀，返回目前安排不還原、不寫入。

[本機8042預覽](http://127.0.0.1:8042/admin/competitions)：獨立 worktree `D:\projects\fucheng-players-system-worktrees\arrangement-grid`、新 `data/grid-preview.db`、`dist-grid`，83位合成會員／3場／85報名，主場80人含上方甲乙丙與左側合成隊名示例。帳密僅ignored `data/grid-preview-admin.json`。沒有讀取A密碼或真會員資料。此入口尚非B公開交付。

```powershell
# 只在B隔離worktree執行；不要覆寫正在8042使用的成品。
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend run build -- --outDir ../dist-grid
uv run --locked python scripts/create_level_preview.py --variant grid
$env:FUCHENG_DATABASE_URL='sqlite:///data/grid-preview.db'
$env:FUCHENG_STATIC_DIR='dist-grid'
$env:FUCHENG_COOKIE_SECURE='false'
uv run --locked uvicorn fucheng.app:app --host 127.0.0.1 --port 8042 --no-access-log
```

建立脚本拒絕覆寫DB／帳密／備份／還原檔。背景PID與日誌在 `data/grid-preview{,-launcher}.pid` 及 `.stdout.log`／`.stderr.log`。停止須先比對 netstat 的127.0.0.1:8042 listener及Python身分，僅停止該預覽，不能套用舊服務PID。

E2E 使用 `FUCHENG_E2E_DATABASE_URL=sqlite:///data/grid-e2e.db`、`FUCHENG_E2E_PORT=8043`、`FUCHENG_E2E_STATIC_DIR=dist-grid`、`PYTHONUTF8=1`，執行 `npm --prefix frontend run test:e2e`。桌面／手機用獨立合成帳號避免測試自身觸發登入限流，沒有放寬正式驗證。證據見 `docs/acceptance.md`。升級／回退見 `docs/deployment.md`。


### B拖曳互動修正成品

拖曳中顯示與來源相近尺寸的姓名／註記浮動卡，來源保留格位並降至25%透明；放下或取消不開資訊卡，下一次正常點擊／輕觸／鍵盤仍可查看。此增量的獨立待交付成品為 `dist-grid-drag`，身份 `data/grid-drag-delivery-identity.json`；沒有覆寫原 `dist-grid` 或現用公開static。後續凍結換版由維運task依該身份核對，E2E仍使用專用8043/grid-e2e.db，實際證據見驗收文件。


### B 表格編輯與當次安排列印（新授權增量）

此節覆蓋前述 A 階段「自訂表頭／當次安排列印不在範圍」的排除。滑鼠在格邊、空白或文字按住框選；姓名與把手繼續移選手。雙擊文字／合併格／欄標題可直接編輯，Enter送出、Escape取消；手機點選格後用「編輯文字」，點欄標題可改名，「範圍選取」再點另一角可選矩形，普通滑動仍為捲動。邊界＋新增／＋標題顯示實際插入位置，鍵盤可聚焦相同按鈕。級數標題是顯示名稱，底層1–10及會員／報名級數不變。

「列印安排」印目前正在檢視的安排或不可變歷史版，保留文字、合併、精確格位與全部姓名，不受搜尋或素食開關影響；已知素食一律印黑白可辨「素」。單幅A4橫向保持原表格，不新增列號／技术座標；寬表每幅最多12欄、長表每段18個資料列，分幅才提供續接資訊，跨幅合併文字標示續接。列印不替使用者保存完整安排，關閉或取消列印後清理暫存畫面。舊版缺餐食仍未知，缺格位則清楚說明僅依級數與順位呈現。瀏覽器縮放、紙張、超長內容與實體列印需使用者在列印預覽核對，沒有宣稱任意大小表格都能塞單頁。

此增量為未提交 B snapshot，獨立成品 `dist-grid-edit`，測試DB `data/grid-edit-e2e.db`／8043，身份 `data/grid-edit-delivery-identity.json`。未更新8042或公開eb24；後續由task5序列凍結與受控換版，必要後端更新但無DB migration。舊backend不支援column_title，且response會遺漏title，不可當作新資料的無損回退版本。證據及界限見驗收／部署文件。


### B 三項顯示與刪除增量（2026-09-21，本機完成待受控換版）

行／自訂文字欄邊界的「⋯」可刪除指定整排或文字直欄，顯示範圍預覽；含文字先列出將刪除與保留內容，再明確確認。含選手的排必須先移走選手，固定1–10級欄及最後一排資料格不可刪。合併區保留合法剩餘範圍及唯一文字；不能無歧義保留時阻擋。刪除沿用token、同交易稽核及原樣重試，其他選手格位與version不動。

素食按鈕開啟時為深綠底白字、關閉時白底深綠字，保留人數及aria-pressed；不篩人、不寫入，列印仍獨立標「素」。保存紀錄由起始基準至最新排序，每次打開都捲到最新，包含仍選取舊版時重開；不改已選版本。保持開啟閱讀時，一般畫面更新不搶捲動，新大存回到最新。

本輪成品 `dist-grid-axis`、合成DB `data/grid-axis-e2e.db`／8043、身份 `data/grid-axis-delivery-identity.json`。尚未更新公開eb24；現用grid-edit版與後續使用者資料保留，task5再受控凍結換版。需要同批前後端更新，schema0008及依賴不變。拖曳仍採插入／下移，本段為axis版歷史紀錄；後續中央交換已獲授權，見下節。


### B 灰階、雙區拖曳與歷次級數（2026-09-21，已公開換版待人工驗收）

- 姓名卡中央顯示交換對象；上下邊界顯示插入線及上／下方提示；空格直接移動。來源留洞，中央交換只影響兩人；放手採用當下已顯示的意圖。手機長按把手同樣操作，普通姓名輕觸仍開詳情。
- 精簡＋在桌面邊界hover／鍵盤focus出現；邊緣可點選或右鍵，高亮整排／欄並開啟底色與刪除。手機可點窄邊緣直接操作，＋仍可直接插入；沒有常駐「＋新增」文字或標題鉛筆。雙擊文字／標題編輯，手機點標題或選格後「編輯文字」。
- 行／表頭及自訂文字欄有無底色、3階淺灰；交叉取較深色，合併格取整個涵蓋範圍最深色。底色跟隨完整保存、歷史及列印；黑字、素食徽記與橘色異動邊框並存。
- 單人詳情以「歷次比賽級數」顯示最近5場已結束比賽，無資料／查詢失敗分別提示。歷史快照的餐食／級數不變，參考區加註「以下為目前查詢結果」。移到級數是緊湊的次要操作，仍放欄底。

成品 `dist-grid-interaction`、合成驗證 `data/grid-interaction-e2e.db`／8043，交付身份 `data/grid-interaction-delivery-identity.json`。已由 task5 更新同一 eb24，公開新前後端身份見頁首。無migration／依賴變更；新operation及shade同批更新，舊app不可視為無損回退。Windows／Chromium桌面與觸控模擬、PDF證據見 `docs/acceptance.md`；未驗證其他OS、實體手機或印表機。


### 選格工具與本次編輯復原

安排表上方提供復原、選取儲存格底色、文字編輯、合併與解除合併；窄螢幕可換行，選取不新增浮動列。「表格底色」與四個色票共用外框；最左純白色票清除局部底色並恢復既有排／欄色，右側為三階灰色。成功上色保留選取，可直接連續換色；重點相同色不送出請求。桌面可在選區右鍵，手機由上方工具操作；直接輕點姓名選取該格，詳情不再提供重複選格入口。局部色屬於格位，移動選手後仍留原格；橘底標示尚未大保存的位置／級數異動，大保存後露出格位底色，素食綠標另行保留。

「復原上一個動作」與「重做」可逐步復原／重做本次頁面已確認的安排操作；Ctrl／Command+Z 復原，Ctrl／Command+Shift+Z 或 Ctrl+Y 重做。重做按鈕會明確顯示可用狀態。復原及重做都依伺服器收據與目前狀態驗證，自動保存並留稽核，不刪保存歷史；新操作清除重做分支，外部更新、大保存或狀態不符會斷鏈。輸入欄、文字 dialog 與中文組字保留原生復原；pending、結果未知、鎖定及歷史唯讀狀態不發編輯請求。重新整理不保留本頁復原／重做堆疊，也不提供回寫歷史版本。

詳情右上叉叉、Esc 或點視窗外面均可關閉。文字編輯 Enter 或點外面會保存退出，Esc 取消本次輸入；中文組字中不提交，失敗保留草稿。已送出的操作不能靠關閉撤銷，未確認時可返回表格核對，原文字仍保留。


固定級數表頭現在預設顯示文字：單擊／鍵盤選取後，用上方工具列編輯文字或底色，雙擊才進入直接編輯。表頭色只影響表頭，不改下方資料格或級數身份；表頭與資料格不混選合併。安排請求若 20 秒內未完成，會顯示核對入口；未確認寫入保留原請求，使用「確認操作結果／原樣重試」，不要視為已取消。已有保存收據但讀取未完成時，只需「讀回目前安排」。


### 版本雙欄與選手選取

開啟歷史後，寬桌面依序顯示主表格、該版本變動、版本紀錄；寬度不足時保留表格寬度，兩區置於下方，手機先變動後版本。兩區可分別捲動，版本仍由舊到新、每次開啟定位最新，保持開啟閱讀時不搶捲動。寬桌面側欄上下緣隨實際表格尺寸對齊，標題／控制固定、內容各自捲動；頁首導覽也使用相同容器寬度。變動卡可用點擊、鍵盤或手機觸控，讓表格標出選手變更前後仍有記錄的格位；舊版本未記錄格位或來源列已刪除時會顯示提示，不推算位置。

姓名單擊／輕點只選格，不修改安排；雙擊／連點兩下開資訊。Enter 查看、Space 選格；範圍選取時點姓名只延伸選區，不開資訊，包含選手的選區不可合併。滑鼠拖曳姓名與手機長按把手沿用原操作，拖放不開資訊；歷史可選取及查看資訊，但不能修改。

## 安排 Excel 匯出與工具列

管理端安排頁可將目前所檢視的完整安排下載為可編輯 `.xlsx`，保留姓名、辨識註記、本場素食、文字、空位、表頭、合併與灰階。搜尋與素食開關不裁減匯出名單；歷史只使用該版本保存內容，舊版未存格位會標示限制。匯出只供離線編輯，不會保存或回寫系統，也不提供匯入。

歷史按鈕以深／淺底顯示開關；搜尋改用置中的放大鏡圖示，放在文字按鈕後。一般手動刷新圖示已移除，讀取失敗、衝突與未知操作的必要恢復入口仍保留。匯出失敗可原頁重試，未確認狀態及儲存中不允許匯出。驗證與限制見 `docs/acceptance.md`。

安排操作結果未知時，保留原頁並使用確認按鈕，不以重新整理取代恢復。若登入已失效，請在另一分頁以原帳號登入，再回原頁確認；恢復會先更新認證，已確認保存的操作只讀回，未知操作以原請求確認。409等確定拒絕仍先重新核對，不自動改寫目標。


同色上色鎖場修正（2026-09-22，待受控更新）：已用合成資料重現使用者的「安排沒有變更」與「重新讀取並核對」；原因是未變更的 422 被視為待人工解除的拒絕。現在首次請求收到這個精確回覆後自動讀回，核對成功即可繼續；一般拒絕、衝突、未知請求仍保護。工程證據與交付指紋見 docs/acceptance.md、data/grid-shade-delivery-identity.json；本段不表示已部署。
