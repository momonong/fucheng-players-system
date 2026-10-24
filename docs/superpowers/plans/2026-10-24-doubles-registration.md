# 雙打報名開發計畫

**Goal:** 免登入單人等搭檔及兩人直接組隊，條件提醒、管理員審核，保持原個人賽連動。
**Architecture:** 既有 Competition 上新增不可變模式；獨立 doubles entry/member/audit/receipt aggregate，沿用 SQLite 寫鎖與既有安全邊界。
**Tech Stack:** FastAPI / SQLAlchemy / Alembic / SQLite / React / TypeScript / Playwright。
**Spec:** `docs/superpowers/specs/2026-10-24-doubles-registration.md`

## Global Constraints

- 使用者已授權開發與測試；不 commit、merge、push、發布、部署，不改真實資料或現用服務。
- 依 AGENTS.md 保留原個人流程、immutable level snapshot、交易/稽核、安全/CSRF、防重與 runtime/base-path 契約。沿用版面，不增加依賴或無關重構。
- 同一 checkout `feat/doubles-registration` 循序實作。後端與前端不得同時修改；獨立 reviewer 可唯讀。
- 由 Sol 6.1 Ultra 實作，root 負責決策及最後核對。實作者不要再派 subagent。
- 先寫有實際失敗證據的行為測試再實作。只使用合成會員，不從照片抄真名。所有 uv 使用既有鎖與本機 cache，不讀 data 下敏感檔案。
- 隔離 E2E 使用新增 `data/doubles-registration-e2e.db`、`frontend/dist-doubles-e2e`、127.0.0.1:8057；使用前核對未被占用，不覆寫既有 dist/DB。人工預覽另用未存在 DB/port/static，root 再決定。
- 不變更1.0.0版號或宣稱已上線；此次含0014migration，需要後續授權發布部署。

## Review Focus

兩人原子性、同會員唯一有效登記、容量以隊、等待承接快照、admin review非自動正取、併發與 receipt actor/payload、封閉公開 schema、visitor 保留與 FK、舊個人/grid API 不可繞過 mode、模式修改相容性、migration與runtime維護契約、前端未知寫入不換 key。

### Task 1: 雙打後端與連動測試

**Files:** models/schemas、新 `src/fucheng/doubles.py`、`public_registration.py`、`registrations.py`、`app.py`、必要 arrangement guard、migration0014、`tests/test_doubles.py` 與必要相容測試、`docs/doubles-registration-api.md`。

- [ ] 先讀 Spec、現有模型/交易及 auth dependency；跑未改動 backend suite，記錄 baseline。保留本次 task 邊界不做前端。
- [ ] 寫 failing tests：雙打型別與隊名額；單人等待；兩人原子 pending；既有單人被承接；不符/等於門檻可送出。落實 Spec 的模型、migration、明確 input/output schema。
- [ ] 公開及管理 routes 按 Spec：公開 GET/POST `/api/public/competitions/{id}/doubles`；管理 GET/POST `/api/admin/competitions/{id}/doubles`；POST `/api/admin/doubles/{entry_id}/{approve|promote|cancel|split}`；GET `/api/admin/competitions/{id}/doubles/history`。處理原流程 mode guard、CompetitionSummary 不混單位、mode在更新不可改、容量調整不可少於正取隊數。
- [ ] 公開身分、CSRF、Origin、Turnstile、rate-limit 可重用，不能另開免保護寫入口；補 visitor cleanup 保留 references。pending/confirmed/waitlisted 用不同文字狀態。
- [ ] 用實際服務層/API 測試最後一隊名額、重複member並發、交易 rollback、stale version、same actor/payload retry與不同actor/payload衝突、取消/拆回等待/候補遞補、晚報與lifecycle、level snapshot與舊grid隔離、public schema、migration既有資料。
- [ ] 跑完整backend pytest，以獨立 .test-tmp-doubles-backend 與 local cache；所有失敗如實列出。寫 API 文件：精確 payload/response、狀態/錯誤與畫面需求，供 Task2 接續。
- [ ] report 應列變更路徑、baseline/red/green命令與數量、未解風險；禁止提交或部署。

### Task 2: 雙打報名與管理介面

**Files:** `frontend/src/types.ts`、`api.ts`、`PublicRegistrationPortal.tsx`、`CompetitionManager.tsx`、`ClubWebsite.tsx` 的比賽入口與報名文案、必要新 Doubles 元件、`styles.css`；`frontend/e2e/doubles-registration.spec.ts`、`scripts/run_e2e_server.py` 只增加新測試 DB allowlist、`.gitignore` 排除新合成 build；`docs/doubles-registration.md`。

- [ ] 先讀 Spec 與 Task1 `docs/doubles-registration-api.md`，依後端最終契約實作，不重複自訂API。檢查 baseline typecheck。先以 failing E2E 表達核心流程。
- [ ] 比賽新增模式選擇、雙打隊數及可選級數合計門檻；編輯模式只讀。現有比賽不改視覺/行為。
- [ ] 公開表單兩個入口：「我先報名，等待搭檔」「我們兩人一起報名」；姓名/辨識註記選擇、先與搭檔說好提示、明確 loading/error/success、18px。名單區 waiting / pending / confirmed / waitlisted，waiting入口「和這位組隊」將該會員帶入兩人表單。不可公開拆換已成隊者。沿用session、CSRF、Turnstile、安全basepath。寫入未知結果保留 key/payload，防重且不默默發新請求。
- [ ] 首頁時程依 registration_mode 對 open/closed doubles 提供名單入口；直接 /register/{id} 在雙打截止後讀取 doubles roster，不依開放報名列表判定整頁不存在，表單隱藏且名單可讀。首頁報名說明不要寫成所有比賽都要選餐食。
- [ ] 雙打管理取代個人grid區塊：名單、隊數統計、級數提醒、接受、候補遞補、取消、拆隊與重新組隊、操作紀錄。版本衝突更新提示而非覆寫；read-only 狀態無寫入；晚報/取消/拆分原因按後端契約。純候補與待確認須明確不同。
- [ ] 真實E2E桌面/mobile驗證：建立雙打→公開單人→另一公開訪客選他並組隊→管理看見pending/門檻提醒→接受→公開看見confirmed；兩人直接送出且不符仍可審核；重複同人錯誤；取消/拆隊/候補。保留原個人registration-linkage E2E回歸。
- [ ] typecheck/build與適當E2E；同新artifact root及/fucheng兩種路徑；看桌面/手機screenshots，無水平溢出、雙人核對清楚、中文可讀。不重建現用成品。
- [ ] 更新功能文件及 migration 升級提醒；report附精確驗證證據、screenshots路徑、未解事項，不提交不部署。

### Task 3: 整合核對與交付

**Files:** 唯讀審查全diff；必要修正交回相應實作者，補驗證報告到 docs。

- [ ] root 直接核對 API/DB/安全/併發與UI證據，不只採信agent宣告。獨立reviewer對Spec審查整體，修正實際缺陷。
- [ ] 確認 backend完整suite、frontend typecheck/build及核心E2E證據同版；有新修正只補受影響檢查；原有失敗不隱瞞。
- [ ] 交付清楚繁中摘要，明示開發狀態、測試、未部署；若可安全提供可渲染本地/既有授權預覽則核對通道，否則先附已核對畫面，不擅自公開會員/憑證或部署正式站。
