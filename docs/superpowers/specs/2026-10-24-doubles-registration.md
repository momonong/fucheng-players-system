# 雙打報名與組隊設計

狀態：使用者已確認「直接可以送出兩人組隊」，並授權討論後開始開發。本文補齊可逆實作細節；此次不包含發布或部署。

## 使用流程

建立比賽時選「個人報名／雙打組隊」。原有賽事與個人報名保持原樣。雙打提供「我先報名，等待搭檔」與「我們兩人一起報名」兩條路。等待搭檔名單公開，使用者可選其中一人、再選另一人，直接送出兩人組隊；也能一次選兩位尚未登記的會員。沿用免登入與代報，不新增邀請、帳號或驗證身分流程。畫面清楚提醒先與搭檔說好，送出後更正請找管理員。

每位會員同場最多一筆有效登記；以 member ID 識別，不能用姓名判斷重複。兩人組隊必須不同人。等待中的單人可以被新隊伍承接；已有隊伍的人不能被公開操作移走或重複報名。兩人的轉移與送出是單一交易，不能只成功一人。

單人為「等待搭檔」，兩人送出為「待管理員確認」。名額以隊計，等待搭檔與待確認不占正式名額。管理員按「接受報名」，有名額且沒有既有候補則整隊正取，否則整隊候補。正取取消不自動遞補；管理員明確遞補最早候補。管理員能新增登記、組隊、接受、取消、拆回兩位等待搭檔（再重新配對即更換搭檔），並查看操作紀錄。已結束／取消／刪除比賽禁止修改。

組隊條件為可設定「兩人級數合計至少 N 級」，預設 10，可不設。照片為 >= 10，包含剛好 10。級數採登記時會員級數快照；由等待名單組隊沿用原快照。規則不符仍可送出及接受，由管理員決定；以文字提醒，不假裝自動合格。修改規則不撤回已接受隊伍；長期會員級數不回寫。第一版不加入餐食、賽程、比分、抽籤或額外級數調整功能。

## 資料與 API 契約

- Competition 新增 `registration_mode`（`individual` 預設／`doubles`）及 nullable `doubles_min_total_level`（2–20）。建立後模式不可切換；舊 client 未傳模式的個人比賽行為不變，修改雙打不得因漏傳而降回個人。
- 獨立 doubles aggregate：entry（waiting_partner / pending / confirmed / waitlisted / cancelled）、entry members（序位、會員、級數快照、有效狀態）、audit、receipt。不要將雙打硬塞入 CompetitionRegistration 或安排表。active competition/member 唯一性由 DB 約束加寫鎖交易保護。狀態與有效成員數相符；取消/拆分/承接不刪歷史。
- 每次 mutation 同一 BEGIN IMMEDIATE 內驗證身分、賽事狀態、版本、名單歸屬，寫資料、audit、actor/payload-bound receipt 一起 commit。未知結果重試同 key/payload；receipt 在 challenge/現況衝突前讀取。取消或拆分 reason 必填。管理員其他晚報沿用 closed/deadline reason 規則。
- 公開 API 沿用 visitor cookie、CSRF、Origin、Turnstile、rate limit；新增公開名單 schema 只包含賽事及有效 entry ID/status/sequence、會員 ID/姓名/辨識註記、登記級數及合計/規則提醒。不得含帳號、餐食、legacy number、稽核、IP、visit 或內部備註。原 candidate API 仍不回級數。
- 僅公開 open/closed 且未刪除雙打賽事的名單；公開提交僅 open 且 deadline 未過。管理員可檢視其他狀態，寫入受上述生命週期限制。回執重送仍可查成功結果。
- 建議路徑：GET/POST `/api/public/competitions/{id}/doubles`；GET/POST `/api/admin/competitions/{id}/doubles`；POST `/api/admin/doubles/{entry_id}/{approve|promote|cancel|split}`；GET `/api/admin/competitions/{id}/doubles/history`。公開 POST `{member_ids:[id]或[id,id], request_id, turnstile_token?}`；管理員新增同 payload 加 reason。管理操作 `{version,request_id,reason?}`。最終明確 schema 由後端任務寫入介面文件供前端消費。
- 公開成功回應是不可變的提交回執，包含該次 entry 與清楚狀態；畫面再讀取最新名單，不把舊回執當現在狀態。等待單人被組隊時原登記以取消且稽核說明承接；快照傳給新隊伍。
- 新增 `doubles_summary`，不把隊數冒充原本 individual 人數統計；雙打 UI 明確顯示隊數與等待人數。單人 registration／arrangement 寫入必須拒絕 doubles，避免繞過兩人交易。
- 新 migration 0014，舊資料預設 individual；runtime 維護／備份規則不變，禁止升級真實 DB。新 schema 降版依既有匹配 image/schema 備份流程，不直接部署舊 image。

## 介面與驗收

沿用深綠、繁體中文、18px 報名文字及充裕按鈕間距，桌面與手機都能用。兩個報名選項清楚，表單只顯示需要的姓名選取；組隊顯示兩位姓名與辨識註記，不以級數條件阻止送出。等待名單有「和這位組隊」入口，送出前再次看見兩位姓名。隊伍列表區分待確認／正取／候補，不靠顏色單獨表達。無需修改既有會員表、會內賽表格或列印。

必須測：新建/舊資料相容、單人/兩人與兩位已等候組隊、不同公開訪客與管理端連動、同人重複與同名不同 ID、below/exact/above 門檻仍待確認、隊伍最後名額並發、同一人並發搶組與 rollback、actor/payload idempotency、version conflict、csrf/auth/截止/隱藏/刪除、名單隱私、拆隊/取消/候補遞補、member level 變更不改快照、原個人報名與格位回歸。前端有桌面及手機實際流程測試、root 與 /fucheng 路徑核對。所有資料合成。
