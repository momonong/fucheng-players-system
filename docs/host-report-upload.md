# 網站內建部署檢查與報告回傳

網站映像已包含檢查功能。網站依既有流程 init／migrate 並啟動後，管理員登入「系統狀態 → 部署檢查報告」，按「立即檢查並回傳」。**不需要另下載主機健檢包、Git、Python 或建立 SSH**。檢查與原報告保存在網站資料庫，也納入既有資料庫備份。

## 網站內建檢查

預設只檢查目前 app／Linux 容器的 Python／平台、靜態成品、SQLite 結構與完整性、資料磁碟容量、既有備份狀態與入口設定。勾選官方網路檢查後，只連 Cloudflare HTTPS、Docker Registry HTTPS 與 `region1.v2.argotunnel.com`／`region2.v2.argotunnel.com` 的 TCP 7844。這是目前 app 容器的連線路徑；一端未確認即為 WARN，不代表 UDP／QUIC、真正 Tunnel 或主機防火牆通過。固定探測在 helper 內並行，7 秒預算保留已完成結果，parent 仍以10秒硬上限終止。這不代表 Windows 主機、Docker daemon／Compose、BIOS、防火牆、電源／冷開機、真實外部入口、Turnstile 真人流程或完整還原已通過；這些項目保留 NOT_TESTED 與理由。程式不掛 Docker socket、主機磁碟或特權，也不安裝主機代理。

按鈕先保存同一份 schema 2（`report_type=container_runtime`）報告，再回傳到固定 `https://momonong.me/fucheng/api/deployment-reports`。未配置憑證不影響本機檢查；畫面仍可查看、下載 JSON／中文 Markdown。回傳狀態：

| 狀態 | 意義與操作 |
| --- | --- |
| 本機已保存／未配置 | 報告保留；首次掛入合法回傳憑證後，可「重送原報告」 |
| 結果未確認 unknown | 可能已送達；只讀回／重送原 UUID 與原內容，不重新檢查 |
| 接收站拒收 rejected | 保留報告，核對設定或接收站版本後以原 UUID 重送 |
| 已收到收據 received | 已驗 report_id、device_id、digest、接收時間；不表示檢查通過 |

若執行連線中斷，前端保留原請求，先「讀回原執行結果」；伺服器已有收據時只重新 GET。重新整理後保留本頁未確認的請求，並由最新報告恢復保存狀態。不要用重跑代替重送。不同管理員可讀既有報告，只有原執行者可重送。

### 首次配置容器回傳

這是發送端 `REPORT_SEND`，與接收站 `REPORT_UPLOAD` 分開。管理者在首次部署設定專用 token 檔（32–64 bytes 安全亂數的小寫十六進位；不要寫入 env、image、一般日誌或聊天）及接收站綁定的 device ID。token 檔由 app UID 10001 可讀並唯讀掛入，內容不進瀏覽器或報告。

於私密 `club.env` 設定 `FUCHENG_REPORT_SEND_DEVICE_ID` 與 `FUCHENG_REPORT_SEND_TOKEN_FILE`（受保護的主機檔案位置），在既有 Compose 命令最後加 `-f compose.diagnostics.yaml`。overlay 僅對 app 掛入專用 secret，並加入既有 egress network。它設 `FUCHENG_REPORT_SEND_ENABLED=true`；未加 overlay 時預設不送，本機按鈕仍可用。不要把 token 寫成環境值。映像不會自動產生憑證或替接收站配置權限。

`FUCHENG_REPORT_SEND_ENABLED`、`FUCHENG_REPORT_SEND_DEVICE_ID`、`FUCHENG_REPORT_SEND_TOKEN_FILE` 是 app 的發送端設定；缺漏／無法讀取時保存報告並顯示未配置。尚未嘗試發送的報告允許第一次綁定裝置。送出前先持久保存 unknown 與 device，之後換憑證可沿用同 device，不能把同一報告改綁別的 device。禁止 redirect、TLS bypass、任意 URL 與環境 proxy；DNS／TLS／HTTP body 皆由子程序總 deadline 約束（探測 10 秒、回傳 15 秒），逾時終止並保留原報告。

需使用同批新版接收站才能接受 schema 2；舊站回 422 時清楚顯示拒收，不假裝回傳成功。schema 1 Windows 報告、原生腳本與手動上傳仍相容，手動報告不會被標示成容器檢查。

新增 schema `0015_deployment_diagnostics` **只新增** run 表。serve 不 migration；升級依既有停寫、備份、明確 migrate、匹配映像／schema 還原至新目標流程。每站本機檢查最多 500 份／64 MiB，滿時回 507，保留舊報告、不自動刪除。接收站的容量／每小時上限仍獨立適用。

## 額外 Windows 原生深度檢查（選用）

以下工具是主機範圍的額外檢查，**不是使用網站內建檢查的前置步驟**。僅在需要 Windows／Docker 主機資訊時使用，並保留其實機未驗證界線。

工具先在 **Windows 主機原生 PowerShell 5.1 以上**完成既有唯讀健檢，寫下 `report.json`、`report.md`，再以專用憑證回傳。Docker 不可用或檢查有 FAIL 仍可回報；沒有網路時保留原檔。收據只證明伺服器已保存，**不表示檢查通過、主機身份已獨立驗證或准予部署**。不安裝軟體、不啟動容器、不接觸正式 volume、不改防火牆或系統服務。

本功能的程式與工具已備妥；是否已在正式接收站啟用，以當次部署紀錄為準。原生 Windows／球館網路尚須實機驗證。管理頁「額外 Windows 主機檢查／手動上傳」展開後保留原上傳與下載功能。

### 選用原生工具的使用方式

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
