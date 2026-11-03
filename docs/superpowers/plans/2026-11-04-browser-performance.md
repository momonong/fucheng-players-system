# Browser Performance 1.4.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for root application work; independent updater candidate is prepared separately and reviewed before integration.

**Goal:** 快取編譯資產、公開站內切頁、瀏覽器會員篩選及公開GET去重，同時保持5秒名單同步並安全交付球館升級。
**Architecture:** 現有React＋History API、在途公開GET去重／可見頁面更新hook；FastAPI及Worker僅對內容hash靜態資產允許快取。
**Tech Stack:** React19、TypeScript、Vite7、FastAPI、SQLite、Cloudflare Worker／Tunnel、Windows PowerShell5.1。
**Spec:** docs/performance-1.4.0.md

## Global Constraints
- 不新增migration或依賴；schema0015、runtime root／子路徑均維持。
- 不快取HTML／API／私人媒體；只有編譯hash資產可長期快取。
- 報名名單約5秒同步，寫入與收據守門不可弱化；背景不輪詢。
- 發布依本次授權，球館不由代理直接操作。所有驗證使用隔離合成資料。

## Review Focus
- 寫入後舊GET晚到，不可蓋掉新名單或重送POST。
- hidden／focus／長延遲請求不可疊加輪詢。
- modified click、hash及進出admin不可破壞既有導覽與寫入界線。
- 偽裝hash的API／錯誤／Set-Cookie回應不得快取。
- Windows既有1.3收據／manifest ID／無Health Tunnel／UNKNOWN／資料全表核對不可只用mock略過。

### Task 1: 資產快取
- [x] 加入失敗的Worker及FastAPI cache policy測試（有效hash、錯誤、Cookie、API、prefix）。
- [x] 建立 src/fucheng/static_cache.py 政策，接入app middleware及Worker，維持轉送守門。
- [x] 將合成說明PNG改為Vite資產imports，讓內容hash隨build產生，調整allowlist與authoring工具。
- [x] 跑focused測試、typecheck、真build資產標頭／cache驗證。

### Task 2: 導覽與讀取
- [x] 新增 frontend/e2e/performance.spec.ts，先釘住Document／GET計數與對外寫入更新。
- [x] frontend/src/navigation.ts 增加公開路徑History導覽及訂閱；App與SiteNav用同一路徑狀態。
- [x] frontend/src/publicReads.ts 共用公開在途GET，fresh讀取避開舊在途；API／會員頁移除重複資料載入並本機篩選。
- [x] frontend/src/useVisibleRefresh.ts 依可見／focus更新，個人／雙打使用5秒與序號守門；寫入後強制重讀。
- [x] 驗證local搜尋、上一頁、hash、admin、兩人名單同步、背景停止與慢回應／UNKNOWN；root與prefix桌機／手機。

### Task 3: 1.3→1.4球館更新器（獨立候選）
- [x] 以既有updater與真實已完成1.3收據形狀建立紅燈fixture。
- [x] 新script核對原1.2部署與已完成1.3鏈，新增1.4收據，保留所有舊收據與操作。
- [x] 停寫／備份／全表摘要不變／切recipe／私有驗證／再開Tunnel；COMPLETE只讀，UNKNOWN不重送。
- [x] 原生Windows未測明示；portable pwsh、真Docker模板、manifest／config識別、資料摘要測試。

### Task 4: 整合與發布
- [ ] 版本1.4.0、release／runbook文件，獨立code review並處理阻擋。
- [ ] 完整pytest、Worker、frontend typecheck/build/audit與相關E2E；allowlist候選image compatibility smoke。
- [ ] 明確暫存／提交／PR／expected-SHA合併及main快轉；正式clean來源重建／smoke。
- [ ] Docker 1.4.0及latest baseline-CAS發布、digest拉回核對、固定tag／Release。
- [ ] 同步府城Worker資產政策後核對公開靜態快取（保留原binding／網域／Tunnel，其他服務不動）；若缺必要權限交付明確限制。
- [ ] 交付固定來源SHA及映像digest的單段PowerShell；現場驗收仍待使用者執行。
