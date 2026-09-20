# 架構與資料模型

## 系統結構

瀏覽器與 FastAPI 使用同一 origin。React/Vite 只在開發或image建置階段使用，正式由單一app runtime image的Uvicorn/FastAPI提供靜態成品與/api。SQLite存獨立Linux named volume；維護／備份復用app image，正式Cloudflare named tunnel直連app。nginx僅本機HTTPS test profile，不是正式依賴；沒有Redis、Celery或額外資料庫服務。Windows Docker Desktop/WSL2現場步驟見docs/deployment.md；本機驗證不代表球館實機與24小時可用性。

容器入口持有writer.lock至服務終止，ops遷移/還原需相同獨占鎖，backup.lock保護備份/retention/export及維護；active.json選DB，maintenance.json讓失敗維護持續拒絕啟動。image schema必須與DB revision一致，start不升級；回退還原新DB並保留原DB/WAL/SHM及operations證據。來源以逐檔snapshot manifest辨識，不把HEAD當未提交內容的完整版本。

部署設定public origin時啟用DeploymentBoundary，Uvicorn --no-proxy-headers：只信任指定socket peer，Cloudflare取CF-Connecting-IP、ngrok取XFF/XFP最後值，Host固定且所有寫入要求同源Origin，再經既有session/CSRF。開發/歷史loopback預覽未設定public origin時維持原行為。

首頁是球館公告與比賽時程入口，公開候選搜尋僅含姓名、辨識註記與選取 ID，不提供級數、預設餐食、原會員編號或報名名單。分級完整名單在 `/members` 免登入公開，`/api/public/members` 僅提供 id／name／distinguishing_note／level。公開與管理 API 使用不同且明確的回應 schema。

## 一致性與安全

- `members.id` 是系統 UUID；姓名可重複，辨識註記獨立，原會員編號選填且有值時唯一。
- 級數的合法範圍是 1～10，畫面只依數字升冪呈現，不賦予強弱方向語意。
- 葷素為 `unset`、`omnivore`、`vegetarian`；確實未知時仍使用未設定。依球館目前名單語意，未標示素食者回填為葷食，新增會員也預設葷食。
- 停用會員仍留在資料庫與稽核歷史，管理員分級名單只查 `is_active=true`。
- 每次更新帶入 `version`，SQL 使用 `WHERE id=? AND version=?` 原子更新。版本不符回傳 409 與可理解提示。
- 建立／修改與 `member_audits` 寫入同一交易；紀錄管理員、UTC 時間與欄位前後值。
- 時間在 SQLite 以 UTC 儲存，ORM 讀取為 aware UTC；前端以 `Asia/Taipei` 顯示。
- 登入密碼使用標準函式庫 scrypt（隨機 salt、N=32768、r=8、p=1）。隨機 session token 只以 SHA-256 摘要存入資料庫；cookie 為 HttpOnly、SameSite=Lax，正式環境 Secure。寫入與登出另驗證 session 內 CSRF token。
- SQLite 連線開啟外鍵、10 秒 busy timeout、WAL 與 `synchronous=FULL`，不犧牲耐久性換取效能。

## 資料表

| 資料表 | 用途與關鍵約束 |
| --- | --- |
| `admins` | 維護指令建立的管理員，帳號唯一，不提供公開註冊 |
| `login_sessions` | session token 摘要、CSRF、到期時間；管理員刪除時級聯 |
| `members` | 穩定 ID、姓名、辨識註記、原編號、1～10 級、葷素、啟用與版本 |
| `member_audits` | 會員、實際管理員、UTC 時間、動作與前後差異；外鍵限制刪除 |
| `fee_periods` | 預留期間，日期範圍唯一且結束日不得早於開始日 |
| `member_fee_statuses` | 預留會員／期間狀態，每組唯一；只有明確列才代表 paid/unpaid/waived |

會費表在第一版沒有 UI、API、一般匯出或實際資料建立流程，也不得影響名單、排序、會員啟用或未來報名資格。「沒有列」只代表尚未記錄。

## 第二階段：比賽與管理員報名名單

比賽保存名稱、日期、名額、截止時間、備註、狀態與版本。管理員從啟用會員選取參賽者；停用會員不再出現在選取器，但既有報名與歷史不變。比賽與報名管理 API 全部需要 session，寫入另需 CSRF。

### 狀態與規則

- 合法轉換為：草稿可維持草稿、轉報名中或取消；報名中可維持、轉報名截止或取消；報名截止可維持、轉已結束或取消。已結束／已取消唯讀。
- 草稿不接受報名；`status=open` 仍會以 `registration_deadline` 做有效截止判斷。截止後允許管理員補登、取消、遞補與修改餐食，但理由必填。
- `capacity` 不得小於目前正取數。增加名額只提高 `pending_promotions`，不自動改動候補。
- 同場同會員以 SQLite partial unique index 保證最多一筆非取消紀錄；取消保留原列，重新報名建立新列與新順位。
- `queue_sequence` 由比賽內單調遞增計數器產生，並有 `(competition_id, queue_sequence)` 唯一約束；時間相同也能穩定排序。
- 有空位且沒有有效候補時，新報名正取；已滿或已有候補時進候補尾端。正取取消只釋出名額；只能人工確認第一位有效候補。
- 報名保存會員當時的 `hard_level_snapshot` 與獨立 `diet`。之後會員預設級數或餐食改變，不回寫既有報名。

### SQLite 交易與重複操作

比賽／報名寫入在驗證 session 與 CSRF 後，先結束驗證造成的唯讀交易，再執行 `BEGIN IMMEDIATE`。SQLite 因此會在讀取名額、第一候補與版本前取得單一寫入保留鎖；名額判斷、狀態變更、順位計數及稽核插入在同一交易提交。這不是前端鎖，也不是交易外先算剩餘名額。

每個新增、取消、遞補與餐食更新帶 8～64 字元的 idempotency key，`registration_audits.idempotency_key` 唯一。相同 key 重送回傳同筆報名的目前狀態，不再次異動；不同管理員同時遞補同一人時，第一筆完成後第二筆因版本／狀態不符而失敗，且不會順帶遞補下一位。

### 資料表

| 資料表 | 用途與關鍵約束 |
| --- | --- |
| `competitions` | 比賽設定、狀態、版本及下一個穩定順位 |
| `competition_audits` | 比賽設定前後值、操作者、理由與 UTC 時間 |
| `competition_registrations` | 會員關聯、正取／候補／取消、當次餐食、硬實力快照、順位與版本 |
| `registration_audits` | 每次報名操作、理由、操作者、UTC 時間及唯一 idempotency key |

管理介面固定顯示全場總數，另列篩選結果，避免搜尋後把局部筆數誤認為整場摘要。飲食姓名與管理列印只在登入後提供；沒有公開比賽名單 API。

會員帳號、自行取消、拖曳軟分級、自動分隊及正式部署不在本階段範圍。


## 第三階段：免登入選名報名

### 流程與身分邊界

`/competitions` 列 open 且尚未截止的比賽。`/register/:id` 提供姓名搜尋、同名註記選取、餐食及確認。使用者手動選取既有 ID，不由姓名或模糊比對直接判定身分。搜尋至少一字、最多 20 筆，LIKE 特殊字元跳脫；另有公開分級名單端點，權限與回應欄位依本節最新公開決策。公開報名僅接受 omnivore／vegetarian，預設葷食，不查閱該會員原本餐食；管理員與歷史資料仍支援 unset。

這是紙本報名的線上形式，不驗證本人，可能代報。member_id 是被登記的參賽者，不能當成已驗證操作者。公開成功回應只含本次提交的姓名、註記、餐食與正取／候補結果，不含報名 ID、順位、歷史或其他人資料。不同瀏覽器重複替某人報名回 409，並不回傳其現有正取／候補身分。取消、更正、遞補及比賽修改只有管理員 API。

### 自動瀏覽器防護

`GET /api/public/registration-session` 自動建立 12 小時匿名瀏覽器上下文，使用者無須登入或操作；cookie HttpOnly、SameSite=Lax、預設 Secure。`public_visits` 只保存隨機 token 的 SHA-256 摘要、CSRF、到期時間及稽核關聯 ID，不具會員授權含義。有效上下文沿用，重新載入不改變未完成操作的 idempotency 身分。

姓名搜尋要求有效上下文；報名另需 matching X-CSRF-Token，有 Origin 時核對同源。auth_attempts 保存 15 分鐘窗口的雜湊計數，跨 worker／重啟有效，成功與失敗都計數：建立上下文 IP 600／全域 1800；搜尋 visit 180／IP 1200／全域 3600；報名 visit 20／IP 600／全域 1800。超限回 429／Retry-After 900。管理員登入另有 10／40／300 限制。速率及 CSRF 防護不保證本人，不能阻止所有惡意代報。

API no-store、Referrer-Policy no-referrer。驗證及資料庫錯誤不輸出原始 payload、SQL 或秘密。過期且未被稽核參照的 visit 在建立新上下文時清除，已被稽核參照者保留、過期不可再使用。管理員 session 與匿名上下文不能互換。

### 共用交易與稽核

管理員與公開報名共同呼叫 `registrations.py` 的 create_registration_service；取得 BEGIN IMMEDIATE 後重新核對 session／visit 期限，才檢查會員啟用、比賽狀態、截止、正取及候補。報名、獨立餐食、硬實力快照、順位計數與稽核同一交易。公開 payload 不接受狀態、順位、級數或截止後理由。

沿用有效報名 partial unique index、有候補不搶空缺、取消不自動遞補、管理員確認第一有效候補，以及取消後新報名排尾。管理員取消／更正／遞補仍由 _mutate_registration 執行。idempotency key 綁定 action、target、payload 指紋及 actor visit/admin ID；跨訪客或內容重用回 409，換新 key 重複報同會員也被有效報名約束拒絕。已完成請求重送可讀取同筆目前結果，不再次修改。舊第二階段 key 沒指紋，保守回 409。

報名與 registration_audits 的來源使用 admin|public|system，CHECK 約束：admin 只能且必須有 admin_id；public 只能且必須有 visit_id；system 兩者皆空。公開來源顯示「免登入報名（身分未驗證）」，不使用選取會員作為假 actor。會員基本資料及比賽設定的舊 admin 稽核不變。

### Migration

`0003_public_registration` 從 `0002_competition_registration` 新增 public_visits／auth_attempts，擴充報名與稽核來源及 request_fingerprint，舊資料保留為 admin。沒有會員帳號、啟用 token 或會員 session 表。

SQLite batch 重建被參照表時，Alembic 專用連線暫關 FK enforcement，以顯式 BEGIN IMMEDIATE 包住 DDL、資料搬移及 revision，提交前 foreign_key_check，故障整體 rollback，最後重開 FK。一般連線維持 foreign_keys=ON、WAL、busy_timeout=10000、synchronous=FULL。正式遷移必須先備份及停機，不以 create_all 取代 migration。

## 球館首頁、公開分級與公告

依 2026-09-18 使用者確認，分級表等同比照球館公共公告欄：任何人可讀啟用會員的姓名、級數及辨識註記；停用會員不列出。會員餐食、原編號、會費、帳號、稽核與參賽名單仍不公開。內部 UUID 只供資料對應，不具修改權限。

公共頁面共用 SiteNav：`/` 最新消息、`/members` 會員分級、`/competitions` 比賽報名。首頁讀取 `/api/public/announcements` 與 `/api/public/schedule`，不需要建立訪客上下文。後者只列非 draft 比賽，open 到達截止時衍生顯示 closed；既有報名 API 保持交易內截止驗證。尚未開放的時間預告可用公告說明，不將未發布草稿當預告，尚無自動開放排程。

`0004_club_website` 在第三階段 schema 上新增 announcements 與 announcement_audits，不修改會員或報名資料。公告以 is_published 控制公開、is_pinned 控制排序，首次／重新發布寫入 published_at，updated_at 記錄修改。所有公開公告回應只含內容及顯示時間，不含操作者或版本。

管理員公告寫入沿用 session／CSRF 依賴及 `_begin_immediate`，在寫鎖內重驗 session、檢查 version，同一交易更新公告與具名 admin 稽核。request_id 有唯一約束，指紋包含目標、payload 與 version，重送必須符合原管理員及指紋；相同操作不增加第二筆公告／稽核。草稿與下架內容不對外回傳，無刪除 API；React 以文字渲染 body，保留換行並跳脫 HTML。

## 已確認紙本正取名單匯入

`roster_import.py` 提供具 session／CSRF 保護的管理 API。僅接受空白 draft 的指定 version，每列明確指定既有 member_id 或確認 create_member，不做姓名推測；新增同名、既有資料變更、重複來源／會員、超額及非空草稿皆拒絕。全數正取才可提交，沒有推導候補先後的功能。

`_create_registration_in_transaction` 從原單人報名服務抽出，保留正取／候補計算、會員快照、有效報名唯一約束、sequence 與稽核建立。單人與批次各自持有寫鎖、權限／狀態檢查與 commit；批次在一筆交易內包含新會員及稽核、全部報名及稽核、competition audit 與 draft → closed，不對外暴露中間開放狀態。

每列 RegistrationAudit 的 key 由批次 request_id 與列位置雜湊取得；所有列綁定同一份完整 payload 指紋與 actor。第一列稽核存在代表原批次已完整提交，重送返回目前場次摘要；跨 actor 或內容重用 key 拒絕。CompetitionAudit 保存 source_ref → member_id／registration_id 與新增會員標記供追溯。沒有增加 schema，revision 仍為 0004_club_website。

## 可還原的比賽刪除

`0005_competition_deletion` 只在 competitions 新增 nullable deleted_at，不搬移或刪除報名。deleted_at 與業務 status 分開；刪除／還原不改正取、候補、取消狀態、當次餐食、級數快照或 queue_sequence。

`competition_deletion.py` 的 `/api/admin/competitions/{id}/delete` 與 `/restore` 都要求管理員 session、CSRF、confirmed=true 與 version。與報名共用 `_begin_immediate`，鎖內重驗 session 與目前版本；更新 deleted_at、版本及 CompetitionAudit 的 admin／時間／before-after 在同一交易。版本遞增防止同版本重送或並行操作執行兩次，稽核失敗完整回滾。刪除與報名並行會依寫鎖序列化，先完成的報名仍被保留。

管理列表預設 deleted=false，deleted=true 專供已刪除區；管理詳情可唯讀檢視。公開時程、可報名列表／詳情皆排除已刪除場次。管理更新、單人新增／取消／遞補／餐食及整批匯入均在鎖內阻擋 deleted_at。已完成 idempotency 請求可讀原結果，但不重新寫入。還原恢復原 status，是否接受公開報名仍由截止時間判斷。

前端使用原生 dialog 限制焦點，初始焦點為保留，Escape 可取消；送出時鎖定操作，錯誤保留對話框並提示。已刪除區有明確的唯讀提示與還原確認。

## 當次比賽級數（0006_competition_level）

`competition_registrations.competition_level` 是非空 1～10 級，與 `members.level`、`hard_level_snapshot` 分開。Migration 只從每筆自己的 hard_level_snapshot 回填（包含正取、候補、取消），不從會員目前級數回填，不改舊列的版本、操作者、時間、排序或稽核。先加入 nullable 欄位、回填，再以 batch 建立 NOT NULL／CHECK；沿用 migration 的 BEGIN IMMEDIATE、外鍵檢查及 DDL rollback。不得破壞性 downgrade。

單人管理、公開及批次匯入都由 `_create_registration_in_transaction` 同時初始化快照與當次級數；新報名稽核保存當次級數初值。取消留原列，重報新列用新快照初始化；候補遞補不修改當次級數。Migration 回填屬 schema 初始化，不假造管理員調級稽核。

`PUT /api/admin/registrations/{id}/level` 輸入 version、competition_level、非空 reason、request_id；多餘欄位及非整數級數拒絕。沿用 session／CSRF 與 `_mutate_registration`，在 BEGIN IMMEDIATE 後重驗登入、比賽狀態、正取身分與版本。僅 open／closed 且未刪除場次正取可調整，截止時間不阻擋；同級數回 422，不增 version、不寫空白調級稽核。更新當次級數、報名版本、操作者／時間及 action=level 的 RegistrationAudit 同交易，失敗全回滾。request_id 仍綁 actor／target／payload 指紋；完全相同已完成重送讀目前結果，不重新寫入。

管理回應新增 competition_level；`summary.competition_level_counts` 只統計正取當次級數，原 `summary.level_counts` 保留正取硬實力快照語意。公開端點 schema 不變，沒有公開參賽名單或當次級數。管理歷史額外回傳 registration_id／姓名註記／queue_sequence／reason／changes；前端顯示每筆調級的前後值及實際 admin／UTC 時間（顯示為台北時間）。讀取失敗清空舊歷史，場次切換取消過期回應。

CompetitionLevels 與原報名名單分區：安排區以當次級數搜尋分區，原名單維持快照篩選及列印。草稿按 registration_id 保存在 CompetitionManager 外層，固定編輯時 base version；篩選、重新讀取及頁內場次切換不覆蓋草稿。409 停止送出並保留輸入，由管理員核對後明確放棄草稿、重新開啟；其他失敗以原 key 重試。草稿是頁內記憶體狀態，beforeunload 提醒不等於持久化。
