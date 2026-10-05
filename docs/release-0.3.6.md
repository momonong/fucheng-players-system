# 0.3.6：手機整張選手方塊拖曳

900px 以下的安排表可直接拖動整個選手方塊，姓名、辨識註記及方塊邊緣都能起拖，不必瞄準六點把手或等待長按。輕點選取、連點兩下開啟選手資訊，右上 ⋯ 獨立開啟操作選單；滑空白／文字格可捲表，拖到邊緣會自動捲動。

- 手指移動超過 6px 才建立拖曳預覽，避免剛按下就清掉雙點紀錄。移出再返回、取消、失去 capture 與第二指介入不算輕點。
- 中央交換、邊界插入、空格移動沿用既有已顯示預告與起拖 token；busy／unknown 整場鎖、原 payload 重試及版本衝突保護保留。
- 大於 900px 的桌面與較大觸控畫面保留原本樣式、姓名／把手拖曳、右鍵、雙擊和鍵盤。手機唯讀歷史及範圍選取不啟動拖曳。

## 驗證

本輪工程驗證共 18 項瀏覽器測試通過：根路徑桌面／手機 8 項，`/fucheng` 桌面 3 項、手機 7 項。包含整卡四邊／註記命中、雙點、7px 移出返回、取消、多指、900／901px 邊界、拖至第十欄、409、未知恢復、範圍選取及歷史唯讀。發布前全後端 211 passed（2 個既有棄用警告）、uv locked sync、Production build／TypeScript 與 npm high audit（0 vulnerabilities）通過，獨立唯讀審查無阻斷缺陷。詳細環境與證據見 [驗收紀錄](acceptance.md)。Chromium 觸控模擬不等於 Android／iPhone 或 Safari 真機手感驗收。

## 發布與部署

Python／npm 版本同步 0.3.6；後端、依賴與 schema 未變，無 migration。乾淨已提交來源經 allowlist staging 與 source manifest 建置 Linux/amd64 image，不含會員資料、秘密、備份或既有 dist。

先合併推送 GitHub，再發布 v0.3.6 及 Docker Hub `0.3.6`／`latest`，核對 registry digest 後更新既有 4090 `fucheng-home`。停寫時使用舊 runtime 備份 DB＋媒體並核對 hash；保留原 named volumes、帳密及舊映像，app／backup／ops 同批固定新 digest。實際發布／部署證據見 [家中部署紀錄](home-deployment.md)。

同一 image 仍以 runtime 設定根路徑或 `/fucheng/`；搬到球館 Windows Docker Desktop／WSL2 時，依場域設定 origin／入口並成組還原資料，不能只搬 image 就宣稱已搬妥資料。
