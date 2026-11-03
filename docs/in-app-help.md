# 站內使用說明與報名名單

新增公開 `/help`，沿用 runtime base path。導覽顯示使用說明，管理後台收進最右側三條線原生 details 選單，支援鍵盤、Escape 與點外關閉。

會員六步、管理員四步，每步搭配實際網站的合成資料截圖，可點開大圖。1.4.0 起圖片在 `frontend/src/assets/help/`，由 `helpImages.ts` 匯入，Vite 產生內容 hash 檔名，並與 Docker allowlist 一起打包。圖片不含真實會員、密碼、token 或認證資料。更新介面後應同步更新截圖並重新建置，不能直接替換已發布 hash URL 的內容。

首頁 NEWS 區塊首先顯示內建指南公告；這是程式內建提示，不建立或覆寫既有公告資料，也不假造發布時間。管理員原公告仍依原規則顯示。若日後需要管理員隱藏／修改此提示，應另外加入明確設定。

已接受的合成 localhost 預覽：`http://localhost:8078/` 與 `/help`。使用 ignored `data/help-preview/preview.db` 的合成會員與場次，正式服務與既有資料不變。示範帳密僅保存在 ignored 私有檔，不提供於說明頁。

預覽：`uv run --locked --offline --no-sync python data/help-preview/server.py`（目前執行中的本機示範腳本，不是正式部署入口）。驗證／截圖：從 frontend 執行 `node help-preview-verify.mjs`，使用已安裝 Chrome。預覽程序保留供使用者檢視。

會員截圖使用陳先生（老師）、陳先生（學生）、林小姐、蔡先生等虛構範例；同名會員透過辨識註記區分。首頁指南公告另含右上角使用說明按鈕的截圖。

## 公開報名名單

個人賽新增公開唯讀名單，僅回傳姓名、辨識註記、正取／候補狀態及順序；不回傳會員ID、餐食、級數、稽核或操作原因。沿用雙打的公開場次範圍（未刪除且 open／closed）；草稿、取消、已結束場次不擴大公開。舊 open-only 報名API與寫入守門保持原語意。新 `/api/public/registration-rosters` 提供可查看場次，`/api/public/competitions/{id}/registrations` 的 GET 提供個人賽名單，POST 沿用原報名流程。GET 使用明確唯讀快照，不補造安排／歷史。

公開頁報名成功會重讀名單與人數；1.4.0 起可見頁面約每五秒同步，切回視窗立即核對，也可按更新名單。背景分頁暫停輪詢；寫入結果未確定時保留原重試入口與內容。截止場次顯示名單並隱藏報名表，服務端仍驗證截止時間。取消的登記不公開。雙打保留等待搭檔／待確認／正取／候補。

發布驗證：完整後端587項、更新器31項、前端型別／建置與相關桌面／手機E2E通過。先前公開名單、原公開報名與雙打46項後端測試亦通過；既有Chrome已核對匿名正取候補、同名註記、報名後即時讀回、更新按鈕、手機寬度與截止唯讀畫面。全部為隔離合成資料，沒有正式報名或部署。

作者截圖工具 `frontend/help-preview-verify.mjs` 與 `roster-preview-verify.mjs` 依賴原本 ignored 的合成預覽資料與私有示範帳密，僅供該預覽環境重拍；乾淨 checkout 請執行 `frontend/e2e/help-roster.spec.ts`，不需這份本機檔案。
