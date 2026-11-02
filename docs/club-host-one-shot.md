# 球館 Windows 貼上即跑健檢

> 2026-11-03：本文件保留歷史檢查／回傳流程。4090 接收站已停用，原固定 SHA 下載
> 與回傳不再提供；已保存的 JSON／UUID／收據保留，球館運行不依賴接收站。
> 目前部署見[球館維運指南](club-deployment-runbook.md)。重新打包的工具識別會改變，
> 不可把舊凍結入口當成任何新版 receiver 都能直接使用的通用網址。

在球館開啟管理者提供的 HTTPS 說明頁，把完整無秘密啟動碼貼到**原生 Windows PowerShell 5.1 或更新版**。不用 AnyDesk 傳資料夾、不用安裝 Python／Git、不需管理員權限，也不永久修改 ExecutionPolicy（工具執行只在短命子程序以 `-ExecutionPolicy Bypass` 進行，不變更 User／Machine／GPO 或目前視窗政策）。說明頁可從 `momonong.me/html-preview` 的已授權預覽連結開啟；啟動碼必須與本次 snapshot 的 download manifest 相符。

工具依序下載固定 URL 的 bootstrap、核對 SHA256，再下載工具 ZIP、核對 SHA256 與每檔 manifest。所有 HTTP 都要求正常 TLS、不跟隨重新導向，下載／登入／回傳有大小與時間限制。ZIP 拒絕跳出路徑、重複名稱、連結及不符 manifest 的檔案，全部驗證後才解壓。公開 ZIP 只有 allowlist 工具、範例設定和說明，沒有密碼、token、會員資料或資料庫；bootstrap 在 ZIP 外，沒有自我 hash 循環。

工具先保存報告及固定 `upload-operation.json`，再於目前終端依序輸入帳號與隱藏密碼（`Read-Host -AsSecureString`），不使用 GUI 認證視窗。請輸入 **momonong.me/fucheng 接收站的既有管理員帳號及密碼**，不是球館 localhost 的管理員，也不是 Windows 帳號。工具不讀瀏覽器 Cookie、不需要手動取得或貼上 token。登入及取得權限最多等待 150 秒；帳號／密碼留空、取消或逾時保留報告，下次貼同一段指令接續。管理員若被要求先改密碼，須先在接收站正常登入並完成改密碼。

登入使用獨立記憶體 session，通過 CSRF 後只取得**這個裝置／這份 UUID 專用的一小時回傳憑證**；簽發後嘗試登出，登出未確認時會明說。密碼與 session 不寫檔、不放命令列、不顯示回應內容。失敗只顯示 `config`／`operation`／`username`／`password`／`login`／`capability`／`token_write` 階段及例外類型，不顯示例外訊息或 HTTP body。短效 token 僅寫入本人、SYSTEM、Administrators 可讀的工具私密目錄；新工具來源中的暫存 token 使用後移除。原長效裝置秘密只留在接收站，不回傳給使用者。短效 token 不能讀會員／報告、不能管理寫入；過期、帳號停用、改密碼／版本變更或要求改密碼後失效。

工具下載工作區位於目前使用者 LocalApplicationData 的 `FuchengClubDownloads`，報告與原 operation 位於 `FuchengClubHostCheck/data/host-...`。工具只重用 marker 相符的自有目錄；拒絕 reparse point，並使用互斥檔鎖避免同時執行。不變更其他目錄 ACL。每次下載解壓到新的執行子目錄，避免覆寫既有工具。

健檢總時限四分鐘，每十秒顯示仍在執行。只查詢 Windows／Docker，以及核准的外部連線與報告回傳；不重開機、不安裝或更新軟體、不修改電源／服務／防火牆、不啟動或重啟容器、不讀寫 volume。逾時只依本工具追蹤的 PID 停止自己的程序樹，不按名稱停止其他程序；清理未確認時會明說。指定檢查 `fucheng-check-v120`，固定 image digest `sha256:0e5a297b0d16876fa56e1b9bed0470c3b8632d55ded6b23ffc5c18315f39e6e2`，本機 health 使用 `127.0.0.1:8052/api/health`，這不代表外部 HTTPS 或冷開機驗收。

`https://momonong.me/fucheng` 現階段只供工具下載及接收報告；球館正式網站使用球館自行持有的網域，另行規劃部署。現有 `fucheng-check-v120_data` 是合成試用資料，不可轉作正式資料。

有 FAIL 仍會回傳。成功顯示可安全回覆的 `report_id` 及 `upload-receipt.json` 位置。一般重跑沿用原報告／UUID；已有合法收據時不再登入或傳送。斷網、逾時結果未知、短效權限到期時，保留原檔並重貼同一段指令，必要時重新登入取得同一 UUID 的新權限；不會因 renew 重新產生報告。409／收據損壞請保留現場交管理者核對。完整報告產生前中斷留下不完整目錄時，同樣保留現場，不上傳半份報告。

舊私密 ready 資料夾／`RUN-CHECK.cmd` 仍相容。只有明確需要新檢查時才使用既有 `NEW-CHECK.cmd`，它先驗證前次收據與原報告／operation；未接收或損壞時不得放棄原 UUID。舊長效 token 不應再公開傳送，下載流程不需要該檔案。

結束碼：0=已接收／沿用收據（PrepareOnly 時僅表示本機準備完成）；2=下載、設定、登入或檢查失敗；3=接收站拒收；4=結果未知，同份重試；5=健檢達時限。收據只證明報告已保存，不等於檢查通過、正式部署或人工接受。

## 管理者建置與接入

```text
uv run --locked --no-sync python scripts/club_host_one_shot_package.py --download data/<fresh-output>
```

輸出 `tools.zip`、`bootstrap.ps1`、無秘密 `launcher.ps1`、`download-manifest.json`。啟動碼採 launcher 完整內容，不能僅依 URL 執行未核對腳本。固定 URL 由兩個 body SHA 決定，變更任何工具／說明後都必須重建並更新說明頁。ZIP 使用固定 timestamp，下載包 manifest 的 `base_commit=null`，以每檔 SHA 表示未提交 snapshot，因此同來源在本機與 Docker stdlib builder 可重現相同 bytes。

app 的匿名 allowlist 只提供 `/api/deployment-tools/{sha256}/bootstrap.ps1` 與 `/tools.zip`，含 runtime base path；URL hash 不等於實際 body 即 404。預設來源是 image 的 `/app/host-tools`，若需本機合成測試，可用可信環境變數 `FUCHENG_HOST_TOOLS_DIR` 指向固定工具目錄。不得將 private／data 目錄設為公開來源。標準 `scripts/deployment_package.py build` 仍只 stage 明確 allowlist source，Docker 獨立 host-tools stage 產生公開 assets，沒有把本機 data 送進 context。

`POST /api/admin/deployment-report-capability` 要求五分鐘內建立的有效 admin session 與 CSRF，body 只有 `{report_id:<UUID>}`。既有 `FUCHENG_REPORT_UPLOAD_*` 啟用設定與伺服器秘密不變；不新增 migration。HMAC 有獨立 domain，payload 明確綁 aud/version/device/report/iat/exp/admin/version，驗證精確 schema/type 與不超過一小時的期限。簽發 metadata 與稽核同寫入交易；稽核不含 token。回傳仍沿用報告 schema 1／35 個唯一檢查、原 UUID 及不可變 receipt。

Linux PowerShell 7.6.6 只用於合成資料與受信任本機 TLS 整合驗證。**原生 Windows PowerShell 5.1、Windows ACL、終端互動輸入、CIM／登錄／powercfg、球館硬體與外部網路仍待現場驗證**；冷開機、斷電、正式網域與資料驗收另行授權。
