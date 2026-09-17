# 架構與資料模型

## 系統結構

瀏覽器與 FastAPI 使用同一 origin。React/Vite 只在開發或發布前建置；正式服務由 Uvicorn/FastAPI 提供 `src/fucheng/static` 成品與 `/api`。單一服務使用 SQLite，符合小型球館的可維護性與 2 GB RAM 驗證目標；沒有 Docker、Redis、Celery 或微服務。

公開首頁是硬實力分級名單，只呈現姓名、必要的辨識註記與級數，不常駐顯示葷素。公開 API 為了後續同源介面取用與相容性，仍只提供 `id`、姓名、辨識註記、級數與葷素；管理 API 才能讀取原會員編號、啟用狀態、版本與時間。ORM 物件不直接作為未限制的輸出。

## 一致性與安全

- `members.id` 是系統 UUID；姓名可重複，辨識註記獨立，原會員編號選填且有值時唯一。
- 級數的合法範圍是 1～10，畫面只依數字升冪呈現，不賦予強弱方向語意。
- 葷素為 `unset`、`omnivore`、`vegetarian`；確實未知時仍使用未設定。依球館目前名單語意，未標示素食者回填為葷食，新增會員也預設葷食。
- 停用會員仍留在資料庫與稽核歷史，公開名單只查 `is_active=true`。
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

每個新增、取消、遞補與餐食更新帶 8～64 字元的 idempotency key，`registration_audits.idempotency_key` 唯一。相同 key 重送回傳第一次結果；不同管理員同時遞補同一人時，第一筆完成後第二筆因版本／狀態不符而失敗，且不會順帶遞補下一位。

### 資料表

| 資料表 | 用途與關鍵約束 |
| --- | --- |
| `competitions` | 比賽設定、狀態、版本及下一個穩定順位 |
| `competition_audits` | 比賽設定前後值、操作者、理由與 UTC 時間 |
| `competition_registrations` | 會員關聯、正取／候補／取消、當次餐食、硬實力快照、順位與版本 |
| `registration_audits` | 每次報名操作、理由、操作者、UTC 時間及唯一 idempotency key |

管理介面固定顯示全場總數，另列篩選結果，避免搜尋後把局部筆數誤認為整場摘要。飲食姓名與管理列印只在登入後提供；沒有公開比賽名單 API。

會員自行報名／取消、免登入授權、拖曳軟分級、自動分隊及正式發布仍是後續工作。
