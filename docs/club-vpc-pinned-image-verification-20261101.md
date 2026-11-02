# 固定 1.2.0 映像的球館搬移相容性驗證

本次使用獨立 Linux Docker context `default`、隨機命名的新測試資料卷與合成管理員。
未開公開 Tunnel、未使用真實會員資料或 Cloudflare 金鑰，未接觸現有服務。

App 固定映像：
`momonong/fucheng-players-system@sha256:0e5a297b0d16876fa56e1b9bed0470c3b8632d55ded6b23ffc5c18315f39e6e2`

驗證結果：

- 使用映像原有 runtime `init` 建立獨立 preview 卷，schema 為 `0015_deployment_diagnostics`。
- 使用 runtime `admin --first-admin-only` 與隱藏互動輸入建立一位合成管理員。
- 透過 runtime `backup` 產生 DB、媒體 archive、metadata 成組備份。
- 透過相同映像 `import-backup`、`restore` 還原到另一個新資料卷。
- 對 source/target 以唯讀掛載執行 `club-vpc-deploy.ps1` 內的 verifier：schema、revision、integrity、foreign keys、所有非 session 資料表、管理員完整資料及媒體全部一致。原 preview marker 保留，新 target 無該 marker；新 target login sessions 為零。
- 正式 Cloudflare 設定下的 `serve` 與 `health` 通過，Turnstile 僅使用不連外的合成設定。
- 還原卷的 `backup-loop`、`backup-health` 通過。
- 停止並重新啟動還原網站後 `health` 通過。
- 本次隨機測試容器與資料卷已清理；測試輸出不含密碼或資料列。
- Root 獨立重跑完整部署與舊 connector 的 focused PowerShell 測試，共 43 項通過；
  涵蓋輸入取消後可重入、未知資料卷／其他 writer 拒絕、舊 connector 升級、失敗保留
  journal 並重新啟動原容器、未知操作不重送，以及 COMPLETE 重跑不還原資料。
- 生成的正式 Compose 經 `docker compose config --quiet` 通過設定解析。
- 公開健康檢查的本機 HTTP fixture：正確 JSON 接受、轉址與超過 4096 bytes 回應拒絕，
  回應本文停滯時約 12.3 秒結束。Worker 的 6 項請求／回應邊界測試通過。

這些結果證明固定映像的備份還原與資料保留流程相容。它們不等於 Windows 5.1、
Windows ACL、Docker Desktop 掛載、球館網路、Workers VPC 端到端登入／報名或冷開機
已完成實機驗收。球館執行腳本後仍須核對公開健康結果與管理員登入；本次不重開機。
