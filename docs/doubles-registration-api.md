# 雙打報名 API

本文件為前後端共同契約。路徑使用既有 runtime base path；以下省略 `/fucheng`。所有範例為合成資料。

## 比賽

建立 Competition 新增 `registration_mode: "individual" | "doubles"`（省略為 individual）、`doubles_min_total_level: 2..20 | null`（雙打省略預設 10；null 不設門檻）。模式建立後不可更改。更新省略模式／門檻時保留原值，明確 null 門檻為取消規則。雙打 capacity 單位為隊，等待搭檔／待確認不占名額。

`GET /api/public/schedule` 的 ScheduleItem 新增 `registration_mode`，供首頁對 open/closed 雙打連至名單；其餘欄位維持原樣。

所有 AdminCompetition / PublicCompetition 新增上述兩欄及 `doubles_summary: DoublesSummary | null`。PublicCompetition 新增 `effective_registration_open: boolean`。個人賽 doubles_summary=null；原 summary 僅個人報名，雙打 summary 的人數/remaining 都為零。

DoublesSummary = `{waiting_partner, pending, confirmed, waitlisted, cancelled, remaining, pending_promotions}`，整數；waiting_partner 為等搭檔人數，其他狀態為隊伍數（cancelled 包含取消的單人登記）。remaining=capacity-confirmed；取消不自動遞補。

## 明確回應型別

PublicDoublesMember = `{member_id:string, name:string, distinguishing_note:string|null, level_snapshot:number}`。

PublicDoublesEntry = `{id:string, status:"waiting_partner"|"pending"|"confirmed"|"waitlisted"|"cancelled", sequence:number, members:PublicDoublesMember[], total_level:number|null, min_total_level:number|null, meets_level_rule:boolean|null}`。

`members` 依送出次序排列，級數為登記快照。單人 total_level/meets_level_rule 均 null；完整兩人有 total_level，無門檻時 meets_level_rule=null。低於門檻也能提交、接受。狀態文字：等待搭檔／待管理員確認／正取／候補／已取消。

AdminDoublesEntry = PublicDoublesEntry 加 `{version:number, created_at:ISO8601, updated_at:ISO8601}`。

## 路由

- `GET /api/public/competitions/{id}/doubles` → `{competition:PublicCompetition, entries:PublicDoublesEntry[]}`。僅未刪除 open/closed 雙打可讀，deadline 已過仍可讀；entries 僅有效登記且依 sequence 排序。以 effective_registration_open 決定是否可送出。
- `POST /api/public/competitions/{id}/doubles` → 201 `{entry:PublicDoublesEntry}`。body `{member_ids:[id]或[id,id], request_id:string, turnstile_token?:string|null}`。不接受 reason/diet/status/level 等額外欄位。沿用 registration-session visitor cookie、`X-CSRF-Token`、Origin、Turnstile、速率限制。只限 open 且未截止。成功回執不可變；之後另 GET 讀現況。
- `GET /api/admin/competitions/{id}/doubles` → `{competition:AdminCompetition, entries:AdminDoublesEntry[]}`，包含取消歷史，所有賽事狀態可讀。
- `POST /api/admin/competitions/{id}/doubles` → 201 AdminDoublesEntry。body `{member_ids:[id]或[id,id],request_id:string,reason?:string|null}`；建立單人為 waiting_partner，兩人為 pending；不是直接接受。
- `POST /api/admin/doubles/{entry_id}/approve` → `{entry:AdminDoublesEntry, waiting_entries:[]}`，body `{version:number,request_id:string,reason?:string|null}`。只有 pending 能接受；有隊名額且無既有候補為 confirmed，否則 waitlisted。
- `POST /api/admin/doubles/{entry_id}/promote` → 同上。只能遞補最早有效候補且須有隊名額。
- `POST /api/admin/doubles/{entry_id}/cancel` → 同上。reason 必填（任何時間）；取消隊伍不自動遞補。
- `POST /api/admin/doubles/{entry_id}/split` → `{entry:AdminDoublesEntry, waiting_entries:AdminDoublesEntry[2]}`。reason 必填；原完整隊伍取消，兩位以原級數快照新增 waiting_partner。
- `GET /api/admin/competitions/{id}/doubles/history` → audit array：`{id,entry_id,action,actor_kind,actor_name,reason,changes,created_at}`；依時間新到舊。action 包含 create/absorbed/approve/promote/cancel/split/waiting_from_split。

管理寫入沿用登入 session/CSRF。closed／已截止操作 reason 必填。draft/ended/cancelled/deleted 禁止新增與管理動作。每次操作 request_id 8–64 字元，version >=1；member_ids 1–2 個不同且啟用會員 ID。重試必須固定原 key／payload；回執在挑戰或現況檢查前讀取，且綁 actor／目標／動作／payload。

## 衝突與畫面

HTTP 401 登入或訪客逾時，403 CSRF／Origin，404 不公開／不存在，409 已變更、重複會員、名額／候補順序／生命週期／key衝突，422 payload／原因缺漏，429 次數限制。寫入逾時保留原 key／payload 標 unknown；成功後重讀名單，讀回失敗只重讀。以 member ID 識別，同名不同 ID 可組隊；公開選名不證明本人。顯示兩人確認及「先與搭檔說好，更正請洽管理員」。單人被組隊時原單人取消並留 absorbed 稽核，新隊伍承接快照。選已在有效隊伍中的人需 409，整組原子拒絕。

第一版不提供餐食／會員級數修改／安排表；原個人報名及安排表寫入口拒絕雙打。migration 0014，舊資料維持 individual；僅用獨立合成測試 DB，不升級真實 DB。降版沿既有匹配 image/schema 備份流程。
