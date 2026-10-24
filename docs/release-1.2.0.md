# 1.2.0：映像內建部署檢查與報告回傳

管理員可直接在網站執行目前 app／Linux 容器的部署檢查，先保存本機報告，再回傳至固定 HTTPS 接收站；不需先下載 Windows 健檢包。這是功能版本升級；專案自身版本由 1.1.0 提升為 1.2.0，依賴版本不變。本文件目前記錄發布候選，正式發布與部署狀態見下方。

## 功能範圍

- 管理員登入後，在「系統狀態 → 部署檢查報告」按「立即檢查並回傳」，產生 schema 2、`report_type=container_runtime` 報告。檢查目前容器的 Python／平台、靜態成品、SQLite 必要表／欄與完整性、資料磁碟容量、既有備份狀態及入口設定；不讀取會員或報名內容。
- 預設只做本機檢查。勾選官方網路檢查後，才探測固定 Cloudflare HTTPS、Docker Registry HTTPS 及兩個官方 Tunnel region 的 TCP 7844；一端未確認即保留 WARN。這些結果只描述目前 app 容器的連線路徑。
- 同一份報告先保存於本機，才向固定 `https://momonong.me/fucheng/api/deployment-reports` 回傳。未配置憑證或回傳失敗仍可查看、下載 JSON／中文 Markdown；下載目前檢視的原報告，不以後來的新報告替換。
- 未知寫入可在重新載入後依原 request UUID 讀回；重送原報告固定原 UUID、裝置及保存的 canonical bytes，不自動重跑檢查或換 ID。取得有效 receipt 後只讀回，不再重送；GET 確認原 run 存在並解除 pending 後，管理員可明確另建新的獨立診斷。
- 回傳狀態區分未配置、未知、拒收與已收件。只有核對 report ID、device ID、digest 與收件時間後才標示已收件；收據不表示所有部署檢查均通過。本機最多保留 500 份／64 MiB，容量滿明確回 507、保留舊報告且不自動刪除。

舊 Windows schema 1 報告、原生健檢腳本與手動上傳仍相容；手動報告保留其原範圍，不會被標成容器檢查。使用方式與狀態恢復見[檢查與回傳操作](host-report-upload.md)。

## 相容與資料保護

新增 Alembic `0015_deployment_diagnostics`，接續 `0014_doubles_registration`，只新增 `deployment_diagnostic_runs` 表及其保護 trigger，不改寫舊業務表。run 身分與報告內容固定、禁止刪除；device 首次送出前綁定，之後不可改綁。既有個人賽、雙打、會員、安排 layout 與帳號契約保留。

發送端 `REPORT_SEND` 與接收端 `REPORT_UPLOAD` 分開配置。發送採 app 專用、受保護且唯讀掛載的 token 檔與已綁定 device ID；`compose.diagnostics.yaml` 只為 app 加入 secret 及既有 egress network，不掛 Docker socket、主機磁碟或特權。token 不寫入 image、瀏覽器、報告、環境值或一般日誌；未加發送 overlay 時預設不送，本機檢查仍可用。固定 HTTPS 回傳保留 TLS 驗證、拒絕 redirect，不接受使用者指定任意 endpoint。

schema 2 發送端與接收站須同批更新；舊接收站拒收時保留本機報告，不誤標成功。前後端及 app／backup／ops 使用同批映像，同一 image 繼續支援根路徑與 `/fucheng/`。部署設定見[部署手冊](deployment.md#映像內建部署檢查schema-0015)。

既有部署須先停寫，以原 runtime 成組備份 DB＋媒體並核對 hash，再由新版 runtime 經 lifecycle lock／maintenance guard 顯式 migrate。serve 不 migration；不向真實資料新增測試會員、場次或報名。`0015` 禁止直接 downgrade，不能只切回舊 image；回退須保留故障庫，以升級前備份還原至新目標，搭配匹配的 image／schema。

## 已取得的工程證據

- 後端完整基準：353 passed、6 項既有 PowerShell skips、2 項既有 TestClient deprecation warnings。最後三項審查修正以受影響範圍補驗 40 passed，沒有宣稱基準完整 suite 已包含最後補修。
- 最新瀏覽器：根路徑與 `/fucheng` 各 16 passed，合計 32；包含桌面／手機的一鍵檢查、unknown 原 key 恢復、receipt 後只 GET、409 核對、明確 507 恢復、原 run 下載及舊 schema 1 手動上傳。typecheck 與專用成品 build 通過，桌面／手機截圖與無水平溢出已核對。
- 獨立審查原有三項 P2：備份狀態非 object 中止報告、缺必要資料欄仍 PASS、本機 507 永久 pending，均已修正並定向複核關閉；沒有新增阻擋問題。
- 候選二 linux/amd64 snapshot 的根路徑／子路徑、容器重啟、原 UUID 讀回及成組備份驗證通過。備份核對包含 schema、完整性、DB／媒體 hash、image manifest 與還原設定；未執行完整還原。
- 同一候選映像的私有 TLS fixture 驗證 schema 2 收據、憑證與 hostname、拒絕不受信 TLS、重啟後相同 receipt，以及相同請求不增加發送次數。使用私有隔離網路，未測真正外部接收站，沒有 TLS bypass、host port 或主機信任庫變更。

上述映像證據屬發布前候選二：image ID `sha256:2712707552727dcd148f4019b4aceb41329e89a0c45820e4eaafdcf8c03f2de4`，source manifest `33d6f9ccbd7619d6abcedc15899ca2594405c5622203fc0554667a20c521ece5`。這是版本 metadata 調整前的 snapshot，不能當作正式 `1.2.0` registry digest；正式映像須由最終固定來源重新建置並核對。

本輪原始 log、截圖、實作紀錄、審查與映像 smoke 收據保留於 ignored `data/image-deployment-checks-20261024/`，不納入 image context。版本 metadata 的 `uv lock --check --offline`、前端 typecheck、版本／lock 結構與 diff 檢查均通過；四份套件與 lock 檔只有自身版本改動，依賴完全不變。沒有因改版號重跑充分的完整後端或 E2E。

## 發布、部署與驗收狀態

目前為 1.2.0 發布候選；本文件準備階段尚未完成本版 commit／合併／推送、tag／GitHub Release、Docker Hub 正式映像發布或現用站升級。正式來源 commit、registry digest、部署時間及資料／帳號保留證據，須於實際操作並核對後補記，不能以候選 snapshot 或本機測試代替。

球館 Windows／Docker Desktop／WSL2、真實接收站及官方外網、實體手機、冷開機／斷電、UDP／QUIC、真正 Tunnel、主機防火牆、Turnstile 真人流程與完整還原仍未驗證。容器重啟不等於主機重開機，備份可讀不等於完整還原成功；上述主機或外部範圍在報告中保留 NOT_TESTED 與理由。工程通過不代表現場或使用者人工接受。
