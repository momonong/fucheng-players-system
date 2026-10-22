# 0.4.3：球館健檢回傳與報名連動回歸

Windows 一鍵健檢工具先保存本機 `report.json`／`report.md`，再以獨立裝置憑證呼叫 `POST /api/deployment-reports/{report_id}`。斷線或回應不明時保留原 UUID、原內容與原位置重試；同一份報告重送回傳原收據，不新增報告。管理員可依既有 session 列表及下載，裝置憑證只允許新增報告。原手動上傳畫面維持原用法，沒有新增報告管理 UI。

接收功能預設關閉。啟用時需另行配置受保護 token 檔與 `compose.report-upload.yaml`；API 跟隨 runtime 根路徑或 `/fucheng`，沿用既有 HTTPS／Origin／管理認證。回傳收據只證明伺服器保存成功，不代表健檢通過或已驗證實體主機身份。使用、固定 UUID 重試與打包方式見[回傳手冊](host-report-upload.md)。

新增 schema `0012_device_reports`，只增加報告表、索引與禁止更新／刪除的 triggers。從0011升級仍須先停寫、成組備份，再透過 runtime guard 顯式 migration；serve 不自動遷移。既有資料庫已在0012時，仍須依既有部署流程核對 schema。舊版0.4.2／0011映像不能直接啟動0012資料，回復須配對映像與既有備份並還原到新目標，保留故障庫。完整步驟見[部署手冊](deployment.md)及[家中部署紀錄](home-deployment.md)。

公開報名、管理報名與當次安排繼續共用交易及資料；新增四項後端永久 regression，以及沿用正式 Playwright harness 的雙身分連動測試。已開啟的管理頁沒有自動刷新，需按「報名與設定」「排級數」或重新載入讀回；取消正取不會自動遞補，管理員須依候補順序確認遞補。驗證範圍及舊測試限制見[報名連動驗證](registration-linkage-verification-20261022.md)。[公開使用指南](https://momonong.me/slides/fucheng/)已上線。

Python／npm 自身版本同步為0.4.3；沒有依賴升級，也沒有修改報名或前端產品行為。

## 工程證據與交付界線（2026-10-22）

- Linux後端完整回歸（獨立傳輸測試另列）：**273 passed**、77.93秒，兩項既有 Starlette／anyio deprecation warnings。涵蓋新增四情境、接收 API、schema保留及原有功能。
- `uv lock --check --offline`、前端 typecheck／獨立 production build通過。正式新E2E使用本次獨立成品及全新合成DB，根路徑與`/fucheng`各桌面／手機，**4/4通過**；兩路徑各2 passed、9.1／9.0秒，8088／8089均已停止監聽。
- 六項實際portable PowerShell 7.6.6／Linux TLS fixture證據重用；相關18份核心檔案與先前freeze完全相同。新build三份資產SHA-256也逐一與先前四組實測成品相同，未將歷史案例重複加總。比對記於 ignored `data/release-0.4.3/evidence-reuse.json`。
- `uv.lock`與npm lock除自身版本外逐欄完全相同；先前80檔部署來源中，排除四份版本metadata，其餘76檔逐一SHA-256相同。沒有重建現用static或操作正式資料。
- 沿用同依賴lock的0.4.2 `npm audit --audit-level=high`證據，**0 vulnerabilities**；已與該發布commit逐欄比較lock，只差自身版本，收據為`data/release-0.4.3/npm-audit-reuse.json`。本次沒有另執行線上audit。

截至本次來源準備，0.4.3的Git合併／推送／tag／Release、registry映像發布及正式服務切換由目標負責者接續驗證；本頁的工程證據不代表上述操作已完成。先前已啟用的健檢接收站仍屬[未提交snapshot部署紀錄](host-report-home-deployment-20261022.md)，不可當作0.4.3發布身份。

Windows PowerShell 5.1／Docker Desktop真實主機、雙擊CMD、球館網路、真正Turnstile報名、實體手機、原生系統列印、斷電／重開機與人工接受仍待現場驗證。Linux合成證據不代替上述驗收。
