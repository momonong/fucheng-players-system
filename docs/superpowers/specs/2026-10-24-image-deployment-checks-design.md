# 映像內建部署檢查

## 使用者目標與授權

使用者要求：「先整合進去，我預計映像拉下來，把網站架起來就可以直接檢查」。沿用已授權的報告回傳接收站 `https://momonong.me/fucheng/api/deployment-reports`。不用另下載專案、主機健檢包或建立 SSH。先完成實作、驗證與候選映像；Git 發布和現用站更新仍分別依當次授權。

## 操作與完成條件

管理員開啟現有「系統狀態 → 部署檢查報告」，按「立即檢查並回傳」。網站本身產生報告並保存；部署已掛入專用上傳憑證時，用同一份報告回傳到接收站。未配置憑證或網路失敗時仍可查看、下載 JSON／中文 Markdown；不丟棄報告，不宣稱回傳成功。重送固定報告 UUID 和原文，逾時不重新健檢。

這是正在執行的 app／Linux 容器檢查，不是 Windows 主機代理。可檢查 Python／平台、靜態成品、資料庫連線與結構健康、所在資料磁碟容量、既有備份狀態、入口設定與有限官方網路端點。網路包含官方 HTTPS 與既有兩個 Cloudflare region 端點的 TCP 7844；結果只描述 app 容器目前的出站路徑，不能宣稱 UDP／QUIC、真正 Tunnel 或 Windows 防火牆已通過。無法直接確認的 Windows 版本、BIOS、主機防火牆、Docker daemon／Compose、電源與重開機、真實外部入口、Turnstile 真人流程及完整備份還原一律 NOT_TESTED，並提供中文理由。不安裝 Docker socket、特權容器、主機磁碟或命令執行代理。

## 已選方案與取捨

- 採既有 FastAPI／React 的管理員功能：啟動同一映像後立即可用，沒有另一次主機腳本安裝。這是本次依使用者已確認流程所做的實作決策。
- Windows 原生代理可取得更多資訊，但需要額外安裝、權限與維護，與本次減少現場操作的目標相反，不採用。
- Docker socket／主機任意命令橋接會擴張到整台主機控制權，不採用。

## 資料與 API

舊 `HostReport` schema 1、Windows 腳本、手動上傳與既有報告保持相容。新增明確標識 `report_type=container_runtime` 的 schema 2，不能把 Linux 容器偽裝成 Windows；接收站和 Markdown renderer 同時接受兩種報告。既有大小、嚴格 JSON、認證、Origin、容量與 append-only 收據契約維持。

新增 `0015_deployment_diagnostics`，只新增 `deployment_diagnostic_runs`。保存 report UUID、actor、請求 fingerprint、不可變的 canonical report／digest、接收端 endpoint／device 與回傳狀態／收據。產生報告、更新現有最新報告及新增既有稽核在同一 SQLite 寫交易。只保留有限數量（500 份／64 MiB）；滿時回 507，保留舊資料。schema 必須經既有 runtime 明確遷移，serve 不 migration，不改業務表與既有帳號。

新增管理 API：

- `POST /api/admin/deployment-report/run`：`{version, request_id, probe_network}`；現有 session＋CSRF。固定 UUID 綁 actor／完整 payload；同 key 重試不重跑健檢、不重複保存或重送已完成回傳。
- `GET /api/admin/deployment-report/runs/{request_id}`：讀回原執行結果，所有現有管理員可讀。
- `POST /api/admin/deployment-report/runs/{request_id}/send`：重送已保存的原報告，僅原 actor，沿用 UUID／endpoint／device；不接受任意 URL 或報告內容。
- 原 `GET /api/admin/deployment-report` 增加 nullable `run` 回傳狀態；原手動上傳會切回原來的 schema 1／run=null。

檢查及回傳各自有單一進行中守門及有限 timeout，寫入版本衝突回 409；執行前先查 key 和 version，保存前再核對。SQLite 寫鎖不包住網路探測。HTTP 之前先持久標記 unknown，之後才送出；遺失回應或重啟後可用原 key 安全恢復。所有公開回應與報告均不含 token、私密路徑、環境變數值、認證 hash、會員或報名內容。

## 配置與回傳

新增獨立的 `FUCHENG_REPORT_SEND_ENABLED`、`FUCHENG_REPORT_SEND_DEVICE_ID`、`FUCHENG_REPORT_SEND_TOKEN_FILE`；預設不送，設定缺漏不影響本機檢查。只有明確啟用才讀 bounded regular secret file，驗證同接收站的 token 格式，repr 不顯示秘密。endpoint 固定為上面的 HTTPS 接收站，禁止 redirect 和 TLS bypass；Origin 為 scheme＋host，token 只在 server-to-server header 內，不進前端。

提供 `compose.diagnostics.yaml` 可選 overlay，只對 app 掛入專用 secret，並讓 app 接入既有 egress network。基本 image 和檢查按鈕不依賴外部檔案；部署的回傳憑證和其他部署金鑰一樣在首次設定時私密掛入，不放公開 image。舊接收站不支援 schema 2 時，保留本機報告並清楚顯示拒收，不能假裝已回傳。

## 驗證界線

測權限／CSRF、版本與 key 衝突、容器來源和 NOT_TESTED、秘密遮蔽、同 key 防重、丟失回應／重啟恢復、錯誤或 redirect 收據、schema 1／2 接收與下載、遷移保留舊表和備份相容。前端桌面／手機與根路徑／`/fucheng` 驗證按鈕、結果、原報告重送和 unknown 讀回，測試不使用外部真實網路。候選 image 在獨立 project／port／volume 上驗同批前後端、明確 init／migrate、報告及備份。未在球館 Windows 實跑、真正外部網路、實體手機或冷開機驗證前不宣稱已通過。
