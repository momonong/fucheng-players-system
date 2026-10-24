# 1.1.0：雙打報名與管理

新增雙打組隊報名，讓會員單人等搭檔或兩人一起登記，再由管理員接受及管理隊伍。原個人賽、餐食與級數安排流程保留。這是功能版本升級；專案自身版本由 1.0.0 提升為 1.1.0，依賴版本不變。

## 功能範圍

- 建立比賽可選個人報名或雙打組隊；模式建立後固定，雙打名額以隊計。兩人登記級數合計門檻可設 2–20 級，預設 10，也可不設門檻；低於門檻仍可報名及由管理員接受，畫面提供提醒。
- 公開頁提供單人等待、直接兩人及從等待名單組隊；送出前核對兩位姓名與辨識註記。同名會員以 member ID 識別，等待者組隊承接原登記級數快照。
- 管理端依等待搭檔、待確認、正取、候補與已取消顯示，支援新增、接受、依序遞補、取消及拆隊。取消不自動遞補；取消、拆隊及截止後操作保留原因與稽核。
- 未知寫入保留原請求編號與業務內容；成功回執後讀回失敗只重讀。管理版本衝突讀回後保留該登記／操作的原因草稿，需由人再次明確提交。

雙打第一版不提供餐食、安排表、額外調級、賽程、比分或抽籤。選名不證明本人，更正由管理員處理。使用方式與 API 見[雙打使用說明](doubles-registration.md)及[API 契約](doubles-registration-api.md)。

## 相容與資料保護

新增 Alembic `0014_doubles_registration`，接續 `0013_announcement_deletion`。舊比賽維持 `individual`，新門檻欄位為 null，不轉換舊報名、不回寫會員級數；既有個人安排 layout JSON schema 2 不變。前後端與 app／backup／ops image 須同批更新，同一 image 繼續支援根路徑與 `/fucheng/`。

既有部署須先停寫、以原 runtime 成組備份 DB＋媒體並核對 hash，再由新版 runtime 經 lifecycle lock／maintenance guard 顯式 migrate。Start 不 migration；不在真實資料新增測試會員、雙打場次或報名。`0014` 禁止直接 downgrade，不能只切回舊 image；回退須保留故障庫，以升級前備份還原至新目標並搭配匹配 image／schema。詳見[部署升級注意](deployment.md#110-雙打報名與-schema-0014)。

## 已取得的工程證據

- 後端：326 passed、6 項既有 PowerShell runtime skips、2 項既有 deprecation warnings；包含 migration、既有欄位保留、容量及並發、原子交易、快照、權限、receipt／version 衝突、公開隱私及原個人流程。
- 實際瀏覽器：根路徑與 `/fucheng` 的桌面／手機雙打核心各 10 項通過，原個人 linkage 各 2 項通過；桌面／手機公開兩人核對與管理正取／候補畫面已檢視。根路徑最初合併 run 的 legacy mobile 曾被既有 IP 讀取限流阻擋，保留原失敗紀錄後，以隔離 run 補驗通過，未放寬正式限流。
- 恢復邊界修正：root／prefix 受影響案例各 10 項通過；最後 challenge 422／503 分支校正後各 4 項通過。覆蓋提交成功但回應遺失、後續 403／429／404 仍保留原請求、receipt 後只 GET、Turnstile token 重驗及管理原因草稿。
- 後端獨立審查及最終整合 scoped re-review 均 PASS；本次版本 metadata 的離線 lock／sync、前端 typecheck、獨立 build 與依賴未變核對，結果記於本輪 `release-110-prep.md`。

上述為本機隔離合成資料的工程證據；未因版本調整重跑完整後端或全套 E2E。完整原始報告及 log 保留在 ignored `.superpowers/sdd/2026-10-24-doubles-registration/`，不納入映像來源。

## 發布、部署與驗收狀態

截至本文件準備時，Git 合併／推送、版本發布、正式映像建置／推送及網站部署尚待執行；此文件不代表現站已更新。正式映像應由固定 commit 經既有 allowlist staging 與 source manifest 建置，禁止納入 data、帳密、備份或既有 dist。實際版本、digest、schema、資料保留與 HTTPS 核對結果須在執行後記入[家中部署紀錄](home-deployment.md)。

外部真實 Turnstile 尚未連線驗證；受控 widget／HTTP 錯誤測試不等同外部服務驗收。未確認請求僅保留在本頁記憶體，關閉或重新整理前須由管理員核對結果。使用者網站試用、球館 Windows、實體手機／印表機及斷電／重開機仍待人工驗收。
