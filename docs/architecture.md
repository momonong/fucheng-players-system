# 架構與資料模型

## 系統結構

瀏覽器與 FastAPI 使用同一 origin。React/Vite 只在開發或image建置階段使用，正式由單一app runtime image的Uvicorn/FastAPI提供靜態成品與/api。SQLite存獨立Linux named volume；維護／備份復用app image，正式Cloudflare named tunnel直連app。nginx僅本機HTTPS test profile，不是正式依賴；沒有Redis、Celery或額外資料庫服務。Windows Docker Desktop/WSL2現場步驟見docs/deployment.md；本機驗證不代表球館實機與24小時可用性。

容器入口持有writer.lock至服務終止，ops遷移/還原需相同獨占鎖，backup.lock保護備份/retention/export及維護；active.json選DB，maintenance.json讓失敗維護持續拒絕啟動。image schema必須與DB revision一致，start不升級；回退還原新DB並保留原DB/WAL/SHM及operations證據。來源以逐檔snapshot manifest辨識，不把HEAD當未提交內容的完整版本。

部署設定public origin時啟用DeploymentBoundary，Uvicorn --no-proxy-headers：只信任指定socket peer，Cloudflare取CF-Connecting-IP、ngrok取XFF/XFP最後值，Host固定且所有寫入要求同源Origin，再經既有session/CSRF。開發/歷史loopback預覽未設定public origin時維持原行為。

首頁是球館公告與比賽時程入口，公開候選搜尋僅含姓名、辨識註記與選取 ID，不提供級數、預設餐食、原會員編號或報名名單。分級完整名單在 `/members` 免登入公開，`/api/public/members` 僅提供 id／name／distinguishing_note／level。公開與管理 API 使用不同且明確的回應 schema。

公告 `body_format` 區分舊純文字與新版受限 HTML。服務端清理只保留標題、段落、列點、編號、粗斜體、底線、安全 http(s) 連結與受限對齊；舊純文字由 React 當文字渲染。內文圖片以 `<figure data-media-id="UUID" data-align="…"></figure>` 保留段落順序，最多 20 個不重複媒體 ID；`img` 原始 src、base64 與外站圖片均不保存。上傳先要求已儲存草稿，媒體 UUID 須屬於該公告，版本／CSRF／request_id／稽核仍受同一交易保護。照片解碼與正規化後以伺服器 UUID 檔名放在 `FUCHENG_DATA_DIR/announcement-media`，DB 的 `announcement_media` 保存 MIME、大小、SHA-256 與公告關聯；舊式文末照片仍由 `photo_id` 指向。公開媒體路由每次核對公告已發布且仍在內文或文末引用，管理媒體路由另需 session。舊檔保持不可變，以免備份與併發讀取失去來源。Docker snapshot 同時封存 DB 和媒體，匯入/還原先驗 hash 與 DB 關聯，再切換 active pointer。schema 仍為 `0009_announcement_media`，須與新版前後端和 runtime 同批更新。

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

## 當次級數與完整安排（0006／0007）

`competition_registrations.competition_level` 是非空 1～10 級，與 `members.level`、`hard_level_snapshot` 分開。0006 只由各筆快照回填當次級數；新報名以自己快照初始化，取消留歷史，重報新列／新快照，候補遞補不重設。公開端點不回傳當次名單，原 summary.level_counts 與名單列印保持快照語意。

`PUT /api/admin/registrations/{id}/level` 輸入 version、competition_level、request_id，可省略 reason（空白正規化為 null）。多餘欄位、非法級數、非整數拒絕。既有 session／CSRF、BEGIN IMMEDIATE 內重驗session、報名version、未刪除open／closed正取限制與同級422不變。只放寬調級原因，其他操作的截止後原因仍必填。更新級數、version、操作者／時間及 RegistrationAudit 同交易，初次調級也須將異動前baseline與初始化audit放在同交易。任何一步失敗全回滾。level request_id 綁定actor／target／payload，重試回目前報名列，因此可能比原成功版本更新。

0007 只新增 `arrangement_versions`，不回填baseline、不修改舊表資料。每場 `(competition_id, sequence)` 唯一；sequence=0 是真正初始化時保存的起始基準，1以上是大存版本，排序不用秒時間。單表rows_json儲存完整正取快照，每列保留registration_id、member_id、當時姓名／辨識、queue_sequence、competition_level及version。另存server秒時間、label、editor_label、真正admin_id及當時actor_name；request_id全域唯一且綁定payload指紋。沒有修改／刪除版本API，不提供還原覆寫。

管理API：

- `GET /api/admin/competitions/{id}/arrangement`：純讀的工作rows、editable、state_token、最新基準完整內容及版本摘要。auth查詢後明確BEGIN建立SQLite一致讀，名單、會員名稱、基準及token同一快照；不是依賴SQLite legacy SELECT implicit transaction。
- `POST .../arrangement/initialize`：auth＋CSRF，BEGIN IMMEDIATE、重驗session及場次，只有未初始化時新增sequence0與CompetitionAudit。重開／並行初始化不重設。直接level API在第一筆異動前也ensure同一baseline。
- `POST .../arrangement/versions`：完整保存，payload含request_id、state_token、base_version_id及可選label／editor_label／note。預設「版本 N」及真正登入username，空備註存null。先查已完成相同key／actor／payload並回原immutable保存版，再核對可寫狀態／token／最新基準。token涵蓋competition id／version／status／deleted_at、所有報名status／version／姓名／辨識／順序／級數及latest id。BEGIN IMMEDIATE內比對，不信任前端disabled。過期409，淨差為空422。新版本與CompetitionAudit原子提交，失敗全部回滾。
- `GET .../arrangement/versions/{version_id}`：authenticated唯讀完整版，跨場或不存在404。

淨差按registration_id比較前後級數及成員集合，取消後重報是舊ID移出＋新ID新增，候補遞補是新增，更名不偽造級數轉換。僅改version／姓名而級數及成員集合不變，不能另建無淨差版本；後續有安排變化時保存當時完整姓名。首個保存版對sequence0，後續對直接前版，目前工作對最新保存版；hard_level_snapshot不參與基準判斷。

前端以 `useArrangementWorkspace` 在 CompetitionManager 保存各場工作讀取、level pending、bigsave pending及metadata draft，切場不重定向非同步回應。狀態rows與token來自同一API結果，不混入另一detail GET。每場generation使舊GET失效；bigsave回來只作receipt，必須新GET讀取最新工作及最新baseline，不能把原receipt直接覆寫到current。其後有人再存或調級時顯示核對提示並重算淨差；只在沒有後續異動時清色。原請求payload/key凍結，未確定時禁止再存或本場拖動。

level每格獨立pending：saving→成功但待讀回refresh→fresh state確認version後解除；GET失敗仍鎖該格，僅重GET。未知結果固定原payload/key重PUT；409等明確拒絕可放棄再讀，不能偷換version。其他格可獨立操作，大存須所有格完成且state verified。metadata失敗保留；known拒絕核對後用新token/key保存，unknown只能原樣確認。beforeunload提醒，頁內記憶體不是持久離線佇列。

排級數與報名／設定分開入口。LevelCardBoard是10欄緊湊table，手機容器水平捲動保欄位；只有小把手touch-action:none，其他區域pan-x/pan-y。350ms長按、滑鼠drag、邊缘水平／垂直捲動、單擊姓名選格、雙擊姓名展開選級數／鍵盤替代共用移動入口。橙色附前後值代表改級、綠色附加號代表新增、灰色側欄項代表移出；短暫移動描邊和持續淨差不同。歷史選版後所有格唯讀，回目前只切UI、不寫DB。state.editable隨重新讀取更新，外部結束／刪除後立即呈現唯讀。

目前無自訂表頭、當次安排列印、編隊或比賽引擎。版本和備份不可丟棄，0007 downgrade明確拒絕；維運回退需0006相符image與升級前備份還原至新target，保留更新後資料庫。


## 0008 精確布局文件與交易

`arrangement_workspaces` 每比賽一列，存目前 layout JSON、revision、初始化 layout、實際時間／admin；`arrangement_operations` 保存actor/payload綁定的 immutable receipt。`arrangement_versions.layout_json` nullable，新增欄不修改0007歷史row JSON或metadata。API `schema_version=2`表示具有新安排回應能力，版本自身 `schema_version=1/layout=null`表示當時沒有保存位置；布局文件內獨立 `schema_version=1` 描述 rows(role header/body)/columns(kind level/text)/sparse cells/merges 結構。

穩定行列 ID 決定語義位置，完整有序row/column陣列保留空格與空行列；第幾個物理欄不能推導級數。操作以strict tagged union輸入及明確GridLayout/GridReceipt回應。BEGIN IMMEDIATE內驗auth/CSRF/lifecycle、完整state token（含本場diet/長期level）、目前layout，server運算操作，不接受client全表替換。操作結果、workspace、必要registration level/version和CompetitionAudit/RegistrationAudit一次commit；任一步失敗整體rollback。每個實際搬位者（包含被推下者）遞增registration.version；純插入列造成索引位移不遞增。

legacy move插入路徑先移除來源留洞，目的為body級數格；遇選手交換carry並向下尋下一可用body格，文字與merge跳過，空格立即停止推移，必要時append body row。不接受選手落文字／合併／標題格。舊直接level API用原version契約，成功在同tx把選手放對應欄底；管理／公開正取新增、取消、遞補亦同tx同步既有workspace。沒有workspace時不因公開報名擅自生成admin布局基準。

合併保留底格文字，不含選手、不重疊、不跨header/body，拒絕多段非空文字；unmerge只移除merge記錄。text操作可直接編輯合併區：使用唯一非空文字來源格，只有全空白才用anchor；多段文字或有人格衝突拒絕，保留其餘底格及解除座標。結構淨差忽略request/revision等技術欄，merge UUID亦不當內容差；row/column ID與順序、文字、merge端點以及玩家座標皆入完整保存。

新布局初始化只由合法管理POST或首次合法調級的同交易執行，GET與migration不寫入。不改舊latest；舊latest.layout為null時，級數/名單差仍對舊保存版，位置/文字差對本次B初始化布局，介面明示分別基準。舊快照缺少diet/member_level預設null，不能join當前值補歷史。新保存凍結全部row展示資料與布局。

同場所有布局修改／大存串行，unknown固定payload重送先查receipt，已知409重新讀取再由使用者核對送新請求；成功receipt之後讀fresh state再解鎖。切場不重定向晚回應，舊receipt不倒退latest。文字草稿由父controller按competition/cell保留，metadata亦保留；成功fresh state清對應草稿。搜尋渲染占位且不改layout，素食只改展示state。新資料不流入公開schema。


### 0008 JSON 相容擴充：顯示標題與列印

columns增加可選 `title`（不變更layout schema_version或資料表）；`column_title`以stable column ID修改顯示文字，與其他operation共用完整token／actor-payload receipt／交易稽核。title不改kind/level、選手格位、registration.version或會員／hard snapshot。missing/null預設「n 級」或「文字／備註」，明確空字串仍是空標題；前後端signature採相同預設正規化，改回預設沒有淨差。GET及舊receipt讀取只解析response，原DB JSON bytes不回填；新完整版本凍結title，後續改名不影響歷史。

桌面框選與拖人分開hit ownership，前者從空白／文字／格邊起手，後者仍用name/grip。首次選取工具浮動而不推版面；手機明確二點選取保留原生pan。標題草稿使用competition/column stable ID，文字仍按competition/cell，成功fresh read才清除；unknown仍整場鎖並原樣重試。inline Enter排除IME composition，Escape取消此次編輯。

ArrangementPrint從選定版本的完整rows/layout建立凍結printJob，portal隔離既有會員／管理名單print CSS。沒有按搜尋或diet toggle裁資料，diet只用該版rows。列印完成／取消afterprint、切場／切版及unmount清理portal，防止後續列印舊版。12欄／18body列分幅維持stable座標，每選手只屬一幅，交界merge取交集span並標示續接；表頭重複但不複製body選手。單幅不加技術座標欄。這是browser print，無新報表服務、Office或印表機操作。

本次 JSON 擴充不需要 migration，但舊 backend 的模型會忽略 title、且不接受 column_title，因此不能以資料表 revision 同為 0008 推定可無損退回舊 app。公開更新採新凍結 source／原 DB，保留 operation receipts、state token 與 session；舊分頁仍須遵守衝突核對與未知請求原 key 重試，不撤銷 session 或替使用者重建操作。接受新 JSON 後若遇問題，優先向前修復或限制受影響寫入；僅回前端亦須先核對功能相容，不能以備份覆寫更新後資料。

安全刪除布局的 delete_row／delete_column 亦屬 operation／receipt 契約擴充，雖然資料表仍為 0008，舊 backend 不認得新版 delete receipt，不能以 schema 相同作為回退依據。公開發布同批更新前後端，保留既有 request_id／receipt／session；若已有新版刪除或其他使用者操作，回退評估須以目前資料為準，不能還原發布前備份抹除操作。


### 刪除軸、範圍確認與顯示狀態

`delete_row`／`delete_column`採stable `axis_id`及strict boolean `confirmed_text`，透過既有mutate_grid的BEGIN IMMEDIATE、完整state_token與actor/payload idempotency、稽核同交易執行。固定級數欄、含registration的排、最後body排、不存在ID均拒絕。非空文字或自訂欄title需確認；不刪會員或報名。剩餘選手座標、級數、hard_level_snapshot與version保持原值。

刪軸先規劃所有受影響merge，再變更layout；剩餘為矩形則保留原merge ID及合法端點，單格則解除，無剩餘則移除。唯一非空文字在剩餘格時維持原座標；來源軸被刪但merge仍有剩餘時搬至新anchor（去除anchor空白text，避免重複address）。多段文字或含選手的歧義merge拒絕，不默默丟內容。

GridAxisMenu開啟時捕捉layout、token、axis ID，預覽及第二次確認使用同一範圍。對方改字後確認會409，不能沿用確認刪除新字。選單依viewport限制高度，內容獨立捲動、actions保持可達；dialog同樣處理多文字。未知操作鎖住原payload；receipt及新GET核對完成後，刪除不存在axis上的selected/end/editing及cell／column drafts。失败或未知未核對時保留輸入。

素食按鈕的pressed樣式只影響呈現；badge與淨差橘色並存，不改列印資料。歷史由sequence升序渲染，最新保存版標「最新」。版本清單獨立scroll容器，每次開啟／換場／非同步初載或目前安排新增保存版時捲底；重開時即使仍選取舊版也到底，但不改selected。保持開啟時切歷史與一般rerender不重設閱讀位置。不更動基準／淨差／完整快照語意。


### 明確拖曳意圖、灰階與歷次級數契約（2026-09-21）

新前端以卡片中央作 `swap(registration_id,target_registration_id)`，上下各22%作 `insert(registration_id,target,side=before|after)`；空格用 `move_empty(registration_id,target)`。同格切換有4px遲滯，穩定上下插入線／交換對象提示；release取React layout effect已提交到畫面的preview，不重算mouseup座標，也不使用尚未渲染的frame。來源25%及單一同尺寸ghost、click抑制、取消／失敗清理沿用。legacy `move`仍為插入，不由backend猜新client意圖。空格API拒絕占用；insert錨定stable行欄格與before/after，下方尋下一合法body格，跳過header／文字／merge，不動無關欄。swap直接交換兩個合法body級數格；self／實際無變更拒絕422且無receipt或稽核。

mutate_grid以操作前後所有registration座標比較，實際搬位者version各加1，跨級者competition_level及admin更新欄位同交易。跨級swap的兩個RegistrationAudit仍action=level，idempotency_key為SHA256({arrangement_request_id,registration_id})固定64字；changes中的arrangement_request_id用既有 `{before:null,after:原request_id}` 形狀，既有ActorAuditEntry可讀。整筆ArrangementOperation仍用原request_id、actor/payload fingerprint；receipt、兩人level/version/audit與布局/CompetitionAudit全成功或全回滾，重送先讀總receipt不交換第二次。會員level/hard snapshot不變。

`shade_row/shade_column(axis_id,shade)`僅允許strict integer 0..3；row含header/body，column僅自訂文字欄。LayoutRow/Column可省略shade，讀為0，前後端signature正規化0，還原色階可清淨差；GET不寫回舊JSON。顏色固定白／#ededed／#d9d9d9／#c4c4c4，交叉及merged涵蓋軸取max。無migration，歷史與receipt回應皆明確解析shade；舊backend會遺漏shade且不接受新operation，不能無損app-only回退。列印用底層SVG rect前景物件，不依賴CSS背景開關；內容黑字覆於其上，跨幅merged顏色仍按完整原merge計算。

新admin-only GET `/api/admin/competitions/{competition_id}/members/{member_id}/level-history`回明確四欄list：competition_id/name/date、competition_level；未知場次／會員404，無符合條件回空陣列。查詢精確member_id、registration.status=confirmed、competition.status=ended且未deleted、date<所選場且<=台北today，date DESC/id DESC取5。既有非取消列唯一索引排除取消重報舊列，不按姓名串接，不用member.level/hard_level_snapshot代替，也不視為實際出賽證明。不要求所選場目前仍有有效報名，以支援歷史快照中後來取消的人。

MemberLevelHistory獨立呈現即時參考；close/unmount或換人／換場會取消回寫舊promise，畫面只取當前key結果。詳情本場diet/level仍來自已檢視ArrangementRow，歷史快照唯讀不被live參考修改；historical prop才加短註「以下為目前查詢結果」。keyboard/mobile保留可達文字編輯與欄底移動，不新增帳號／公開資料／報表服務。


### 局部灰階與伺服器收據復原（2026-09-22）

`cell_shades` 是獨立於 cells 佔位的 stable row_id/column_id → strict 1..3 清單；缺少欄位與空陣列在 signature 相同，GET 不改舊 JSON bytes。`shade_cells(start,end,shade)` 允許 0..3，0 只移除 override；不提供白色 override。選區以矩形閉包反覆擴到完整相交 merge，前端高亮與後端一致。單格有效色為 local override 或原排／欄 max；merge 顯示所有底格有效色 max，merge/unmerge 保留底格設定。刪軸只 prune 該軸設定、不隨保字搬色；選手移動不搬色，空白著色不建立 text。列印沿 SVG 前景色保留 local 色，跨幅 merge 仍取完整原區域色階。

復原使用原 operations 入口與 `{action:"undo",target_request_id}`，不接受 client snapshot。成功操作在既有 receipt_json 加 private `_undo`（服務端 before_layout、parent_request_id、base_version_id），公開 GridReceipt 只加 optional state_token/undo_head；舊 receipt 缺 metadata 仍可重播但不能復原，不 migration。head 以 competition/actor、完整 state_token、workspace revision 精確匹配成功 receipt，不依 created_at 排序。undo target 必須是 head、同場同人同保存基準，服務端驗證恢復布局與當前正取名單後套用；version/revision 單調增加，跨級多人以 operation+registration 的 SHA256 稽核鍵同交易更新。undo 留新 receipt/稽核，head 指回 target.parent；連續 undo 不拿 target 舊 after-token 當目前 token，也不回寫舊版本號。新操作從當前 head 延伸，不提供 redo。

完整 token 包含名單／餐食／會員資料／場次狀態／保存基準／布局與 revision；外部更新或大保存會斷鏈，合法普通操作仍可開始新鏈。前端只保存本頁面已成功並讀回的 request-ID stack；receipt token 與新 GET 不符時清除可復原狀態，失敗不 pop，unknown 固定 payload 原樣重試。大保存確認後清 stack；歷史唯讀、terminal 與 input 原生 undo 邊界不放寬。

工具列常駐於表格前方，沒有選格時禁用相關按鈕；「表格底色」標籤與四個純色色票共框，白色在最左並保留清除／繼承語義，aria/title 提供可及名稱。成功上色保留不遮底色的選框，同一選區可連續換色；已按下的同色不發請求。詳情只在 pointerdown、pointerup 均落視窗外時關閉，避免內部拖選放手誤關。文字外點先提交並消耗該次點擊，待成功讀回才關閉；IME 不送出，失敗保留 per-cell 草稿，已有未決操作時允許返回表格核對。


### 表頭選格與請求等待修正（2026-09-22）

虛擬級數表頭保留 column ID/level，使用獨立 selectedHeader，不建立假 row/cell。單擊／Enter 選取、雙擊直接改字、工具列文字沿 `column_title`；選取 header 與 body 互斥，包含右鍵 body 切換，表頭不參與矩形範圍、merge/unmerge。多個畫面表頭對應同一 column 顯示設定。`shade_header(column_id,shade)` 接受 strict 0..3；optional `header_shade` 僅保存 strict 1..3，0 移除 override，回原 column.shade（missing 視 0），只影響 th／列印表頭，絕不擴散至 body。signature missing/null 等價、GET 不回寫舊 bytes；undo、保存、歷史沿原交易／快照機制。固定十級不能刪除，title 和 header_shade 不改語義級數。

安排專用 `arrangementRequest` 以 AbortController + 20 秒計時包住整個 `await request`，包含 fetch 與 JSON body 解碼。僅安排讀取／初始化／operation／完整保存／歷史版本請求使用，不變更其他 API。超時 throw 無 HTTP status 的明確錯誤，寫入由既有 controller 分類 unknown，保留 request_id/payload、整場寫入鎖及原樣重播入口；不自動重送、不假失敗／成功。已取得 receipt 而 GET 超時時保留 refresh/receipt，只重讀 GET；初次／一般 GET 超時清 loading 顯示讀取錯誤與重試。超時不表示伺服器停止執行，正確性仍由 BEGIN IMMEDIATE 與固定請求識別守護。

已證實的程式缺陷：前版裸 fetch／JSON 無界等待，合成 POST 實際 commit 後讓回應懸置，前版超過新期限仍 saving 且無確認入口。公開健康檢查正常但缺該次 mutation trace，不能將合成重現宣稱為使用者該次網路根因，也沒有據此歸咎 ngrok。


### 版本雙欄與選手點擊（2026-09-22）

CompetitionLevels 保留原 rows/baseline/layout 選版與捲動狀態邏輯，僅將差異拆成 arrangement-diff，DOM 順序表格、差異、版本；名稱為「該版本變動」「版本紀錄」。本頁 main 與相鄰比賽導覽上限 2200px，1700px 以上三欄、701–1699px 表格跨全寬且下方兩欄、700px 以下依序堆疊。表格維持內部水平捲動。寬桌面兩側區以 ResizeObserver 讀取表格外框高度與工具列造成的頂部偏移，單向寫入 CSS 變數，不用側欄撐高表格；標題／控制固定、內容 flex:1/min-height:0 獨立捲動。中尺寸及手機置於下方、最高60vh。只有存在 arrangement-main 的頁首白導覽與綠管理header共用2200px容器，切到報名設定及其他公共頁仍用原1240px。

LevelCardBoard 分開 selectPlayer/openDetail。姓名有效 click 立即選格，mouse dblclick 必須有同人兩次被接受的 click，touch 則同人 500ms 內兩次有效 tap 開資訊。drag 被抑制的尾端 click 不算有效，移動／取消清候選，姓名以外 pointerdown 清候選。range 終點保留 count=0 的短暫手勢記號，同序列第二擊既不縮選區也不開詳情。Enter 開資訊、Space 選格並 preventDefault；range 下兩鍵皆選取延伸。詳情移除選格按鈕，X／Esc／內外 pointer 邊界保持；歷史能查看資訊，寫入依原 readonly/blocked 守門。選區含 registration 時禁用合併，後端規則不變。兩個 gesture hooks、API、backend、schema 與依賴本輪皆未修改。

## 安排 Excel 匯出與列印格線（2026-09-22）

`arrangementExcel.ts` 靜態匯入 `write-excel-file@4.1.1/browser`，使用原生 cell、rowSpan/columnSpan、thin borders、wrap、灰階與合理行欄尺寸；正式相依只新增該套件及 fflate。CompetitionLevels 在已驗證且無未知操作／保存／讀取中的狀態下，複製完整 rows/layout 後產生下載；try/catch/finally 保證錯誤後解除匯出忙碌。沒有自訂 loader、動態載入重試或 Vite 擴充。

只輸出比賽標題、版本標籤及表格可見的姓名、辨識註記、餐食素標與自訂文字；不輸出 ID、會費、稽核等其他欄位。所有值明確使用 String 與 `@` 格式，`= + - @` 起始文字不轉公式；不產生 macro、外部連結或圖片。原生儲存格可離線修改，不新增匯入或資料庫寫入。歷史 rows/layout 使用所選保存版；layout=null 沿用既有級數／順位 fallback 並明示不代表原始分組，未知餐食不補現況。

官方套件契約：<https://github.com/catamphetamine/write-excel-file>，使用 browser `toFile`、String、columnSpan/rowSpan、backgroundColor、borderStyle、height、wrap；版本鎖定於 package-lock，npm audit 於本輪為零漏洞。

列印不一致的原因是前景 SVG 填色覆蓋 collapsed table border 邊緣像素。保留既有列印引擎與分幅，只將 `.print-cell-shade` 四側內縮 .25mm、寬高扣 .5mm，避免填色蓋住格線。代價約 1 CSS px 白色內緣；背景圖形關閉仍保留 SVG 灰階。獨立對照與實際產品 PDF 見驗收文件。

## 安排恢復狀態修正（2026-09-22 D）

20秒期限仍涵蓋transport與JSON body。小存成功回應先驗證request_id、competition_id、非負revision、與原payload逐欄相符的operation及layout必要結構；大存也驗證必要保存版結構。空回應、null、錯誤JSON/HTML、錯key或operation不符保持unknown原key/payload，不能只憑HTTP2xx進refresh。讀回資料先驗證根結構，失敗保留合法receipt以便只GET恢復。

人工recover按同場去重並暫停寫入，先bounded GET /auth/me核對本頁原帳號及非空CSRF再更新token；認證失敗或另一帳號不清pending，不自動登入或重播。成功後重讀當前pending：unknown原樣POST；refresh只GET安排；rejected才清操作並GET核對，草稿保留。unknown重試遇401/403繼續unknown；409/422等確定拒絕仍走rejected，避免未送達後token過期造成無限重試。後端先查同actor/key/payload receipt，再查state token，原子寫入及安全契約未變。

上方狀態優先顯示saving/loading/unknown/refresh/rejected，避免整場鎖住卻只顯示上次保存。恢復待辦存在時，讀取錯誤只顯示原因並沿用該待辦的明確確認按鈕，不另提供可能誤解成純GET的通用重讀入口。離頁保護仍在；session失效引導另一分頁以原帳號登入後回此頁確認。


同色 no-op 恢復：controller 僅對首次操作的 HTTP 422 且 detail 精確為「安排沒有變更」清除未寫入請求，再走既有 GET／版本核對。沒有 receipt、revision、audit 或 Undo 偽造；讀回成功才 verified，失敗仍鎖定且提供重新讀取。一般 422、409 及 unknown 重試不走此特例，原 request_id／payload、認證、衝突與不可降版檢查不變。相同 token 保留 Undo，其他頁異動仍斷鏈。後端與 schema 0008 未改。

## 格位共用操作選單、明確白色與表頭合併（2026-09-23 F）

本節是目前契約，修訂前文 2026-09-22 局部色與固定表頭章節中的歷史限制。`cell_shades` 以 stable row_id／column_id 存 0..3；0 是明確白色 override，缺少該格項目才沿用 row／column 有效色階。舊 JSON 的 missing／null／空集合仍可讀，GET 不回填；無 migration，資料表維持 0008。合併格的底格色仍逐格保存，顯示時依完整 merge 範圍取 max；明確白色格不被軸色重新染色。列印與 Excel 均輸出當前或所選歷史版的同一色階。

固定級數表頭是以 stable column ID／level 投影的虛擬列。optional `header_shade` 支援 0..3；0 明確白色，欄位缺少時沿用 column 色階，只畫在表頭與列印表頭。optional `header_merges` 用 start／end column ID 表示同一虛擬表頭列內的合併；它與 body 的 `merges` 分開保存，不能跨表頭、body 或自訂標題列合併。`merge_header`／`unmerge_header`／`header_text` 經既有 operation、state token、actor/payload receipt 與稽核流程執行；編輯合併標題不改固定十級身份或 stable 欄 ID。舊 backend 不保證保留新增的 JSON 欄位或辨識新 operation，因此 schema 同為 0008 不代表可無損退回舊 app。

表頭與 body 共用同一個格位操作選單，可在單一矩形選區內一併上色；不以假 row 寫入資料模型。merge 僅允許同一表頭／標題／body role，跨表頭、body 或自訂文字列會拒絕並在選單說明。桌面右鍵／ContextMenu／Shift+F10 與觸控原生按鈕 click 開啟選單，外部 pointerdown 或 Escape 關閉。觸控入口只在 click 開啟，避免同一 tap 的相容 click 命中新掛出的 portal 操作鈕。整張表格 Undo 位於獨立群組，僅依本頁已成功 receipt、目前 head/token/revision 與 server 保存前狀態發出既有 undo operation；它不接受任意 client snapshot，不回退版本號，也不等同文字欄原生復原。

ArrangementPrint 將 header_merges 映射成表頭 colspan；跨 12 欄分幅時只輸出本幅交集並加續接標記，不複製 body 選手。Excel 使用原生 header merge 與格位合併，明確白色填色保留為實際儲存格樣式。選單入口與列印裝置無關，驗收只使用瀏覽器下載／PDF，不操作實體印表機。

### 逐步重做與差異格位定位（2026-09-23 B 後續）

重做沿用 `/operations` 的 `{action:"redo"}`、固定 request ID、actor/payload receipt、state token、寫鎖及稽核交易。可重做佇列存於成功 receipt JSON 的私有 `_redo_stack`；每個項目只引用伺服器保存的 undo 前狀態與 parent receipt，不接受或重送 client snapshot／舊 operation。`operation_cursor` 在目前 competition、actor、token、layout revision 與 undo/redo head 下讀取游標；redo 只可套用佇列頂端，並核對保存基準、前序 receipt、目前名單及布局與伺服器快照相符。套用後以新 receipt、單調遞增的 revision／報名 version 與同交易稽核記錄結果。正常新操作清空 redo 分支；大保存及外部名單、角色、token、head 或 revision 改變會使前端鏈失效。未知寫入保留原 request ID/payload 原樣重試，收到 receipt 而讀回逾時則只 GET。只在本頁保存已確認堆疊；換場、保存、歷史唯讀、pending／locked 狀態不發編輯請求。快捷鍵為 Ctrl／Command+Z、Ctrl／Command+Shift+Z 及 Ctrl+Y；輸入欄、文字編輯、原生 dialog 與 IME 組字保留原生復原。改動只擴充既有 receipt JSON/API operation，schema 仍為 0008、無 migration；不支援新 redo operation 的舊 app 不保證相容。

目前安排的差異卡依 registration ID 比較來源與目標 stable row／column ID，卡片只高亮仍存在的實際端點，不建立矩形選區或寫回布局；新增、取消、移動、同級換位、跨級移動及交換皆可從卡片定位，鍵盤與觸控可啟用。舊快照無座標或軸已刪除時只定位可證實存在的端點，並說明缺失原因；換場、換版本及一般格位選取清除定位。卡片位於獨立捲動的「該版本變動」側欄，基準標題固定顯示相較版本；右側「版本紀錄」固定標題及「目前安排」控制，兩側各自捲動。僅 compact card 本身縮小間距，不改表格與側欄捲動行為。結構差異仍參與保存與淨差，移除泛用結構提示；純結構變更仍可保存且不顯示「沒有變更」。固定級數表頭及其按鈕 hover 使用 `cell` cursor。

大型保存只把目前 workspace 的完整布局附加為不可變版本快照，不執行新增、刪除或裁切布局列；row 的變更只由明確布局操作產生。大型保存後的尾端空列仍須依使用者回報另行觀察，不能在保存路徑以裁切或 fallback 隱藏。
