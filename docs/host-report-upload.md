# 球館主機健檢與報告回傳

工具先在 **Windows 主機原生 PowerShell 5.1 以上**完成既有唯讀健檢，寫下 `report.json`、`report.md`，再以專用憑證回傳。Docker 不可用或檢查有 FAIL 仍可回報；沒有網路時保留原檔。收據只證明伺服器已保存，**不表示檢查通過、主機身份已獨立驗證或准予部署**。不安裝軟體、不啟動容器、不接觸正式 volume、不改防火牆或系統服務。

本功能的程式與工具已備妥；是否已在正式接收站啟用，以當次部署紀錄為準。原生 Windows／球館網路尚須實機驗證。既有管理頁手動上傳報告和畫面保持原用法。

## 球館使用方式

1. 取得管理者交付的 `fucheng-host-report-kit.zip`，在可信來源核對隨附 SHA-256，解壓到受管理的本機資料夾，例如 `C:\FuchengCheck`。不需要 Git、Python 或額外 runtime；不要直接在 ZIP 預覽視窗執行。
2. 管理者另外以私密方式提供專用 token 檔。將它放在解壓目錄的 `private\report-upload-token.txt`，只允許執行者與管理者讀取。將 `private\club-report.example.json` 複製為 `private\club-report.json`；確認其中 `device_id` 與伺服器設定相同，`token_file` 指向該私密檔。不要把 token 文字放進 JSON、命令列、聊天、截圖、Git、一般 ZIP 或報告。
3. 雙擊根目錄的 `CHECK-AND-SEND.cmd`。它會產生全新的 `data\host-report-時間-隨機碼\`，執行完顯示保存位置與結果。預設也執行已授權的有限官方端點 DNS／Cloudflare／registry／ngrok 連線探測，並回傳至設定的 HTTPS 接收站；若只要本機探測加 `-SkipNetwork`。UDP／真正 Tunnel、外部入站與重開機仍是 NOT_TESTED。設定中的 `image_ref` 指向核對過的 0.4.2 manifest digest，可在授權更新時明確改成新固定版本，不執行 pull。

預設唯一接收位置為 `https://momonong.me/fucheng/api/deployment-reports`。腳本只向設定的精確 HTTPS 位置傳送，不跟隨任何 redirect，不跳過 TLS 驗證，不搜尋其他入口。若站點要求跳轉、憑證異常或斷網，應由管理者核對；不要關閉安全檢查。

保留同一個報告資料夾：

| 檔案 | 用途 |
| --- | --- |
| `report.json`、`report.md` | 原始健檢結果；不覆寫舊資料夾 |
| `upload-operation.json` | 固定 report UUID、endpoint、device ID、原始 JSON 位元組 SHA-256；不含 token |
| `upload-status.json` | 最近一次回傳狀態 unknown／rejected／received、HTTP code、時間 |
| `upload-receipt.json` | 成功時的伺服器 report_id、device_id、canonical digest、received_at；一旦建立不覆寫 |

逾時或顯示 `UNKNOWN` 時，伺服器可能已保存。**不要重做健檢或換 ID 來重試同一份報告**。在解壓根目錄開啟 PowerShell，將路徑換成顯示的原報告資料夾：

```powershell
.\deploy\docker\check-and-send.ps1 -RetryReportDirectory '.\data\host-report-原來那一份'
```

重試不再執行健檢；會驗證原報告 hash、原 endpoint／device ID，使用原 UUID。成功後再次執行會讀原收據。需要重新檢查主機時才再雙擊產生全新報告。不要編輯已建立 operation 的 JSON；更正內容需保留舊資料交管理者核對。

HTTP 401：核對私密 token／綁定設定。403：核對接收站與 Origin。404：可能尚未啟用。409：ID 已綁其他內容，停止並交管理者核對。413／422：大小／格式不被接受。429：稍候以原 ID 重試。507：容量已滿，舊報告不會被刪，保留本機檔案並聯絡管理者。失敗不輸出 token、例外原文或 raw HTTP body。

只做健檢、不回傳時，可直接執行既有 `host-preflight.ps1 -OutputDir <本工具data下的新路徑>`。Git Bash 使用既有 `host-preflight.sh`；一鍵回傳本身不依賴 Git Bash。

## 接收站設定與界線

預設 `FUCHENG_REPORT_UPLOAD_ENABLED=false`，匿名／缺少或錯誤 token 不接受。單一 server 設定的 device ID 與獨立 token 綁定；token 只允許 append 報告，不能登入管理員、讀會員或讀任何報告。host.name 只是報告宣稱名稱，device ID 是憑證綁定標籤，均不證明實體主機身份。

token 必須由安全亂數產生 **32–64 bytes**，以 64–128 個小寫十六進位字元放入獨立秘密檔（例如 `secrets.token_hex(32)` 的結果；不要印到一般日誌）。server 只接受 `FUCHENG_REPORT_UPLOAD_TOKEN_FILE`，不接受 token 環境值。Settings repr 隱藏 token，驗證以固定長度 hash 常數時間比對；檔案不存在或無效時拒絕啟動。秘密檔不得打包進 image／source manifest／一般球館 ZIP，從受保護位置唯讀掛載。

在原接收 app 的 Compose 組合末尾加入 `compose.report-upload.yaml`，保留原 `compose.home.yaml`／TLS／Turnstile／可信 proxy 與既有 volumes。overlay 只對 app 注入：

```text
FUCHENG_REPORT_UPLOAD_DEVICE_ID=club-windows-01
FUCHENG_REPORT_UPLOAD_TOKEN_FILE=<受保護的主機檔案絕對路徑>
FUCHENG_REPORT_UPLOAD_MAX_REPORTS=500
FUCHENG_REPORT_UPLOAD_MAX_BYTES=67108864
FUCHENG_REPORT_UPLOAD_HOURLY_LIMIT=12
```

Compose 將檔案掛載為 `/run/secrets/report_upload_token`；不要當成 admin 密碼或 Tunnel token。API 跟隨 runtime `FUCHENG_BASE_PATH`，根路徑與 `/fucheng` 使用同一映像。sender 設 `Origin` 為 endpoint scheme＋host，沿用 trusted HTTPS ingress 與 same-origin 規則，沒有放寬管理登入／CSRF。專用 `X-Fucheng-Report-Token` 可通過既有移除 Authorization 的 proxy，不需變更共用 Caddy；proxy／監控不可記錄此 header。

schema 新增 **0012_device_reports**，只新增 `device_deployment_reports`、索引及禁止 UPDATE／DELETE 的 SQLite triggers；既有 21 張表不改欄位、不補歷史、不改資料。更新依既有 runtime 流程停寫、成組備份、`ops migrate`、驗證後啟動；**serve 不自動 migration**。寫入沿 server 生命週期 writer.lock／maintenance guard；單筆 `BEGIN IMMEDIATE` 串行核對 ID、rate、容量與 INSERT。不繞過 runtime 直接寫 volume。舊 image/schema 不匹配時不可只換回程式，依既有匹配備份還原至新目標並保留故障庫。

容量以 canonical JSON bytes 計，預設 500 份／64 MiB；單份原文與 canonical 均最多 256 KiB，沿用 schema1、35 項 check 與嚴格 parser。每 device 每小時最多 12 份新報告，另有 admission/body 大小／5 秒 body deadline。重送同 UUID＋同內容回相同 receipt，不新增行或占新報告配額；同 UUID 不同內容／device 回 409。FAIL／WARN 仍可保存。容量滿回 507，不自動刪除，本版無刪除 API。token 輪替後原 device ID 可重試；device ID 變更須先核對未完成 operation。

## API 與管理者取回

路徑以下省略 runtime prefix（本接收站預期 `/fucheng`）：

| 方法與路徑 | 認證／內容 |
| --- | --- |
| `POST /api/deployment-reports/{report_id}` | UUID；`X-Fucheng-Report-Token`；原 schema1 body；回 report_id／device_id／digest／received_at |
| `GET /api/admin/deployment-reports?limit=20&before=<UUID>` | 原 admin session；回 receipt、宣稱主機名、檢查時間、summary；next_before 分頁 |
| `GET /api/admin/deployment-reports/{report_id}/json` | 原 admin session；下載 JSON |
| `GET /api/admin/deployment-reports/{report_id}/markdown` | 原 admin session；可信 renderer 產生 Markdown，文字轉義，不執行內容 |

receipt digest 是伺服器對驗證後 canonical JSON（固定 key 次序、緊湊 UTF-8）的 SHA-256；operation raw_report_sha256 是 Windows 原始檔 bytes hash，兩者用途不同。GET／下載維持 no-store／nosniff，上傳憑證不能代替管理 session。沒有新增狀態 UI，也不取代原單份手動上傳 API。

## 工具打包與驗證範圍

開發端執行 `uv run --locked python scripts/host_report_kit.py data/<全新資料夾>/fucheng-host-report-kit.zip` 建立固定 allowlist ZIP。只含腳本、範例設定、本文件及逐檔 manifest，不讀 private、data、token、資料庫或備份；拒絕覆寫已有 ZIP。PS1 含 UTF-8 BOM，相容 Windows PowerShell 5.1。核對 ZIP SHA-256 後另行私密配置。

Linux backend 合成測試涵蓋 parser、權限、Origin／base path、容量／速率、防重、回應遺失後同 ID 重試、migration 保留原21表與 append-only。另以官方 portable PowerShell 7.6.6 實跑 wrapper（主機探測用合成 fixture）→sender→隔離 HTTPS receiver，驗證成功收據、回應遺失後同 ID 重試、拒絕 redirect／錯誤收據、未受信任 TLS、原檔變更拒送；測試 CA 僅透過子程序 SSL_CERT_FILE 信任，不改全域 trust。這些證據不等於 Windows PowerShell 5.1、原生主機檢查、雙擊或球館實機通過。
