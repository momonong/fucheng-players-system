# 球館健檢接收站部署（2026-10-22）

台北時間 00:24 完成既有 4090 `fucheng-home` app／backup 更新與明確遷移；00:25 完成外部 HTTPS 合成傳輸驗證。入口維持 [momonong.me/fucheng/](https://momonong.me/fucheng/)，報告接收已啟用，原資料與帳密保留。**這次部署的是未提交工作樹 snapshot，沒有 Git commit／push、tag／Release 或 registry 新版發布**；產品版本仍標示 0.4.2。

## 現用身份

| 項目 | 已核對值 |
| --- | --- |
| 本機 image tag | `local/fucheng:snapshot-da298e6231f1f628` |
| source manifest SHA-256 | `da298e6231f1f628eae04e78260851a8637b38ef3fa6355b835e66a5e02f01d2` |
| Docker Desktop OCI index／建置紀錄 ID | `sha256:319a05b5b5c6f606e88140b13197b9ec000907654b54638c8d2bc6cb55a947c0` |
| 原生 default context config／實際 image ID | `sha256:c36d04c6f8d2e75e90b13e546df998dc0244c22bcb053aed09f26347c091e592` |
| schema | `0012_device_reports` |

建置 `release.json` 保留 Docker Desktop 的原始 OCI index 身份，沒有改寫成 native config ID。`image/native-import.json` 記錄 save/load archive Config SHA 與 native ID 相符、兩個 context 的全部 RootFS layers 相同；兩者對應同一 source manifest，不能把上述 OCI index 當作新版 registry digest。建置使用80份 allowlist來源加1份manifest，共81檔 context，正式部署使用原生 Linux Docker Engine 的 `default` context。

## 遷移與資料保留

先正常停止本 project 的 app／backup，用舊 0.4.2 runtime 成組備份 DB＋媒體並 export，核對 archive 及所有成員 SHA；原 env、舊 image、所有 volumes、checkpoint 與故障回復所需資料均保留。由新 runtime 經既有 writer／maintenance guard 顯式 `ops migrate` 至0012，serve 沒有自動 migration，沒有 init、bootstrap、重設密碼或新增管理員。

遷移及啟動後、驗證登入前，原 **21張表全部欄位與列值完全相同**，包含4個管理員、帳密與原 sessions；只新增空的 `device_deployment_reports`。其後既有帳號登入、管理 GET、下載及登出完成，排除正常認證會影響的 `auth_attempts`、`login_sessions`、`public_visits` 後，原 **18張表及完整管理員值仍相同**。兩次比較均為 integrity ok、FK errors 0；沒有更動會員、比賽、報名或安排。

保留342會員、2場次、81報名、6安排保存版、82安排操作、4管理員、2公告及1份公告媒體。app／backup 同批使用新 native image 且 healthy，新 runtime 成組備份通過；原 `fucheng-home_data`／`fucheng-home_home_backups` 沿用，未清理。備份與 app 同機，仍不等於異地備份。

## 公開接收與權限證據

外部 HTTPS `POST /fucheng/api/deployment-reports/{report_id}` 使用獨立裝置憑證。同一 report UUID／內容重送兩次，得到完全相同收據，資料庫只新增一筆。admin session 可下載該 JSON／Markdown，下載及列表的 digest 與收據一致；錯誤 token、匿名讀取與只持有上傳 token 的 admin 讀取均拒絕。

唯一新增報告明確標記為 **`SYNTHETIC-DEPLOY-PROOF-NOT-CLUB`**，35項 check 全部是 **NOT_TESTED**，只是部署傳輸驗證。report ID 為 `7631dc5d-7159-4134-a82a-dd32f886726e`，收據宣稱綁定裝置 `club-windows-01`；該標籤不證明實體主機身份。這不是球館主機健檢結果，接收收據也不表示檢查通過或部署批准。

未更動 HP／Caddy／Tunnel／DNS／SSH、共用首頁、其他服務或既有8064 loopback入口；專用 `X-Fucheng-Report-Token` 沿既有路由傳送，保留原 Origin／管理 session／CSRF 規則。原手動上傳與管理畫面維持原用法。

## 後續操作與秘密位置

私密設定 `data/home-deployment/home.env` 已持久更新為本次 snapshot、device ID 與 `FUCHENG_REPORT_UPLOAD_TOKEN_FILE` 指向的受限檔案；文件只記設定位置，不保存 token、帳密或認證 hash。app 透過 `/run/secrets/report_upload_token` 讀取上傳憑證，原 Turnstile secret 同時保留。不要用公開範例覆寫現用 env。

後續 Compose 操作必須持續包含三份設定：

```bash
dc=(docker --context default compose --env-file data/home-deployment/home.env
    -f deploy/docker/compose.yaml -f deploy/docker/compose.home.yaml
    -f deploy/docker/compose.report-upload.yaml)
```

一般工具 ZIP 位於 ignored `data/club-report-20261021/kit-candidate/fucheng-host-report-kit.zip`，只有腳本、說明、範例設定與 manifest。球館 `private/club-report.json`／`private/report-upload-token.txt` 另以私密方式配置，不把 token 加入一般 ZIP。操作與固定 UUID 重試方式見[健檢回傳手冊](host-report-upload.md)。

## 回退與未完成驗收

原已發布 v0.4.2 image、原 env、所有備份及 volumes 都保留，但它使用0011 schema，**不能直接啟動目前的0012資料**。失敗時先停本 project 寫入並保留故障庫及後續報告，不 downgrade、不覆寫舊庫、不自動 rollback；必要回復需匹配 image/schema，以升級前成組備份經 runtime import／restore 到全新 target，核對後才切換。

球館 Windows 電腦仍關機，原生 Windows PowerShell 5.1／Docker Desktop、雙擊工具、球館網路、真正 UDP／Tunnel／外部入站、實體手機、原生系統列印、真正 Turnstile 報名、斷電／重開機及人工接受仍待現場驗收。Linux／portable PowerShell fixture 與這次公開合成報告均不代替球館實測。

非秘密部署證據位於 ignored `data/club-report-20261021/home-deployment/` 的 `deployment.json`、`migration.json`、`data-preservation-all.json`、`data-preservation-after-auth.json`、`public-verification.json`；映像身份在同輪 `image/release.json`／`image/native-import.json`。工程驗證與其平台限制另見[驗證紀錄](host-report-verification-20261022.md)。
