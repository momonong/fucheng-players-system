# 0.4.0：管理員帳號、姓名與首次啟動

本版交付管理員管理與全新部署首位帳號設定。版本標籤與 registry digest 以 [GitHub 發布頁](https://github.com/momonong/fucheng-players-system/releases/tag/v0.4.0) 的實際發布紀錄為準。本版尚未部署到球館，也未更新家中既有服務。

## 使用行為

- 所有啟用管理員權限相同，可登入後新增管理員、停用／啟用、重設他人密碼、變更本人密碼及查看操作紀錄。登入帳號建立後固定，姓名選填；舊帳號保持未知姓名並以帳號顯示。
- 新增與重設使用暫時密碼，首次登入必須先更換；敏感操作需要本人現密碼、session 與 CSRF。停用或改密碼撤銷該帳號所有 sessions，禁止停用自己及最後一位啟用管理員。
- 完整操作與稽核同交易，採 version 衝突核對；密碼及 hash 不進入回應或稽核。DBAPI 寫入／提交失敗會清理連線，Web、CLI 與 bootstrap 的錯誤不輸出秘密 SQL 參數。
- 管理員姓名與登入帳號、ID 分開。會員分級、報名時級數快照、安排與歷史資料的既有資料契約保持相容。

## 全新球館與升級

schema 升至 `0011_admin_management`；新增管理員姓名、帳號版本、首次改密碼標記及操作紀錄。舊帳號、驗證資料、sessions 與歷史原值保留，遷移不補造建立紀錄。Start 不自動初始化或 migration；既有部署要先停寫、用舊版成組備份，再明確 migrate。回退使用匹配 image／schema 的備份在新目標還原，保留故障資料。

球館首次設定範例 `club.env.example` 僅指定姓名「陳鎮濃」、帳號 `momonong`。可在 Windows Start 前使用互動式 Admin 私密設定首組密碼；或使用受保護檔案 bootstrap，在監聽前建立首組帳號。沒有固定密碼或明文密碼環境變數，未設定時拒絕服務。bootstrap 只有在管理員表完全空時作用；任何既有帳號都會讓它跳過，重啟、改設定及還原不覆寫帳密。

首組本人自設密碼可直接使用；後續新增／重設仍須首次更換。詳細步驟見[部署手冊](deployment.md#球館首次部署陳鎮濃momonong)。本輪不執行球館或家中服務變更。

## 版本與驗證

Python／npm 版本同步為 0.4.0；既有 transitive `source-map-js` 最小修補至 1.2.2。沿用 uv 與 npm 鎖檔，不升級其他依賴。發布前完成完整後端、typecheck／build／audit、根路徑與 `/fucheng` 桌面／手機合成 E2E。實際輸出與發布 image 的來源、digest／manifest 核對由交付階段保存；工程驗證不代表球館實機或人工接受。


已完成本版實際驗證：完整後端 **257 passed**（68.04 秒，2 個既有棄用警告）；npm ci、typecheck、build 與 audit 通過，漏洞 0；根路徑與 `/fucheng` 各桌面／手機 E2E 共 **4/4 通過**。本版使用獨立合成資料庫與 `dist-admin-management-040` 成品。私密提示無法隱藏輸入時會直接拒絕，不退回明文回顯；原生 Windows Docker Desktop 與球館實機操作仍待部署窗口驗證。

## 發布映像驗證

正式建置來自乾淨提交 `57a4fe367a871334cf4dc52e73272a7f23dedc82`，source manifest SHA-256 為 `71cc92a0a535037a9348afc343e4fda6ec9155224460f090a3e3631b11fa6138`，image ID 為 `sha256:bf9126c1d3302474a639999b8987648aa4c813e97edbc22cdc2c0f3f2f37cfe8`，平台 `linux/amd64`。後續整合更新部署文件、Compose 非秘密錯誤提示及來源清單；交付時再次核對 manifest 中全部原始碼 hash 相同。

78 個 allowlist context 檔案核對通過；image 內 manifest、HTML、JS、CSS 與已測成品逐位元一致。同一 image 於根路徑、`/fucheng` 分別驗證空表初始化、缺設定拒啟、姓名與唯一首位帳號／稽核、登入登出與 Cookie Path、改密碼檔重啟不覆寫、既有帳號不再需要 bootstrap secret。兩者皆為 schema 0011、integrity `ok`、foreign-key 錯誤 0。真實容器 PTY 驗證 CLI 私密提示及已有帳號拒絕首設，未回顯秘密。

合成測試使用獨立 named volumes、network `none`、無 host port，測試容器已停止；既有服務未變更。GitHub 未設 CI workflow，以上為本機與獨立容器的工程驗證，原生 Windows 與球館實機待後續確認。
