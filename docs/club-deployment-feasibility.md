# 球館一次貼上部署可行性測試

> **歷史工具（2026-11-03 停用接收站後不再作為新部署入口）。** 下列兩支 feasibility
> 腳本固定的 bootstrap／ZIP SHA 屬於當時 4090 接收站的凍結工具；不是目前來源重建
> artifact 的識別，不能拿新 image 取代原接收站就假設固定 URL 仍有效。4090 舊站現已
> 停止，首次下載與報告回傳不可用；既有本機報告／收據保留。球館正式運行不依賴它。
> 目前指南見 [球館部署與維運](club-deployment-runbook.md)。

目前預設使用 `deploy/docker/club-deployment-feasibility-console.ps1` 的完整 `& { ... }` 區塊。完成後終端會列印全部 44 項繁中 Markdown、每項狀態／原因／實測證據／下一步、摘要及本機路徑；直接複製「=== 府城部署檢查結果開始 ===」到「=== 府城部署檢查結果結束 ===」之間的內容貼回聊天即可，不需帳密、token、session 或接收站部署。NOT_TESTED 會完整保留，不當作通過。

Console 版使用獨立 `%LOCALAPPDATA%\FuchengDeploymentCheckConsole`，保留相同固定 image、nonce-only Tunnel 與標籤／ID 清理。第一次保存 JSON／Markdown；之後重貼只重印原報告，略過下載及探測。原主機健檢與原回傳版工作區不變。原生 Windows 5.1、ACL、Ctrl+C/watchdog 仍待現場驗收。

以下為仍保留的可選回傳版；不是目前預設入口。

把 `deploy/docker/club-deployment-feasibility.ps1` 的完整 `& { ... }` 區塊貼入一般使用者的 Windows PowerShell 5.1。無須手動傳資料夾、管理員 shell、GUI 登入窗或永久更改 ExecutionPolicy。接收站必須已支援 `schema_version=3`。第一次執行下載固定 SHA256 的既有 bootstrap／ZIP，僅載入 allowlist 函式並驗證 ZIP manifest。新腳本本身透過聊天完整交付，不需要新的公開下載端點。

工作區是 `%LOCALAPPDATA%\FuchengDeploymentCheck`，有 marker、目前使用者 ACL、reparse 拒絕與排他 lock。原 `%LOCALAPPDATA%\FuchengClubHostCheck` 報告、UUID、operation、收據不受影響。第一次建立新的 `active-check.json`，固定 run/report UUID、nonce 與資源名稱；新報告位於 `data\check-<uuid>`：

- `host-report.json`／`host-report.md`：原 schema 1 的唯讀主機健檢。
- `report.json`／`report.md`：schema 3 的 44 項完整可行性結果，scope 明確記錄容器執行與暫時公開探測是否發生。
- `upload-operation.json`、`upload-status.json`、`upload-receipt.json`：沿用原 sender 的固定 body hash／UUID 與回傳收據契約。

完成報告後的重貼只續傳同份 payload。已有 data 卻缺少 active，或已有 operation／報告 Markdown 卻缺少原 JSON 時會停止；不另建 UUID 或產生替代 payload。已收到收據時不登入；未知回傳時保留原 report／UUID／operation，重新用終端輸入接收站既有管理員取得同報告短效權限。密碼、session 僅存在短命子程序記憶體，token 僅在自有私密 kit，finally 刪除。帳密／token 不會放在參數、原始碼或輸出。錯誤只顯示固定階段及 CLR exception type，不輸出 exception message、HTTP body 或任意 FQID。

測試建立獨立 Docker bridge，以及兩個有 run UUID／nonce-only 標籤的暫時容器。固定的 app 1.2.0 image 僅以 Python entrypoint 執行隨機 nonce HTTP handler；另一個固定 manifest digest 的 cloudflared 2026.10.3 容器建立 HTTP/2 Quick Tunnel。兩者使用 Linux amd64、無 volume、無 LAN port publish、無 host network、無 restart policy；不提供 app、管理或會員介面。五次真正 HTTPS 回讀要求 TLS 驗證、拒絕 redirect、body 精確符合 nonce，記錄成功數及 min／median／max 延遲。視角為 `club-host-via-public-edge`；不代替另一網路手機驗收，QUIC 未測。

每個缺少的 image 最多拉取 90 秒，Tunnel URL 等候約 40 秒，HTTPS 每次最多 8 秒，唯讀健檢子程序最多 240 秒，終端登入／簽權／登出合計最多 150 秒。Docker 命令各自有 3–15 秒界限。finally 先 inspect 名稱，核對完整 ID 與兩個標籤，再以 ID 清除此 run 的兩個容器及 network。獨立隱藏的短命 watchdog 從啟動後 600 秒再次核對清理；nonce server 自身 240 秒退出，防止父程序 Ctrl+C 殘留持續提供內容。watchdog 不是 service／排程；清理未確認會 WARN，保留工作區供核對。不會 prune、改防火牆、電源、正式服務、既有 volume 或重新開機。

本機 health 會額外以 narrow inspect 只取指定試用容器的 `FUCHENG_PUBLIC_ORIGIN`，再作 loopback GET 搭配正確 Host header。只允許此公開設定鍵，不讀取完整環境。這修正 Host 驗證造成的 localhost 400；本機 health 成功仍不等於正式公開 app 驗收。Cloudflare 官方 trace 僅保留觀察到的 IPv4／IPv6 類型，不存完整 IP；不從單次 IP 推論固定 IP、CGNAT 或入站政策。球館網域未提供時保留 NOT_TESTED。

本機合成測試與 Linux Docker 真 Tunnel smoke 不等於球館 Windows 5.1 接受。現場需核對終端輸入、Docker Desktop、實際出口、44 項報告及接收收據。原生 Windows ACL、Ctrl+C/watchdog、球館網域、獨立手機、真實備份還原、開機恢復與長期穩定性仍須各自驗收。
