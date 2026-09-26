# Windows Docker 部署、搬移與維運

## 0.3.1 候選：管理後台部署檢查報告

此版新增 `0010_deployment_report` migration。在目標 Windows 主機的 Git Bash、已整合本版腳本的 repo 根目錄執行 `bash deploy/docker/host-preflight.sh data/host-preflight-club-YYYYMMDD`；需要測出站網路時另加 `-ProbeNetwork`，並改用新的輸出目錄。腳本不需要 Python、不執行容器、不修改主機網路設定；只在 ignored `data/` 下建立 `report.json` 和 `report.md`。舊離線 kit 的 `preflight.ps1 -Output` 維持原契約，不以本腳本取代。

用管理員帳號登入後，依序開啟**系統狀態 → 部署檢查報告**，選擇 `report.json` 上傳。伺服器只接受 256 KiB 內且符合 schema v1 的 JSON；管理員 session、CSRF 與目前報告版本都必須通過，格式失敗或版本衝突會保留既有報告。頁面只顯示最新一份，可查看 35 項結果與入口建議、複製伺服器生成的 Markdown、下載 JSON/Markdown。所有內容都當純文字處理；報告不進 public API 或靜態檔，管理端回應使用 `no-store`。上傳者提供的主機名稱與檢查結果**未經伺服器獨立證實**，須現場核對目標主機身份與執行時間；超過七天及未來時間會提示風險。開發電腦的 Windows Enterprise 報告不可充作球館 Windows Pro 的驗收。

最新報告與每次替換的版本、操作者和 SHA-256 稽核記在既有 SQLite 資料庫，隨資料庫成組備份及新目標 restore；沒有新的外部檔案或容器權限。升級前依下文 runtime lifecycle guard 停止舊 app 寫入、取得 `0009` 完整 DB＋媒體備份並核 hash，使用相容的新 image 明確執行 `ops migrate` 至 `0010`，再啟動 app/backup 並驗證登入、報告與照片。`start` 不會自動 migration。回退須保留故障庫，將**升級前**備份還原至另一個新 volume/project，配回 0.3.0／`0009` image；不可拿 0.3.0 app 寫 `0010` DB，也不可用 Alembic downgrade 清除報告稽核。公開預覽與正式服務的切換需另核對當次授權。

## 0.3.0 球館 Windows 快速部署（Git Bash + Docker Desktop）

此流程使用 **Docker Desktop 的 WSL 2／Linux containers**；Git Bash 只提供 Git 與命令列，不取代 Linux 容器。以下先建立新 project、新 named volume 的合成預演；真實名單匯入、正式入口切換及場地電腦的斷電恢復驗收須另外執行。2026-09-26 已在開發電腦從 Docker Hub 拉取 0.3.0、以獨立 volume 還原合成資料、驗 HTTPS／圖片／重啟／週備份與新目標還原；**尚未在球館 Windows 主機驗收**。

1. 從官方頁面安裝 [Git for Windows](https://git-scm.com/install/windows)（使用 Git Bash）及 [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)；依 Docker 的系統需求核對 Windows／WSL 版本，在 Docker Desktop 啟用 WSL 2 backend、Linux containers，啟動 engine。確認 CPU 虛擬化、磁碟空間、Docker Desktop 登入／開機啟動與主機斷電後恢復方式。Docker Desktop「登入時啟動」不等於無人登入後自動恢復。
2. 從 Git Bash 執行以下命令。使用已整合本部署文件的 repo 版本；核對 `git rev-parse HEAD`，不要將不相容的未來程式碼／Compose 與 0.3.0 image 混用。

   ```bash
   git clone https://github.com/momonong/fucheng-players-system.git
   cd fucheng-players-system
   git rev-parse HEAD
   wsl.exe --version
   bash deploy/docker/host-preflight.sh data/host-preflight-before-club -TestPort 8052 -DockerSubnet 172.30.98.0/24
   docker info --format '{{.OSType}}/{{.Architecture}}'  # 預期 linux/x86_64
   docker compose version
   docker pull momonong/fucheng-players-system:0.3.0
   docker image inspect momonong/fucheng-players-system:0.3.0 --format '{{json .RepoDigests}}'
   docker pull ngrok/ngrok@sha256:14d80d083e5b53145f416bbbd36238336c9de4016c43fd950eb2eb845670583b
   mkdir -p deploy/docker/secrets deploy/docker/backup
   cp deploy/docker/release.env.example deploy/docker/release.env
   cp deploy/docker/ngrok.yml.example deploy/docker/secrets/ngrok.yml
   ```

   0.3.0 的預期 OCI index digest 為 `sha256:339f35c9b4f251d41279e8db7070541c67bdfa93a03635933a85f4aa957463dd`（linux/amd64 manifest `sha256:bd667c154a2533d1102ff9cd98ac2d8b1e1a56e6f4befe0155f36dc16da1fcab`）；若拉取結果不同，先停止。新 project 名、`172.30.98.0/24` 範例網段及 host 備份路徑須先與現有 Docker networks／volumes／LAN／VPN 核對，不能沿用其他部署的 volume。`.env`、ngrok token、`backup/` 均不入 Git。
3. 從 ngrok 帳號取得**此部署專用且已指定的 HTTPS domain** 與 authtoken；兩個值分別填到 `deploy/docker/release.env`、`deploy/docker/secrets/ngrok.yml`（不要貼在聊天、指令參數或提交）。[ngrok Docker agent 官方說明](https://ngrok.com/download/docker)可供核對安裝方式；`ngrok.yml` 的 upstream 保持 `http://app:8000`。`release.env` 至少設定：

   ```dotenv
   COMPOSE_PROJECT_NAME=fucheng-club
   FUCHENG_IMAGE=momonong/fucheng-players-system@sha256:339f35c9b4f251d41279e8db7070541c67bdfa93a03635933a85f4aa957463dd
   FUCHENG_PUBLIC_ORIGIN=https://YOUR_ASSIGNED_DOMAIN.ngrok-free.app
   FUCHENG_PROXY_KIND=ngrok
   FUCHENG_SUBNET=172.30.98.0/24
   FUCHENG_APP_IP=172.30.98.2
   FUCHENG_PROXY_IP=172.30.98.3
   FUCHENG_BACKUP_PATH=./backup
   FUCHENG_BACKUP_KEEP=8
   FUCHENG_NGROK_CONFIG_FILE=./secrets/ngrok.yml
   ```

   在私密 `ngrok.yml` 中把 `agent.authtoken` 與 `endpoints[0].url` 的範例值換成自己的值。`FUCHENG_PUBLIC_ORIGIN` 與 endpoint URL 必須逐字相同且沒有尾端 `/`。此 ngrok 預演未設定真實 Cloudflare Turnstile 金鑰，app 使用 `disabled`；此設定不代表抗機器人驗收。不要將真實名單放入預演 volume。
4. 先驗設定，再**只對全新空 volume** 初始化與建立管理員；管理員密碼由容器互動提示輸入，不放在命令列。Git Bash 若回報 `the input device is not a TTY`，只為 `admin` 那一行加 `winpty` 前綴。

   ```bash
   dc=(docker compose --env-file deploy/docker/release.env -f deploy/docker/compose.yaml -f deploy/docker/compose.ngrok.yaml)
   "${dc[@]}" config --quiet
   "${dc[@]}" run --rm ops init
   "${dc[@]}" run --rm ops admin admin
   "${dc[@]}" --profile ngrok up -d --wait --wait-timeout 120 app backup ngrok
   "${dc[@]}" ps
   curl --fail --show-error -H 'ngrok-skip-browser-warning: 1' https://YOUR_ASSIGNED_DOMAIN.ngrok-free.app/api/health
   "${dc[@]}" exec -T backup python /app/runtime.py backup-health
   bash deploy/docker/host-preflight.sh data/host-preflight-after-club -ComposeProject fucheng-club -Domain YOUR_ASSIGNED_DOMAIN.ngrok-free.app -PreviewOrigin https://YOUR_ASSIGNED_DOMAIN.ngrok-free.app -ProbeNetwork
   ```

   公開頁面、JS/CSS、公告圖片、免登入選名與管理員登入還要在手機 HTTPS 入口驗收。`app` 沒有 host port，只有 Docker 私有 origin network 的 ngrok 容器能以指定 proxy IP 到達；入口要求精確 Host／Origin、CSRF 與 Secure cookie。`backup` 每週一台北時間 04:00 備份，啟動時補做最近漏跑週次；`backup/` 是同機副本。手動 checkpoint 可執行 `"${dc[@]}" run --rm ops backup`，不取代週排程。使用**另一個受管理的磁碟**上的全新目錄執行成組匯出；此命令會核對 archive 與每個成員的 hash：

   ```bash
   powershell.exe -NoProfile -File deploy/docker/operate.ps1 -Action ExportBackups -EnvFile deploy/docker/release.env -Value 'E:\fucheng-export-YYYYMMDD'
   ```
5. 重啟後再執行 `"${dc[@]}" ps`、`"${dc[@]}" run --rm ops inspect`、`backup-health` 與手機 HTTPS smoke，確認 named volume 與媒體持久化。升級時先 `backup`／`ExportBackups`，保留舊 image 與原資料，停止此 project 的 app／backup／ngrok，拉取且核對新版 image，若有 schema 變更才以新版 `ops migrate` 明確遷移，再同批啟動。不可用舊 image 開新版 schema；回退要使用匹配 image/schema 的備份，在**另一個**新 project／volume `ImportBackup`→`Restore` 演練，保留故障庫。下文有鎖、備份與還原契約。

   新目標還原時，先複製 `release.env` 為受忽略的 `restore.env`，改成**新的** `COMPOSE_PROJECT_NAME`、未衝突 subnet／IP、`FUCHENG_BACKUP_PATH` 與目標 HTTPS origin；不要啟動舊 project 的 app，也不要把舊 named volume 掛到新 app。從已驗證匯出目錄選**明確檔名**的 `.db`，確認同名 `.json`、`.media.tar` 一起存在，再執行：

   ```bash
   powershell.exe -NoProfile -File deploy/docker/operate.ps1 -Action ImportBackup -EnvFile deploy/docker/restore.env -Value 'E:\fucheng-export-YYYYMMDD\weekly-EXACT.db'
   powershell.exe -NoProfile -File deploy/docker/operate.ps1 -Action Restore -EnvFile deploy/docker/restore.env -Value 'weekly-EXACT.db'
   docker compose --env-file deploy/docker/restore.env -f deploy/docker/compose.yaml run --rm ops inspect
   ```

   `Restore` 會清除舊管理員 session；若要對外啟動新目標，先核對新 origin 的代理、完整功能及入口切換授權。此新目標演練只驗證備份可還原，不自動把它當成正式資料。

### Git Bash 主機健檢的範圍與判讀

`host-preflight.sh` 是 Git Bash 入口，呼叫**主機原生 PowerShell** 的 `host-preflight.ps1`；不需 Python，不修改路由、防火牆、Docker daemon 或現用服務。唯一預設寫入為使用者指定、位於 repo 忽略的 `data/` 下**尚不存在**的輸出目錄，其中固定產生 `report.md` 與 `report.json`；已存在的目錄一律拒絕覆寫。離線包舊 `preflight.ps1 -Output` 仍保留其原單檔契約，兩者勿混用。Git Bash 入口的 `-ExecutionPolicy Bypass` 僅作用於此次 PowerShell 程序，不修改主機長期政策；先確認 clone 來源與腳本內容。

部署前使用不同的輸出目錄執行上述第一次命令；尚未 `docker pull` 時 `app_image=WARN` 屬預期。部署後使用第二次命令，將 `-ComposeProject` 限定至新 project，`-Domain` 與 `-PreviewOrigin` 換成實際 ngrok 名稱與精確 HTTPS origin。`-ProbeNetwork` 是**明確 opt-in**：只對所給 domain 與 Cloudflare、Docker Registry、ngrok 官方端點做限時 DNS／TCP／HTTPS 查詢，不傳 token、不執行 container，也不掃 LAN；預設沒有任何外部請求。任一命令逾時或缺失仍應產生 `PASS`／`WARN`／`FAIL`／`NOT_TESTED`、理由、證據與下一步；外部指令的原始 stdout/stderr 不進報告。`-TimeoutSeconds` 預設 5，可在 1–20 秒內調整。每次重跑選新的 `data/host-preflight-*` 目錄。

報告只代表執行當下的**那部 Windows 主機**。Docker image/platform、指定 project 的狀態與 restart policy 是 Docker CLI 證據；不從容器推論 Windows 的 WSL、開機登入、休眠或防火牆。`docker_service` 即使存在也不是無人登入冷開機保證；`backup_write_and_restore` 必須靠隔離合成備份／新目標還原。TCP 7844 成功只支持 Cloudflare HTTP/2 的網路路徑，不證明 UDP/QUIC；HTTPS 成功也不證明 Tunnel agent、帳號金鑰或網域控制。當次沒有 Cloudflare domain/key 或外部手機探測時，相關項目保持 `NOT_TESTED`。本機私有 LAN IP 不足以判定 CGNAT；DNS 成功、本機 port 空閒或從主機連回公開 URL，也不等於外網入站可達。

入口選型依據：[Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/)與[7844 防火牆需求](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/)是**出站公開入口**，可先評估是否直連既有單 app；ngrok 也是出站試用入口。[Caddy 自動 HTTPS](https://caddyserver.com/docs/automatic-https)與 nginx 是**reverse proxy**，可與 Tunnel 組合；若選公網直連，須另驗網域/DNS、入站 80／443、持久憑證與續期。Caddy 的 DNS-01 可免入站完成簽證，卻不使網站自動對公網可達；[原生 Windows nginx beta 限制](https://nginx.org/en/docs/windows.html)不可套用到 Docker Linux nginx。健檢只提出待驗證的推薦，不切換 Tunnel 或公開路由。

本輪開發電腦實測報告位於忽略的 `data/host-preflight-delivery-20260926/`（預設唯讀）與 `data/host-preflight-network-delivery-20260926/`（外網 opt-in）：該電腦是 Windows Enterprise，不能當作預定球館 Windows Pro 的實機證據。外網 opt-in 從**此開發電腦**測得 Cloudflare 兩個 region 的 TCP 7844、HTTPS、Docker Registry 401（認證預期）、ngrok TCP 443、既有 8052 HTTPS health；UDP/QUIC、Cloudflare domain/key、外部入站與冷開機仍為 `NOT_TESTED`。另外用無 Docker、daemon 錯誤、1 秒逾時與假 token 輸出驗證結構化報告及遮罩；無需觸碰 live volume。Git Bash 本身未安裝在此開發電腦，入口 shell 尚待球館主機實跑；PowerShell 5.1 核心已在此機驗證。

### 既有 host ngrok agent 的 Docker 預覽入口

若該電腦已有 ngrok agent 占用帳號 session，並且已轉發 `http://127.0.0.1:8052`，可改用 `compose.host-ngrok.yaml`：只載入 `compose.yaml`＋此 overlay，以 `app backup host-ngrok` 啟動，不啟動第二個 ngrok 容器。overlay 只把 nginx proxy 綁在 `127.0.0.1:8052`，app 仍無 host port，信任來源固定為私有網段的 proxy IP；先確認 8052、既有 ngrok 身分、公開 origin 與資料 owner，停寫並成組備份後才切換。此路徑於 2026-09-26 用 0.3.0 合成預覽驗證；ngrok 帳號對第二個 agent 回 `ERR_NGROK_108`，因此沿用原 agent。原生 8052 DB／媒體保留、原生 app 停止，Docker 使用新 volume；不可把原 DB 直接掛進 app。host proxy 將入站來源固定為 Docker host gateway，這條路徑的 app 內 IP 節流無法區分個別外部訪客；長期部署優先使用上方直接 ngrok sidecar，並在實際帳號／主機驗證可用性。

本輪實測 project 為 `fucheng-docker-preview-20260926`，原生 8052 app 停寫後，以 SQLite Backup API 與媒體 tar 製作完整備份（DB SHA-256 `0268aa8196c632eca8683af7c747ed54abdbd3fcb0dda7dbcf402148416ad943`；媒體 tar `48e8883a1be701cf504ae3ec4c1f2d2584c94a35aa9f881b9a8ab23c17a88fb4`），runtime `import-backup`／`restore` 到新 volume；原 DB／5 張媒體未覆寫。新容器為 `0009_announcement_media`、165 位**合成**會員、3 則公告、5 張媒體，`integrity_check=ok`、FK error 0。Docker app／proxy 重啟後，同一 HTTPS [手機入口](https://29e0-140-116-158-107.ngrok-free.app/) 的 health、HTML、兩個資產、兩張公開公告圖片仍通過 TLS 驗證；本機可信代理的管理員登入、Secure cookie 通過，錯誤 Host 為 400、錯誤 Origin 為 403。舊管理員 session 在還原時失效，需重新登入。

週備份容器於啟動時補做台北時間 `2026-09-21 04:00` 到期備份，DB SHA-256 `047e60db373e4302992b22f74786be24845f563c548ca371b904bcde0da6fdc7`，DB／媒體 hash、完整性、FK 與 `backup-health` 通過；`operate.ps1 ExportBackups` 的 archive／成員 hash 驗證通過。另以 `fucheng-docker-restore-20260926` 全新 volume 實走 `import-backup`→`restore`→`inspect`，並以 `operate.ps1 ImportBackup/Restore` 再驗一份匯出 checkpoint。8052 僅綁 localhost，app 沒有 host port；8044 listener 與六個 NeuroAI 容器仍在。本輪沒有真實名單匯入、球館主機測試、Cloudflare Turnstile 正式金鑰或正式部署。合成原資料、備份與兩個新 volume 保留供核對，測試用第二 ngrok 容器已移除。

## Linux 使用者家目錄與公開安全（部署參考）

本節是 Docker／Linux 交付設定，**尚未部署到正式服務或球館主機**。2026-09-26 獨立 8052 合成預覽改由已發布的 0.3.0 Docker image 提供 app／備份／本機代理，沿用原 ngrok HTTPS agent；8044、其 ngrok 及資料保持原狀。8052 缺真實 Cloudflare Turnstile 金鑰，明確為 `disabled`；下述 Cloudflare profile 仍須金鑰，缺少時拒絕啟動。公開入口維持免登入「找名字→選葷素→確認」；選名不驗證本人，也不對每筆報名加人工審核。

建議在 Linux 的服務帳號家目錄放置 `~/service/fucheng/{compose.yaml,compose.cloudflare.yaml,.env,secrets/,backup/}`。將同一 release 的 Compose 檔與 `release.env.example` 複製進此目錄，填入固定版本的 image、唯一 HTTPS origin、Cloudflare origin-network 位址及公開 Turnstile sitekey；受保護的 `secrets/cloudflare-token.txt` 與 `secrets/turnstile-secret.txt` 分別放 token／secret，不放入 Git、image、`.env` 或備份 metadata。以此目錄為工作目錄執行 `docker compose --env-file .env -f compose.yaml -f compose.cloudflare.yaml --profile cloudflare up -d --wait app backup cloudflared`。操作前要核對套件 manifest、現有 Docker project／volume／port、secret 權限及 `backup/` 對容器 UID 10001 可寫；新部署先用獨立 project／volume 合成資料驗證，不指向現有預覽或正式 volume。Docker 的 `restart: unless-stopped` 使容器在 daemon 重啟後恢復；rootless Docker 另須在該服務帳號啟用 linger 並核對 daemon 啟動。此處沒有自動安裝系統服務的腳本或球館 Linux 實機證據。

Cloudflare profile 的 app 只開 origin internal network 與 Siteverify 所需的對外 HTTPS 網路，不發布 host port；cloudflared 使用指定的唯一 proxy IP 連到 app。對外網路本身**沒有**目的地防火牆白名單，部署主機若要求只連 Siteverify，需另設 egress 規則。必須把 Turnstile widget 的允許 hostname 設為 `FUCHENG_PUBLIC_ORIGIN` 的 hostname，正式模式缺 sitekey、secret 或 HTTPS origin 會拒絕啟動。前端只在選定姓名後載入 Managed、`interaction-only` widget，使用者無須建立帳號；後端在資料庫寫入前驗 Siteverify 的 success、hostname、action 與 5 分鐘時限，3 秒連線逾時會以中文提示稍後重試。已提交且 actor／request_id／payload 完全相符的 receipt 先讀回，避免一次性 token 已消耗時重送造成重複報名。Siteverify 需真正的 Cloudflare 網域與密鑰才能驗收；本機僅使用 fake／[官方測試金鑰](https://developers.cloudflare.com/turnstile/troubleshooting/testing/) 合成驗證。[Siteverify 契約](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/)與[SPA explicit render](https://developers.cloudflare.com/turnstile/get-started/client-side-rendering/)為設定依據。

可先在 Cloudflare Free WAF 對 `/api/public/` 加一條計數規則，依實際共享 Wi-Fi 流量設寬鬆門檻，觀察 429／誤攔；再用少量自訂規則擋明顯異常路徑／方法。Free 方案目前提供 [5 條自訂規則](https://developers.cloudflare.com/waf/custom-rules/)與 [1 條 rate limiting rule](https://developers.cloudflare.com/waf/rate-limiting-rules/)；不要依賴付費 bot score、regex 或對 API 套回 HTML 的 Managed Challenge。app 自身另有重啟即清空的有限記憶體入站節流、64 個並發上限、查詢長度與 body／傳送時間上限；既有 SQLite 限流、CSRF、session、version、request_id 及稽核仍保留。共享 IP 可能碰到 429；這不是身分驗證，也不保證抵禦分散式攻擊。正式門檻應在實際流量觀察後調整，不能把合成測試當成誤攔率證據。

`backup` 容器每分鐘依 `Asia/Taipei` 曆法檢查：每週一 04:00 到期，啟動時補做一次最新漏跑週次；維護中或失敗會重試，同週已驗證成組備份不重做。`FUCHENG_BACKUP_KEEP=8` 可調，僅成功完成且 hash 可核對的 `weekly-*.db/.json/.media.tar` 成組計入並刪除超額週備份；手動、更新前、還原前及舊每日檔不受此 retention 影響。`backup/` 是 host bind，只有 backup／ops 掛載；一般 app 看不到備份。每組以 SQLite Backup API 複製 DB，再核對資料庫完整性／外鍵、媒體檔、archive hash，metadata 保存 image ref、schema、manifest hash 與公開 origin／proxy 種類，不保存 secret。管理員頁只顯示最近成功、失敗或逾期；失敗不清理已完成備份。`docker compose --env-file .env -f compose.yaml -f compose.cloudflare.yaml run --rm ops backup` 是額外手動 checkpoint，不能取代週排程。單一主機備份受同機故障影響，最壞資料損失可能接近一週；需另行規劃異地加密匯出。真正災難還原仍未在球館環境演練。

還原只經 runtime 的受鎖 `restore` 操作：驗 `.db/.json/.media.tar` 與相符 image/schema，在新目標 DB 還原、再次跑 integrity／FK、核對媒體後才切換 active pointer；舊 DB／故障資料保留，舊管理員 session 在新目標失效，稽核 actor 歷史保留。不得直接覆蓋 named volume、以舊 app 開新 schema 或把備份 bind 掛回普通 app。人工部署／切換入口、真實資料遷移、正式密鑰與外部網域均需另外的交付授權。

先前 B 公開合成預覽的 v0.2.0 [b021 管理頁](https://b021-140-116-158-107.ngrok-free.app/admin/competitions) 為歷史紀錄；本輪只確認 8044 listener，未重驗 B 的版本或完整功能。獨立的 8052 [手機合成預覽](https://29e0-140-116-158-107.ngrok-free.app/) 已於 2026-09-26 切至 Docker 0.3.0 並完成公開 HTTPS smoke；兩者資料、程序與 ngrok 彼此獨立。Docker Hub image、開發電腦的合成預覽與球館主機部署分別驗收；下列舊 PID、release 與入口記錄均為歷史證據。

## 公告媒體 schema 0009（0.3.0 已發布；以下保留原遷移約束）

舊式文末照片與新版多張內文圖片共用 0009 媒體表和成組 DB／媒體備份；內文功能未新增 migration。公開路由只供已發布且仍被公告引用的圖片讀取。

0.3.0 已包含 `0009_announcement_media` 與 `FUCHENG_DATA_DIR/announcement-media`；**尚未套到 B 公開入口或任何正式資料**。照片以伺服器檔名、最多 5 MB、PNG/JPEG/WebP 解碼後重存；DB 保存 SHA-256／大小／關聯。runtime 備份每組包含 `.db`、`.json`、`.media.tar`，metadata 存 DB 與 media 各自 SHA-256；ExportBackups 全部封存，ImportBackup/Restore 拒絕缺失或 hash 不符的媒體，還原先寫不可變媒體檔並核對 DB 指向，最後才切換 active pointer。舊 schema 備份沒有 `media_file` 時照原契約還原，但須使用與該備份 schema 匹配的 image。排程保留政策同時移除過期組的三檔。舊照片檔不立即刪除，以維持備份與併發讀取一致；容量需由資料負責人監控。

部署必須先停寫，依現有 writer/maintenance guard 做完整 DB＋媒體前備份、明確 `Migrate`、同批換新版 app/static/runtime，再驗圖片重啟可讀與獨立目標還原；不能用舊版 app 對 0009 DB 啟動。Windows 原生開發命令 `fucheng backup/restore` 只含 DB，不是這版公告照片的完整備份；要保護照片應使用 Docker runtime 的成組 Backup/ExportBackups 或等效停寫封存。2026-09-26 已在開發電腦以合成資料實走 Docker import/restore、app 重啟、週備份驗 hash 與另一新 volume 還原；未在球館主機或真實資料上演練。

### C 真實名單待執行清單（唯讀盤點；尚未匯入）

正式目標與入口仍待使用者選定：建立獨立正式 Docker volume，或將現有公開合成預覽改作正式入口。選定之前不遷移、覆寫、清理任何真實／預覽資料，也不更新公開服務。下列數字是本機來源盤點的核對目標，不是新系統已匯入的結果。

1. **核定來源與範圍。** 原 `data/fucheng.db` 為 schema 0001、327 位會員。候選 `data/club-preview.db`（0004）及 `data/club-delete-preview.db`（0005）保留原 327 位會員 ID 與共同欄位、另有 15 位會員；兩候選的共同業務資料列一致。需明定採哪一份候選作為來源，並以既有匯入決策／回執對照，預期正式會員共 **342 位**、9/20 比賽 **80 筆 confirmed 報名**。
2. **先界定排除項目。** 候選另有明確測試用途的 9/26 比賽與 1 筆報名、預覽用途的兩則使用說明公告、既有 sessions／auth attempts；不得把它們當正式資料。若新增 15 位會員或 9/20 紀錄的稽核仍參照預覽管理員，保留該 actor 的 ID 供歷史關聯但停用登入，不複製其有效 session。
3. **保全與隔離。** 核對來源與目標的當下身份、schema、hash、writer/maintenance 狀態及既有服務 owner；停寫後分別備份來源與選定目標，媒體與 DB 成組保存，先在獨立目標驗證備份可還原。不得以預覽 DB 直接覆蓋未知正式 volume，也不以舊版 app 啟動 0009 DB。
4. **執行與驗收。** 在選定目標套用 0009 與相容的新版 app/static/runtime，以白名單保留真實列的 ID、外鍵、快照與稽核關聯；驗 `integrity_check=ok`、`foreign_key_check` 無錯、原 327 ID/共同欄位相同、新增 15 ID、9/20 的 80 筆狀態／會員關聯，以及測試比賽／預覽公告／舊 session 未進正式目標。再從成組備份向另一獨立目標還原，核對 DB／照片 hash 與登入、管理／公開讀取。
5. **入口切換另行驗收。** 先完成隔離 Docker 容器的 0009 遷移、重啟、備份與回退演練；正式入口選擇、公開切換、真實資料寫入及人工驗收均須依當次授權執行。本工作樹目前只完成唯讀盤點和合成驗證，這份清單沒有任何已執行的正式資料步驟。

## v0.2.0 Docker image 與 B 預覽（2026-09-23）

Git `main` 與 `origin/main` 已到 `c9c4e0be1907cf6e6f2f2a54ffafba3ab4868e45`；annotated tag `v0.2.0` 指向同一 commit，遠端 tag object 為 `453be22bf9e2211a29016baeb0124cc4afa54717`。Linux/amd64 Docker image 位於 [`momonong/fucheng-players-system`](https://hub.docker.com/r/momonong/fucheng-players-system)，公開標籤 `0.2.0` 與 `latest` 的 OCI index digest 相同：`sha256:bf522f2646caf936fd8c4b852789ed34367f85979a867511b3f3f5a7d2f70176`。image ID 相同，source manifest 為 `b1f55e47383b81796098c602541955ecf94a8ca73d49d1fcceacdc1349c3a826`，allowlist build context 60 檔。Hub tag/API 與 `buildx imagetools inspect` 核對紀錄見 `data/deployment-release-20260923-v0.2.0/dockerhub-verification.json`。

image 以獨立 synthetic named volumes `fucheng-v020-20260923_data`／`fucheng-v020-20260923_backups` 驗證。fresh volume init 跑既有 migration 0001–0008；health、首頁、JS/CSS 靜態資產 HTTP 200，schema `0008_arrangement_grid`、18 tables、integrity `ok`、FK errors 0；重啟及 SQLite Backup API backup/verify 均通過，backup SHA-256 `2c5027a4991bd8b73c283770c90e49561fdb3721966956060eba4c25da01f3a2`。容器以 non-root UID 10001、`--network none`、read-only rootfs、無 host port 執行。容器與 named volumes 全部保留，容器目前停止；沒有清理或碰觸其他 Docker 工作負載。詳細 smoke／restart／backup 報告見 `data/deployment-release-20260923-v0.2.0/`。

Windows 原生 B 預覽另更新至 `data/grid-public-runtime/releases/grid-v020-20260923-200323`，後端來源是上列 Git commit 的 135 檔 `git archive`，前端 static 直接從同版 image 擷取。app `45460`、launcher `5908`、原 ngrok `22148` 沿用，listener 綁 `127.0.0.1:8044`；WMI/AppOnly identity guard 在更新後通過。release identity、public smoke 與資料比對見該 release 的 `release-identity.json`、`public-smoke.json`、`grid-v020-update.json`。

更新前停止 B app 後，SQLite Backup API 備份 `rollback/grid-public-before-v020.db`，SHA-256 `d581ffd34898109fed996fdba48bf41de86faefde7d9d5405980fd8880eb2aff`。啟動前後 18 張表的 row count 與 SHA-256 全相同；schema 仍為 `0008_arrangement_grid`、integrity `ok`、FK errors 0。沒有 migration、reseed、業務寫入、登入、session 清理或 ngrok 重啟。公開 HTTPS health、`/`、JS、CSS 均 HTTP 200 且 `Cache-Control: no-store`；HTML/JS/CSS SHA-256 與凍結 image static 相同。只做這些唯讀 smoke，沒有登入或測試 admin 操作；使用者人工驗收待進行。Docker image 的合成 volume 驗證與此 Windows 原生服務不是同一執行環境。

目前服務停止方式（會先核對 B app、launcher、ngrok 與 8044 身分；`-CheckOnly` 不停止程序）：

```powershell
powershell -NoProfile -File data/grid-public-runtime/stop-preview.ps1 -CheckOnly -AppOnly
```

需停止時另依已授權維護程序移除 `-CheckOnly`，並保留 ngrok／DB/session。rollback 備份與舊 source/static/helper 皆保留；不得以舊資料庫覆蓋新服務寫入，也未執行回退。E2E C3/C5 的留存 `.last-run.json` 仍是歷史失敗狀態；其四個原失敗 viewport 後有 scoped pass 證據，C6 為修正測試 locator 後的 2/2 通過。詳[驗收紀錄](acceptance.md#v020-發布驗證2026-09-23)；沒有單次全綠的完整 C 重跑。

## 前次 B grid-menu 版執行身份（2026-09-23，Windows 限定預覽）

release `data/grid-public-runtime/releases/grid-menu-20260923-102847`。凍結 identity SHA256 `8c9b8879499e52a68e52cf1b63560d1d7391a22dcfc575fe0f4eda7131cf9589`；59 source aggregate `676db4866a50700147a641331bc416917b9ee8a3835fcc3ef50fa03a61a326cf`，3 static aggregate `5dabf888c310598cd30f887e17ff1f0f489a56b78ea61451068d8d7666600b5b`。public HTML `e155fca8bf7799fd62b68e8fe979b2d1dd880b659ede00ca9e204d96446ff916`、JS `index-BHRspbMV.js` SHA256 `6ce590cb20a6d811a4d96faacdd20fadfd939453652404832875147d21d8cdee`、CSS `index-BLYowlPJ.css` SHA256 `dc36d36295c72ad7a64502f4cf3b923dba33aa7876f46be980f2e9e3d1f8f5dd`，HTTP 200、no-store；local/public health 均 JSON200。完整證據 `data/grid-public-runtime/grid-menu-update.json`。

app **46196**／launcher **39588** 分別於台北 10:29:32.137／10:29:32.102 啟動；WMI wrapper **14308**、parent WmiPrvSE **52800**。原 ngrok **22148**（2026-09-22 14:58:00.483 台北啟動）、b021／127.0.0.1:8044 沿用，沒有重啟或換 URL。AppOnly guard 在停止前、啟動後與公開核對後通過。

停止舊 B app 後 SQLite Backup API 備份為 `data/grid-public-runtime/releases/grid-menu-20260923-102847/rollback/grid-public-before-menu.db`，SHA256 `4d1f782bfca7f8ba2f1e0b9262cf65f65f83d95b6ac1e695fb2d79d9161c8454`；91 個舊 source/static/runtime/helper/log 檔保存於同一 release 的 `rollback/`，逐檔指紋見 `rollback-identity.json`。停寫備份、啟動後、公開 health/static 驗證後的 18 表 count/hash 一致；schema `0008_arrangement_grid`、integrity `ok`、FK errors 0。保留當時 2 workspace／9 versions／153 receipts（81 筆舊 receipt 沒有 undo metadata）、DB/admin/session、其他 unknown 與舊 static/releases。沒有 SQL migration、reseed、公開業務寫入或原 pending 重送／丟棄。

本版持久化 JSON 契約增加 explicit white 與 optional `header_merges`，不改 SQL schema；舊 app 不保證能解讀新版資料。若需回退，需將相符舊 source/static 與其匹配資料庫備份作為一組，先另行授權並保留故障後資料；不能只按 Alembic schema 判斷，也不能把舊 DB 覆蓋在已有新寫入的 DB 上。本次未測公開 admin UI，無現成 session；使用者需自行重整原頁載入 F。停止命令：`powershell -NoProfile -File data/grid-public-runtime/stop-preview.ps1 -CheckOnly -AppOnly`；已授權維護時才移除 CheckOnly。啟動沿用 `start-app-detached.ps1` 經 WMI，不重啟 live ngrok。未操作 A／8041／8042、Git 交付或清理。

## 前次 B shade 版執行身份（2026-09-22，Windows 限定預覽）

release `data/grid-public-runtime/releases/grid-shade-20260922-222334`，58 source 摘要 `ce1d6c8b068af44d8868701b22ed4373c997a51ae1094866374cb0777017c27a`，manifest SHA256 `a0f5e884eb75d140ae4490ce7b2b7209bfdb30c24bce65f3e09a99f64eccfdb2`。app **33220**／launcher **50204** 分別於台北 22:24:09.194／22:24:09.161 啟動，WMI wrapper **40792**、parent WmiPrvSE **52800**。ngrok **22148** 自 14:58:00.483 沿用，b021／127.0.0.1:8044 不變；JS `index-I2_TPn6a.js`／CSS `index-BQ87w01t.css` 及 HTML 公開 hash/health 證據見 `data/grid-public-runtime/grid-shade-update.json`。

停寫 Backup API 備份 release 的 `rollback/grid-public-before-shade.db`，89 檔舊 source/static/runtime/helpers/logs 與備份 hash 見 `rollback-identity.json`。18 表 before/after-start/after-verification count/hash 相同，schema0008、integrity ok、FK0；保留 2 workspace、7 保存版、115 receipts、原 DB/admin/session/其他 unknown 及舊 assets/releases，index 原子替換。只變更五個前端來源，後端/schema/依賴不變，無 migration/reseed/public 業務測試寫入。

本次無可沿用原管理分頁，公開 admin 互動未重測；未登入或另找 session、未重送/discard/reload 原頁。使用者「安排沒有變更」對應已合成重現的同色 no-op422 鎖場；新修正不等於原頁 pending 已解除，使用者可重整載入 E 版。停止先 `powershell -NoProfile -File data/grid-public-runtime/stop-preview.ps1 -CheckOnly -AppOnly`，另授權才移除 CheckOnly；啟動沿 `start-app-detached.ps1` WMI，不重啟 live ngrok。未操作 A／8042、Git 交付或清理；未建排程。以下 recovery 及更早身份為歷史紀錄，其事件未知敘述僅代表當時證據。

## 前次 B recovery 版執行身份（2026-09-22，Windows 限定預覽）

release `data/grid-public-runtime/releases/grid-recovery-20260922-215041`，58 檔來源摘要 `d3e03084b51b4f55846682b0848f010f5c71286795dbabfd4927e0d917a2e780`；manifest SHA256 `eec4fce900e73b5febc2f6327c5d94b981b7bd469dfb09511670c81e6390d0ea`。app **24512**／launcher **63472** 分別於台北 21:51:36.729／21:51:36.695 啟動；WMI wrapper **66852**、parent WmiPrvSE **52800**。ngrok **22148** 自 14:58:00.483 沿用，原 b021／127.0.0.1:8044 不變。新 JS `index-XIjfDQUe.js`／CSS `index-Bvc7fl3I.css` 與 HTML 的公開回應 hash、health 及完整時間見 `data/grid-public-runtime/grid-recovery-update.json`。

停寫 SQLite Backup API 備份為 release 的 `rollback/grid-public-before-recovery.db`，87 檔舊 source/static/runtime/helpers/logs 與備份指紋見 `rollback-identity.json`。只更新五個前端來源；後端/schema0008/依賴不變，無 migration/reseed。18 表前後 count/hash 相同，原 DB/admin/session、未大存安排、所有舊 assets/releases 保留，index 原子切換。無可沿用的原管理分頁，因此本次公開 admin 互動未重測，未登入、掃描其他 session、reload、重送或 discard 原 unknown；原事件根因與結果仍未確認。

停止先用 `powershell -NoProfile -File data/grid-public-runtime/stop-preview.ps1 -CheckOnly -AppOnly`，另獲授權才移除 CheckOnly；重新啟動仍經 `start-app-detached.ps1` 的 WMI，不重啟 live ngrok。回退須另獲授權並核對當時資料與版本，不用舊 DB 覆蓋後續操作。本次未 stage/commit/merge/push、未動 A／8042，沒有新增排程或清理。以下 export 等身份為歷史證據。

## 前次 B export 版執行身份（2026-09-22，Windows 限定預覽）

release `data/grid-public-runtime/releases/grid-export-20260922-173559`，58 檔來源摘要 `8c1c694bb5269a498f65340df75e854c8ffac9f70442f2b929ad8c322e21c274`。app **34072**／launcher **46404** 分別於 17:36:17.793／17:36:17.757（台北）啟動；ngrok **22148**／b021／8044 保持不變。WMI wrapper **27496** 的 parent 為 WmiPrvSE，跨工具與 smoke 後 guard 通過。公開 JS `index-Dk9E5fFa.js`／CSS `index-PNa2NX9l.css`，完整 hash、HTTP、程序時間見 `data/grid-public-runtime/grid-export-update.json`。

停寫 Backup API 備份為 release 的 `rollback/grid-public-before-export.db`，86 檔舊 source/static/runtime/helper/logs hash 見 `rollback-identity.json`。backend/API/schema0008 沿用；新增前端依賴已包含在凍結 bundle，未重建或安裝後端依賴，無 migration/reseed/未知重送。保留原 DB/admin/session、舊 assets 與 releases，原子替換 index。停法為 `stop-preview.ps1 -CheckOnly -AppOnly`，另獲授權才去除 CheckOnly；啟動沿用 `start-app-detached.ps1` 經 WMI，不重啟 live ngrok。本輪只更新預覽，未 stage/commit/merge/push、未操作 A／8042。以下 panels 等身份為歷史證據。

## 前次 B panels 版執行身份（2026-09-22，Windows 限定預覽）

release `data/grid-public-runtime/releases/grid-panels-20260922-164146`，57 檔來源摘要 `988a05d8bc620ec8bfe4909ccf88d8a96e460e0fee08c4db6d6d6c82b9c93cc0`。app **12780**／launcher **6996** 分別於 16:42:11.716／16:42:11.682（台北）啟動，ngrok **22148**／b021／8044 不變；WMI wrapper **30144** 的 parent 為 WmiPrvSE，跨工具與 smoke 後 guard 通過。公開 JS `index-DGQG1ehm.js`、CSS `index-DakIpyZL.css`；完整來源／資產 hash、HTTP 與程序時間見 `data/grid-public-runtime/grid-panels-update.json`。

停寫 Backup API 備份在 release 的 `rollback/grid-public-before-panels.db`，84 檔舊 source/static/runtime/helper/logs hash 見 `rollback-identity.json`。只變更三個產品前端來源，backend/API/schema/deps 與 header 版一致；無 migration、reseed、未知請求重送或業務寫入。保留原 DB/admin/session、舊 assets 與歷次 release，index 原子切換。停法仍為 `stop-preview.ps1 -CheckOnly -AppOnly`，另獲授權才移除 CheckOnly；啟動仍由 `start-app-detached.ps1` 經 WMI，live ngrok 不重啟。以下 header／undo 身份為歷史證據。

## 前次 B header 版執行身份（2026-09-22，Windows 限定預覽）

release `data/grid-public-runtime/releases/grid-header-20260922-161245`，57 檔來源摘要 `9f4a1839f073951a69dd131aedf45be704ceb0f466804e675124684bc0d63d11`。app **53896**／launcher **67372** 分別於 16:13:07.911／16:13:07.875（台北）啟動；ngrok **22148** 自 14:58:00.483 沿用，b021／127.0.0.1:8044 不變。WMI wrapper **43256** 的 parent 為 WmiPrvSE，跨工具呼叫與 smoke 後 guard 通過。完整時間、hash、公開 HTTP 及 WMI 身份見 `data/grid-public-runtime/grid-header-update.json`。

停寫 Backup API 備份在 release 的 `rollback/grid-public-before-header.db`；舊 source/static/runtime/helpers/logs 的 82 檔 hash 見 `rollback-identity.json`。公開 JS `index-6EzVBfUD.js`／CSS `index-BEIp3IaC.css` 來自凍結 `frontend/dist-grid-header`，保留舊 assets 並原子替換 index。schema0008、DB/admin/session/全部安排保留，無 migration 或依賴變動；header_shade/shade_header 要求前後端同版，不能假設舊 app 可無損回退。

停前使用 `powershell -NoProfile -File data/grid-public-runtime/stop-preview.ps1 -CheckOnly -AppOnly`；另獲授權才移除 CheckOnly 停 B app。啟動沿用 `start-app-detached.ps1` 經 WMI 讀新 runtime.app_dir，勿重啟 live ngrok。未操作 A／8042、Git 或正式部署；本次沒有重送／清除原未知請求。以下 undo 身份為歷史證據。

## 前次 B undo 版執行身份（2026-09-22，Windows 限定預覽）

release `data/grid-public-runtime/releases/grid-undo-20260922-152840`，57 檔來源摘要 `95e65ef5ed6d10bf5eebea8dc9e175ed3f272f1e3e8a170c15e66faeeffb3c3b`；app **24292**／launcher **60616**，ngrok **22148** 原程序與 b021／127.0.0.1:8044 不變。新成品為 `frontend/dist-grid-undo`，公開 JS `index-DctYxroS.js`、CSS `index-CQDIqcMj.css`；3 檔完整 hash、HTTP／Cache-Control 及 WMI 身份見 runtime 的 `grid-undo-update.json`。舊 assets 保留，index 以原子替換切換。

停寫備份為該 release 的 `rollback/grid-public-before-undo.db`；同目錄保留舊 source、static、runtime、啟停腳本及日誌，清單見 `rollback-identity.json`。沿用 `data/grid-public-preview.db`、schema0008、admin/session 與未大存安排；新 backend/front 必須同批。舊 receipts 無私有 metadata 可讀但不可 undo，不補造；舊 backend 不理解局部色／undo，不能因 schema 相同就無損回退，更不可用備份覆寫發布後操作。

守門沿用 `powershell -NoProfile -File data/grid-public-runtime/stop-preview.ps1 -CheckOnly -AppOnly`。另獲授權後才移除 CheckOnly 停 app；啟動使用 `powershell -NoProfile -File data/grid-public-runtime/start-app-detached.ps1`，由 WMI 隱藏執行既有 start-app，讀取 runtime.app_dir，保持 live ngrok。此次 wrapper **27184** 的 parent 為 WmiPrvSE，跨工具呼叫與瀏覽器 smoke 後仍存活；不可直接以短命工具 child 啟動。沒有服務安裝、排程或開機自啟保證；未操作 A／8042、Docker／GPU、Git 提交／合併／推送或正式部署。

2026-09-20 緊湊級數表格／完整安排保存版，已於本機8039及下列新建原生HTTPS合成入口驗證，schema為0007。舊Docker／ngrok、8448／8450與r7～r10套件未升級，r11仍hold；不能直接把新原始碼接舊schema。

## 原生臨時公開預覽（2026-09-20 22:44 台北啟動）

入口：[新版安排管理](https://f9d0-140-116-158-107.ngrok-free.app/admin/competitions)。新URL由ngrok官方agent分配，與舊 `30a1-140-116-158-107.ngrok-free.app` 不同；沒有踢除其他session或購買方案。公開HTTPS只提供全新合成庫，不讀取／複製真實資料或舊volume。帳密檔 `data/arrangement-native-preview-admin.json`，不可貼入聊天、Git或日誌。

執行身份：`feat/competition-arrangement-versions`／HEAD `0970af21abf4a8761a898f06d8b4d34da8a7d341` 加未提交變更。48個應用來源SHA與已驗證task4版本相符，3個靜態檔逐檔核對後複製到 `data/arrangement-native-runtime/static`，沒有重建原成品。身份記錄 `identity.json`，**沒有新image或r11包**。資料 `data/arrangement-native-preview.db` 是以 `scripts/create_level_preview.py --variant arrangement-native` 新建的0007；建立腳本拒絕覆寫已有DB／帳密／備份／還原檔。基準在合成首次合法1→3前同交易建立，實際時間22:43:31；不是遷移補造歷史。初始Backup API備份及新目的地還原檢查通過。

ngrok可攜版3.39.11取自[官方Windows下載頁](https://ngrok.com/download/windows)，Authenticode為Valid、簽署者ngrok Inc.；exe SHA256為 `d339bcbd0713233337e860163f5249eea679cf26750a5700510dbc241d201748`。只置於ignored `data/arrangement-native-runtime`，沒有全域安裝。私有ngrok.yml僅讀取既有本機token建立，web inspector、流量檢查、remote management與update check關閉；設定／日誌目錄及admin檔ACL限目前使用者與SYSTEM。

邊界：uvicorn `--host 127.0.0.1 --port 8041 --no-proxy-headers --no-access-log`；`FUCHENG_PUBLIC_ORIGIN=https://f9d0-140-116-158-107.ngrok-free.app`、`FUCHENG_TRUSTED_PROXY=127.0.0.1`、`FUCHENG_PROXY_KIND=ngrok`、`FUCHENG_COOKIE_SECURE=true`、`FUCHENG_LOCAL_HTTP_PREVIEW=false`。app要求精確Host／寫入Origin及CSRF，僅解析ngrok所附XFF／XFP。此為**本機程序信任邊界**：同機127.0.0.1程序可扮演代理，不具Docker private ingress network隔離；未開LAN listener或public debug。正常公開TLS與瀏覽器驗收通過，沒有略過憑證驗證。

執行／停止身份由 `data/arrangement-native-runtime/runtime.json` 記錄：ngrok PID50144、app listener64348、launcher60996。程序均隱藏啟動；目前日誌為同目錄 `ngrok-assigned.stdout.log`／`ngrok-assigned.stderr.log`、`app-final.stdout.log`／`app-final.stderr.log`；初次及恢復嘗試日誌保留。使用README的 `stop-preview.ps1 -CheckOnly` 核對，再執行同腳本停止；不殺全部Python/ngrok、不動8037／8039、不刪DB。這是臨時程序，關機／程序退出／ngrok限制會使入口不可用，沒有自動重啟或排程。再次啟動前須重新核對來源、port、ngrok URL及精確Origin；不可盲目重放舊PID或恢復舊Docker容器。

公開API安全證據 `security.json`、兩次保存及歷史證據 `browser-evidence.json`／`data-verification.json`、資源保護核對 `protection-final.json` 均在同runtime目錄。這次只改README／驗收／部署文件及合成建立腳本variant；沒有stage、commit、merge、push、worktree、正式部署或共用Docker/GPU操作。r11遷移及image/volume回退演練仍未執行，下節接續命令受hold約束。

收尾依使用者最新指定，僅更新上述合成庫的 `admin`，最終使用既有hash_password的正常12字元規則與隨機salt，並撤銷該admin所有舊sessions。過程曾套用短密碼，該例外已取消；舊密碼401，定向session測試在撤銷前200／撤銷後401，新登入200、管理讀取200、登出204，Secure／HttpOnly／SameSite不變。原管理員與歷史actor保留，ignored帳密檔已更新；最終證據 `admin-rotation-verification.json`，先前fixture證據已標示superseded。

22:54:49台北的共用owner狀態由main／orchestrate轉達：Docker Desktop已恢復，舊府城ngrok app／backup／ngrok及portable app／backup已由owner依其他授權停止至exited；原生8037／8039／8041／ngrok未動。本task沒有再probe或操作Docker；此回報不解除Docker hold，舊容器暫不重開。下方14:34不可用記錄是歷史阻礙。

23:09恢復紀錄：初次8170入口的三個原生程序在後續回合已不存在，根因尚未確認，main與shared owner均表示未停止。免費ngrok拒絕指定重用8170（ERR_NGROK_313），因此重新分配目前f9d0入口，app精確Origin同步更新。僅恢復本task程序；舊8037／8039亦未觀察到listener，但本task未重啟或停止它們。背景程序已跨啟動shell結束存活，沒有建立排程／開機服務。原80人功能驗收在8170完成；來源／DB／static沿用，新入口只補正常TLS登入與舊session失效驗證，不重跑功能。

### 0006 → 0007 接續升級及回退

0007僅新增不可變arrangement_versions結構，不回填歷史基準。首次合法編輯POST或第一筆直接調級才保存實際當下名單；migration不捏造時間、編輯者或舊安排。合成0006全舊表逐欄保留、DDL失敗回滾、升級前／後backup與新目標restore、integrity／FK已由本輪Python測試驗證，未套用到舊服務。

部署方須依既有runtime契約停寫→備份→明確migration→以匹配新schema的image啟動；啟動不自動migration，maintenance/writer鎖不得繞過。更新前保存原image身份及0006備份。若要回退，停止新writer，使用舊image＋pre-update備份Restore到**新target**，保留原0007故障／更新後DB及版本歷史，不執行downgrade或直接覆寫volume。回退不會把更新後的新版本搬回0006，應將其保留供核對。

source_files allowlist的`src/fucheng/*.py`、`migrations/versions/*.py`、`frontend/src/**/*.ts(x)`涵蓋新arrangements.py、0007及前端controller／表格。要重新build fresh staging／manifest與image，不沿用r10來源hash或把本機dist塞入image。不得包含data／帳密／備份／參考圖片。`scripts/deployment_drill.py`舊0005情境是歷史演練，不能當成本輪0006→0007 image/volume回退證據；部署task需以實際舊image和新image做本輪隔離演練。

2026-09-20 14:34（台北）部署接續暫停：Docker Linux Engine 查詢先回 API 500，兩次後續 version 查詢均回 `Docker Desktop is unable to start`。正常 TLS 公開 health 為404、8448連線逾時、8450讀取逾時；8039原生預覽health200。沒有執行build、停服務、migration或改私有env，不自行重啟共用Docker／WSL；由main協調恢復。來源48檔allowlist已核對新檔存在／刪除hook排除，尚未建立r11 image。只讀核對既有ngrok合成0006 checkpoint的SHA256、integrity、FK及3會員／1場／2報名通過，不能冒充目前線上資料快照。

新 `scripts/deployment_arrangement_drill.py` 已備妥，**僅通過語法與CLI help檢查，尚未執行Docker演練**。它拒絕既有演練資源，在network none／無host port的獨立volume以r10還原合成checkpoint，驗證服務中migration拒絕、新舊schema不匹配拒啟動、0007遷移全舊表保留／版本表為空，透過容器loopback API寫baseline／調級／保存，再以r10還原0006 pre-update至新target並核對原0007與後續寫入保留。此loopback API不是公開TLS證據。成功停止僅自己建立的演練server，保留volume及容器；失敗保留證據，不能盲目重跑。

以下為保留的Docker接續命令；**目前禁止執行**。須由main明確解除共用Docker hold，再核對原服務／空閒名稱及當時授權後才能依序接續：

```powershell
$env:PYTHONUTF8='1'
uv run --locked python scripts/deployment_package.py build data/deployment-release-20260920-r11
uv run --locked python scripts/deployment_package.py export data/deployment-release-20260920-r11
uv run --locked python scripts/deployment_arrangement_drill.py --new-release data/deployment-release-20260920-r11/release.json --synthetic-checkpoint data/deployment-ngrok-r10-evidence-20260920/manual-20260920T030501454562Z-2de5c494.db --synthetic-credentials data/deployment-ngrok-evidence-20260920/synthetic-admin.json --evidence data/deployment-arrangement-drill-20260920-r11
```

預定新演練project為`fucheng-arrangement-drill-20260920-r11`；截至暫停尚未查得可用daemon確認此名稱，腳本執行前會重新檢查，不能宣稱已建立資源。演練通過後才為原ngrok project做**新的**正常備份、停app／backup、new ops migration（自動pre-update checkpoint／maintenance guard）、舊表及新schema驗證，再啟new app／backup。不得因已有離線checkpoint而略過真正升級前的備份。最後另做公開TLS桌面／手機尺寸與兩次大存歷史驗收，更新文件與證據；以上仍未執行。

本階段交付是**本機已驗證、可搬至球館的部署套件**。正式架構是一個 app image，內含 React 靜態成品及 FastAPI，SQLite 存獨立 named volume；備份與維護復用 app image。Cloudflare named tunnel 直接連 app；nginx 僅供本機 HTTPS 測試，不是正式必要層。不增加 PostgreSQL、Redis 或常駐 Node，不更換 Windows。

本機合成驗證不等於球館實機、正式資料或人類驗收已完成。下節記錄先前ngrok合成預覽。當時級數／部署成果已推送至 `289be6c`，r10為未提交snapshot；其後r10前階段成果已整合至目前main／本工作分支起點 `0970af2`。目前33個dirty paths屬緊湊表格／安排保存及部署接續，仍未提交、合併或推送，未搬移正式資料或發布registry。

## 已授權的 ngrok 公開合成預覽（2026-09-20）

遠端筆電的localhost不是服務主機，因此另建立 **https://30a1-140-116-158-107.ngrok-free.app/**。這是公開合成驗收環境，沒有真實會員資料；不是將8450 local-http模式接上Tunnel。最初以r9建立project `fucheng-ngrok-preview-20260920`、volumes `_data`／`_backups`，本輪只更新app／backup至r10，沿用原資料與網路。獨立origin `172.30.106.0/24`與egress網路、ngrok容器均保持；app不發布host port、Secure cookie與精確Host/Origin/CSRF/session維持，trusted ngrok peer為`172.30.106.3`。

原本機ngrok配置含可用authtoken，只讀取並複製到ignored的本次secret檔，沒有修改原設定。沒有發現本機既有ngrok process/container；帳號其他主機session未枚舉，沒有停止其他session。設定關閉agent web UI、request inspection、remote management與update check。未購買方案、保留付費網域或修改帳號付費設定。

私有運行設定：`data/deployment-ngrok-evidence-20260920/release.env`、`ngrok-secret.yml`；合成帳密：同目錄`synthetic-admin.json`。以上不加入Git/image/離線包，勿將token或密碼貼到聊天。只初始化3位合成會員與1個2099年合成場次，未從其他資料庫複製。

CUA IAB已實測首頁、管理登入、儲存合成會員及登出；main與orchestrate亦核對首頁可見合成比賽。首次可能有ngrok自己的Visit Site提示（orchestrate實見ERR_NGROK_6024），這不是瀏覽器TLS警告；本task沒有使用skip header或略過TLS驗證。公開API使用正常TLS驗證，HTTP入口307導向同域HTTPS。

r10 公開 IAB 另驗證先填原因、滑鼠拖曳、自動儲存、重開讀回與操作歷史；手機 390×844 尺寸點選移動／已儲存撤回成功，長按沿用既有 trusted touch E2E，未取代實體手機驗收。保留 3 會員／1 場／2 報名，僅新增三筆驗收調級稽核；會員及快照不變，合成甲當次級數最終為 6。換版前後所有資料表 hash 相同，無 migration／reseed；驗收後逐欄比對亦只包含預期調級與登入紀錄。

本輪套件 `data/deployment-release-20260920-r10/` 身分：

- image：`local/fucheng:snapshot-b7a6f33e2b8e4777`；ID `sha256:66c085ef0d95f42d7f63007290d741961bb4b75e824c12e36cafe9cd8e726bf9`。
- source manifest SHA256：`b7a6f33e2b8e477732cc0265094557c51852670798541146bf2a79ccd3df3602`；47 個允許的 context 檔案，含三個新前端模組與 manifest。
- `fucheng-images.tar` SHA256：`51ac531570d655d0f3f535bd79c55e2475c05b5c537b2eede957712316d47964`。起始 HEAD `289be6c` 不代表全部未提交來源；原包 r7～r9 保留且 checksum 通過。

更新前先以 r9 runtime 正常 Backup，正常停止本 project 的 app／backup，再 Backup 留下停寫 checkpoint `manual-20260920T030501454562Z-2de5c494.db`（SHA256 `473c6316a7d826541ffa797d58d78ff0dd01f47a5a72566c1e1862af0dbc9db3`，revision 0006、integrity ok）。它在原 backups volume，另複製至 ignored `data/deployment-ngrok-r10-evidence-20260920/`；舊 env 為同目錄 `release-r9.env`。正常 compose up 只替換 app／backup，serve 仍經 writer.lock 與 schema guard，未觸碰 ngrok／其他服務。

若需回退，另依授權停止此 project 的 app／backup，先用 runtime Backup 保存後續寫入，再將目前 release.env 的 image 改回保留的 r9 tag，使用 r9 套件 `up -d --no-deps --wait app backup`；schema 相同可沿用原資料，不能直接覆蓋 DB。只有確需資料回復時，才走 runtime Restore 指定 checkpoint 至新目標並保留故障庫／後續寫入。此次未執行回退。完整更新及瀏覽器證據在 `data/deployment-ngrok-r10-evidence-20260920/final.json`。

服務主機、Docker daemon、app與ngrok容器必須持續運作且可連網；關機、休眠、斷網、帳號限制或停止容器都會令網址不可用。網址已寫入本次ngrok配置與精確public origin，但不保證永久保留或未登入冷開機自動恢復。若ngrok拒絕重啟或改配網址，先停止該preview並重新核對origin，不放寬Host。

立即关闭公網（保留app與資料）：

```powershell
docker stop fucheng-ngrok-preview-20260920-ngrok-1
```

停止整組本次環境，保留volumes，不影響8032～8035、8448、8450：

```powershell
powershell.exe -NoProfile -File D:\projects\fucheng-players-system\data\deployment-release-20260920-r10\operate.ps1 Stop -EnvFile D:\projects\fucheng-players-system\data\deployment-ngrok-evidence-20260920\release.env
```

來源契約：[ngrok v3設定](https://ngrok.com/docs/gateway/agent/config/v3)、[upstream headers](https://ngrok.com/docs/gateway/endpoints/http#upstream-headers)。首次建置證據為`data/deployment-ngrok-evidence-20260920/ngrok-final.json`；本輪更新以`data/deployment-ngrok-r10-evidence-20260920/final.json`為準。

## 套件與現場最短步驟

本輪套件位於 `data/deployment-release-20260920-r10/`：`fucheng-images.tar`、`release.json`、`SHA256SUMS.txt`、逐檔 source manifest／snapshot ZIP、Compose、PowerShell helpers及本手冊。它包含未提交的拖曳與自動儲存前端，是 **working-tree snapshot**；HEAD 並不代表全部來源，應以 image ID 和 manifest SHA256 識別。套件不含會員資料、帳密、Tunnel token、TLS私鑰或備份。

將整個套件搬到球館本機，例如 `C:\Fucheng\releases\<snapshot>`；不要放 OneDrive／網路磁碟。Docker Desktop／WSL 是主機前置需求，不含在 image 包，也沒有自動安裝、重啟或更改登入策略。先只驗空白／合成安裝：

```powershell
Set-Location C:\Fucheng\releases\<snapshot>
.\preflight.ps1 -Output .\host-preflight.json
.\load-images.ps1
Copy-Item .\release.env.example .\release.env
# 編輯release.env：image複製release.json；本機測試先設定：
# COMPOSE_PROJECT_NAME=fucheng-site-test
# FUCHENG_PUBLIC_ORIGIN=https://localhost:8447
# FUCHENG_PROXY_KIND=local
# 檢查172.30.98.0/24不與LAN/VPN/Docker衝突，必要時連同APP/PROXY_IP修改
$release = Get-Content .\release.json -Raw | ConvertFrom-Json
.\test-tls.ps1 -Image $release.image
.\operate.ps1 Init
.\operate.ps1 Admin -Value <管理員帳號>
.\operate.ps1 StartTest
.\operate.ps1 Status
```

密碼由互動終端私下輸入，至少12字元，無預設帳密；不要放命令列、環境變數或聊天。開啟 `https://localhost:8447`，自行簽署憑證只供本機合成測試；瀏覽器若顯示憑證警告，由操作人員確認本機網址後自行決定是否接受該頁例外，agent 不代為略過，也不加入全機信任。測試入口同時綁127.0.0.1與[::1]，不綁LAN或任意介面；網址必須與 FUCHENG_PUBLIC_ORIGIN 完全一致，不能直接換成IP網址。若瀏覽器顯示連線拒絕，分別以 `curl.exe -4 -k https://localhost:8447/` 與 `curl.exe -6 -k https://localhost:8447/` 診斷兩條路徑；curl 的 `-k` 僅為測試自簽TLS連線，不代表瀏覽器已信任憑證或已通過人工驗收。

已驗Windows內建PowerShell5.1及開發機PowerShell7。若主機限制執行本機腳本，先核對套件來源與SHA256，再於此次執行使用 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\operate.ps1 Status`（其他helper同理）；不修改全機execution policy。Start系列有90秒等待上限，逾時應查Logs與Status，不表示服務已就緒。

`load-images.ps1` 先核對套件逐檔 SHA256，load後核對每個image ID。可攜Compose使用保存的本機tag，全部 `pull_policy: never`，啟動不安裝依賴／暗自pull。包內有app、Cloudflare、ngrok及**可選测试**nginx；只啟動所選profile，並非四個正式必要服務。

## 僅限本機的合成 HTTP 預覽（獨立 opt-in）

使用者已另行授權本機 HTTP 預覽，供 IAB 不信任自簽 HTTPS 憑證時檢視合成資料。正式部署仍強制 HTTPS／Secure cookie，8448 HTTPS 預覽仍獨立保留；不修改憑證信任或瀏覽器驗證。本預覽不是正式部署，禁止放真實會員資料。新增套件為 `data/deployment-release-20260920-r9/`，r7/r8原交付保留。

此模式使用獨立 `compose.local-http.yaml`，不得與正式 Compose 合併。只有 app／ops，沒有 Cloudflare、ngrok 或代理；直接發布 app 的 IPv4 `127.0.0.1` 及 IPv6 `[::1]` loopback。Docker Desktop 對 internal-only bridge 不發布 host port，因此用獨立普通 bridge；它不提供出站隔離，不表示可以啟公網 Tunnel。入口不綁 LAN，應用拒絕所有 forwarding headers。

```powershell
Copy-Item .\local-http.env.example .\local-http.env
# 填入release.json的image、新的FUCHENG_HTTP_PROJECT與空閒FUCHENG_HTTP_PORT
.\local-http.ps1 Init
.\local-http.ps1 Admin -Username <合成管理員>
.\local-http.ps1 Start
.\local-http.ps1 Status
# 使用 http://localhost:<FUCHENG_HTTP_PORT>/
.\local-http.ps1 Stop
```

`FUCHENG_LOCAL_HTTP_PREVIEW=true` 必須搭配 http loopback origin、`proxy_kind=local`、無 trusted proxy、`Secure=false`，其他組合啟動失敗。精確 Host、每次寫入的 Origin、管理 session 及 CSRF 照常驗證。管理 cookie 為 `fucheng_http_preview_session`，訪客 cookie 為 `fucheng_http_preview_visit`，與 HTTPS 舊 cookie 名稱隔離，因為 cookie 不依 port 隔離。

Init 只接受新空白合成 volume，寫入 `local-http-synthetic.json`；未標記 volume 不得用 HTTP 啟動，已標記 volume 不得用 HTTPS 部署。HTTP 模式不提供匯入、還原或 migration；需要重新建立不同版本合成預覽時另用全新 project，舊 volume 保留待授權清理。不能用此模式接入真實備份。

本次可檢視入口 `http://localhost:8450/`，project `fucheng-http-synthetic-20260920`，volumes 同名前綴 `_synthetic_data`／`_synthetic_backups`。只建立3位合成會員、1個2099年合成場次；合成帳密在 ignored `data/deployment-http-evidence-20260920/synthetic-admin.json`，不放套件與聊天。實際 CUA IAB 已驗首頁、登入、儲存合成會員、比賽管理及登出；API另外驗兩個真實合成 session 同 jar 共存、HTTP登出不影響HTTPS、雙向token不可交叉認證。這不是正式環境或人類接受成果的證明。

此開發機停止命令（保留資料）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\projects\fucheng-players-system\data\deployment-release-20260920-r9\local-http.ps1 Stop -EnvFile D:\projects\fucheng-players-system\data\deployment-http-evidence-20260920\local-http.env
```

## 主機前置與常開責任

preflight只讀取Windows build／RAM／虛擬化與Hypervisor／磁碟／WSL／Docker server與Compose／測試port／LanmanServer／睡眠設定，不修改系統。Hypervisor運作時CPU的virtualization／SLAT欄位可能無法直接顯示true，不能只看單欄判斷。另須人工核對LAN/VPN/Docker subnet。

按 [Docker Windows官方需求](https://docs.docker.com/desktop/setup/install/windows-install/) 核對WSL≥2.1.5、受支援Windows、RAM、SLAT／BIOS virtualization、WSL2 feature及LanmanServer。球館照片僅支持Ryzen5 5600GT／16GB／Win11 Pro25H2與磁碟資訊，其餘未實查。本機證據是Docker Desktop4.50.0／Engine28.5.1／Compose2.40.3／WSL2 linux amd64，不能冒充球館已就緒。

Docker Desktop [啟動設定](https://docs.docker.com/desktop/settings-and-maintenance/settings/) 是「使用者登入時啟動」；[Windows helper](https://docs.docker.com/desktop/setup/install/windows-permission-requirements/) 不保證WSL2 daemon無人登入開機恢復。[unless-stopped](https://docs.docker.com/engine/containers/start-containers-automatically/) 只在daemon運作時有效，人工停止的容器不會自動恢復。

現場須指定重啟後登入／檢查的負責人，驗Windows更新重啟、睡眠、斷電復電、斷網恢復。若要求完全無人值守24小時，交main另行確認啟動策略；不自行設定自動登入、更換OS或宣稱已達成此可用性。

## 持久化與互斥

同一 `COMPOSE_PROJECT_NAME` 對應 `<project>_data`、`<project>_backups`。app為UID/GID10001、唯讀root filesystem、單一Uvicorn worker，只有data/backups/tmp可寫；無debug/reload/access body log。各服務log rotation為10MB×3。app無host port，origin network為internal；SQLite不開網路port。

`/data/active.json` 指向實際DB；DB/WAL/SHM留在同一Linux named volume，禁止live DB放SMB/NAS/OneDrive。應用連線維持foreign_keys=ON、busy_timeout=10000、WAL、synchronous=FULL。不得直接複製正在寫入的DB主檔充當一致性備份。

writer.lock涵蓋整個serving生命週期與所有維護寫入，阻止兩個版本共寫及服務運作時migration。Start只驗image Alembic head與DB revision一致，**不自動migration**；未初始化、schema不符、maintenance.json未清除都拒絕啟動。health驗HTTP及revision；啟動／備份／遷移／還原另做完整integrity/FK驗證。不得繞過入口直接用Alembic/CLI寫volume。

```powershell
.\operate.ps1 Status
.\operate.ps1 Logs
.\operate.ps1 Stop       # 此project所有入口／app／backup，不刪volume
.\operate.ps1 Start      # app+backup，尚無公開入口
.\operate.ps1 StartTest  # 合成HTTPS測試
```

一個project只選一個ingress profile，三者共用明確代理IP，不可同時開啟。禁止prune／down -v／任意刪volume。更換release時沿用project名，避免誤建空白庫。

## 一致性備份、離機交付與還原

backup sidecar復用app image，啟動後立即Backup API備份，預設每86400秒一次、保留最近14個 `scheduled-*`；手動／pre-update／pre-restore／exports不自動刪除，須按容量管理。這是14次成功備份，不是保證14個日曆日，停機不補跑。keep至少2、interval至少5秒；本機演練用5秒／2份，正式設定保留範例值。

先以Backup API寫.partial，僅將該備份副本的journal轉為DELETE，驗integrity/FK，再完成單一.db與SHA256 metadata；live DB仍使用WAL。ImportBackup先驗來源hash，再複製獨立.importing暫存於可寫備份volume驗證，不以immutable忽略WAL；來源若有WAL/SHM就拒絕。Restore核對metadata/hash，內部已匯入備份的連線允許SQLite收回空白輔助檔，還原後再次確認來源bytes未變。`/data/backup-status.json` 保存成功／失敗；失敗stderr為BACKUP FAILED，health轉unhealthy。未配置外部通知，現場負責人須定期看Status/Logs，不能把unhealthy當已寄出通知。

```powershell
.\operate.ps1 Backup
.\operate.ps1 ExportBackups -Value E:\FuchengBackups\<新的時間戳目錄>
```

Export持有backup.lock，先建checkpoint，再把**已完成**DB/metadata封存到独立exports tar，排程retention不影響該封存。Windows端驗tar SHA256，解開後逐檔再驗；失敗停住並保留材料，不覆寫既有目的地。備份含會員、管理員密碼雜湊及session，須保護裝置/權限；加密方式、保管人及第二地點由資料負責人指定。**同磁碟副本不是離機／異地備份**，本輪未購買儲存或上傳真實資料。

restore drill使用新project／新volume，把已驗備份放/backups，再 `Restore -Value <filename.db>`。必須使用與備份schema一致的image；restore永遠寫新DB再切pointer。驗登入、會員、比賽／正取／候補／取消、級數與稽核，不把測試目標指向舊DB覆寫。

### 從離機副本取回，全新volume還原

需獨立套件目錄，不需原repo／uv／npm。先load-images並將release.env的project改成從未使用的新名稱，例如fucheng-restore-drill；origin/proxy/subnet也按新測試入口設定，不與舊project重疊。**不要先Init**，由Restore建立active pointer。

```powershell
# E:是已取回、解開且有DB及同名.json的一組備份；不要直接掛正在寫入的DB
$backup = 'E:\FuchengBackups\<timestamp>\manual-export-<timestamp>.db'
.\operate.ps1 ImportBackup -Value $backup
# Windows與容器都核對DB/metadata的SHA256；目的檔已存在即拒絕覆寫
.\operate.ps1 Restore -Value (Split-Path $backup -Leaf)
$release = Get-Content .\release.json -Raw | ConvertFrom-Json
.\test-tls.ps1 -Image $release.image
.\operate.ps1 StartTest
.\operate.ps1 Status
# 用備份中既有管理員登入，核對會員／報名／級數／稽核；不用再建預設管理員
.\operate.ps1 Stop
```

若ImportBackup來源不是本工具產生的備份（缺同名metadata），先由來源端的受控備份流程補上校驗證據，不手造hash繞過來源確認。真實資料取回仍須資料操作授權。新volume保留供驗收，不自動刪除。

## 更新與回退

1. 保留舊release、image ID、project名及release.env；核對並load新版，先在合成或獲准資料副本演練。
2. `Backup` 後 `Stop` 此project所有入口/app/backup；確認無其他舊程序寫同一資料。不要停止其他專案的共用服務。
3. 新release.env填新image、沿用project/網路/入口，再 `Migrate`。取得writer+backup鎖後寫持久maintenance，先建pre-update備份，再upgrade head。任何失敗均停住並保留maintenance；不得刪標記或直接Start略過。
4. 成功後 `Start` 檢查app/backup，再按既有授權選StartCloudflare或StartNgrok。驗公開頁、登入/登出、報名、級數和稽核，再交人工接受。
5. 失敗回退保持停機，把image改回**符合pre-update備份schema**的舊image，`Restore -Value <pre-update-....db>`，再啟動。只換image不等於回退，schema不匹配會拒絕啟動。

Restore保留原DB/WAL/SHM、舊pointer與operations證據；健康原庫另建pre-restore一致性checkpoint，保存恢復點後寫入。若原庫損毀／缺失，保留現存檔案與hash，記錄「無法取得一致性snapshot」，仍可由有效備份恢復到新檔。恢復後不會自動合併更新期間資料，須核對保留庫再決定補登。沒有破壞性downgrade。

首次Init中斷且尚無active pointer時，`RecoverInit`只允許init maintenance，保留失敗檔後建立新DB。已有active pointer須用Migrate/Restore，不得重新Init。`/data/operations/*.json`供追查。

## Cloudflare named tunnel：固定HTTPS主方案（未公開啟動）

取得外部操作授權後，依[官方流程](https://developers.cloudflare.com/tunnel/get-started/)準備account、Cloudflare domain/DNS及remotely managed named tunnel。token只存現場 `secrets/cloudflare-token.txt`，限制使用者權限，不入release.env/Git/聊天/命令列。鎖定image支援[token-file](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/)（需≥2025.4.0）。

公開hostname service設 `http://app:8000`，Host保留公開hostname；release.env設 `FUCHENG_PUBLIC_ORIGIN=https://<hostname>`、`FUCHENG_PROXY_KIND=cloudflare`。app無公開port，不開router app/DB管理port；依官方文件核對對外7844。**取得公開開通授權後**才執行StartCloudflare。

Uvicorn自動forwarded parsing關閉。app先驗socket peer為指定代理IP，再採CF-Connecting-IP與X-Forwarded-Proto；Host固定、寫入必須同源Origin及既有session/CSRF。未受信來源的Forwarded/XFF/CF header拒絕；X-Forwarded-Host不作權威。依[Cloudflare header契約](https://developers.cloudflare.com/fundamentals/reference/http-headers/)確認沒有同zone Worker改寫IP或Pseudo IPv4 Overwrite等改變此語義。

正式入口仍須驗Secure/HttpOnly/SameSite、CSRF、偽造header不能改變限流、不同client IP／球館共用IP額度、外網手機與斷線恢復。代理/APM不要保存body/Cookie/Set-Cookie/CSRF。Quick Tunnel僅合成試用，隨機網址／200 concurrent requests／不支援SSE，不當固定入口，本輪未啟動。

## ngrok替代方案（未公開啟動）

使用鎖定image、compose.ngrok.yaml及ngrok.yml.example。完整設定只存 `secrets/ngrok.yml`，填authtoken及已分配HTTPS domain。web_addr=false關閉本機inspect UI，remote_management=false、update_check=false；帳號端另核對停用敏感request capture，未核對前不承載真實資料。release.env設對應origin及proxy kind=ngrok，先Stop原入口，授權後才StartNgrok。

命令依[Docker](https://ngrok.com/download/docker)、[config v3](https://ngrok.com/docs/gateway/agent/config/v3)、[CLI](https://ngrok.com/docs/gateway/agent/cli)；config check只是靜態檢查，沒有建立endpoint。依[header契約](https://ngrok.com/docs/gateway/endpoints/http)，ngrok會append XFF/XFP，app只在受信peer取**最後值**。免費方案有[流量／請求／HTML提示頁限制](https://ngrok.com/docs/pricing-limits/free-plan-limits)，自有domain及配額以現場帳號再確認，不猜價格。

## 真實資料交接：目前只讀盤點

開發端 `uv run --locked python scripts/deployment_inventory.py data/<新檔名>.json` 用SQLite mode=ro/query_only盤點revision、表筆數與列hash、受保護成品/帳密檔hash，不輸出會員列或密碼，不複製/遷移。fucheng.db、competition-case.db、club-preview.db、club-delete-preview.db與levels-preview.db等有不同來源／操作歷史；合成預覽不是正式來源。

main與資料負責人須確認唯一權威DB、各副本新增操作、附件範圍、停寫時段與匯出/搬移/切換授權。先由原服務Backup API建立一致性檔及hash，於獲准副本演練升級、逐欄保留與還原，才安排正式停寫、再次備份、搬移、遷移及切換。不可任選preview覆蓋，也不可把本套件當已含正式資料。

## 一頁現場驗收清單

- [ ] preflight、虛擬化/WSL2/Docker linux amd64、容量、subnet/port與其他服務隔離。
- [ ] SHA256SUMS/image ID/來源snapshot一致，離線load與不pull啟動成功。
- [ ] 空白/合成Init、互動Admin、StartTest；首頁/分級、登入登出、Secure cookie/CSRF。
- [ ] 桌面及現場手機：選名報名、正取/候補/取消、級數/快照獨立及稽核；人工接受另記。
- [ ] recreate持久化、排程備份healthy、故障可見、離機副本實際取回、獨立restore、更新與舊schema回退。
- [ ] 唯一真實資料來源、附件、停寫、匯出/搬移/切換授權與正式恢復點；未確認就不切換。
- [ ] named tunnel/domain/token本地設定，公開HTTPS/IP/Host信任、外網手機及斷網恢復。
- [ ] 睡眠/更新/重啟/停電復電，登入與監控責任人；無人值守需求另行決策。

待填：project名、公開hostname、入口種類、subnet/app IP/proxy IP、管理員帳號（密碼私下輸入）、唯一資料來源、備份第二地點/保管人、重啟登入責任人、人工驗收人。球館未就緒不阻止本機套件交付，但不宣告正式上線。

---

# 過往部署與預覽紀錄（歷史參考）

以下保留原階段資料來源／schema／預覽限制。Linux/systemd是舊建議，目前球館執行步驟以上方Windows Docker流程為準。

## 目錄與帳號

```text
/opt/fucheng/releases/<版本>/  唯讀程式與前端成品
/opt/fucheng/current           指向目前版本的 symlink
/opt/fucheng/venv              已鎖定的 Python 虛擬環境
/var/lib/fucheng/fucheng.db    執行資料
/etc/fucheng/fucheng.env       秘密及環境設定（0600）
/var/backups/fucheng/          備份（不在發布目錄）
```

建立專用、不可登入的 `fucheng` 系統帳號，讓 `/var/lib/fucheng` 屬於該帳號。不要使用 root 執行網站服務。先在建置機執行 `npm ci && npm run build`，把含 `src/fucheng/static` 的發布內容送到新 release 目錄；主機不需要常駐 Node.js。

安裝時以 release 目錄中的 lockfile 建立固定虛擬環境（不在 systemd 啟動階段安裝）：

```bash
cd /opt/fucheng/releases/2026-09-16
UV_PROJECT_ENVIRONMENT=/opt/fucheng/venv uv sync --locked --no-dev
install -m 600 deploy/fucheng.env.example /etc/fucheng/fucheng.env
sudo -u fucheng /opt/fucheng/venv/bin/alembic upgrade head
sudo -u fucheng /opt/fucheng/venv/bin/fucheng create-admin <管理員帳號>
```

依現場路徑修改環境檔與 service，複製 `deploy/fucheng.service` 後執行 `systemd-analyze verify`、`daemon-reload`、`enable --now`。`FUCHENG_COOKIE_SECURE=true` 不得在公開 HTTPS 環境關閉。

## 更新

1. 將新版本放入新的 `/opt/fucheng/releases/<版本>`，先建置前端並執行測試。
2. 對仍在運作的資料庫執行一致性備份：`/opt/fucheng/venv/bin/fucheng backup /var/backups/fucheng/pre-update.db --force`。
3. 從新 release 執行 `UV_PROJECT_ENVIRONMENT=/opt/fucheng/venv uv sync --locked --no-dev`。
4. 停止服務；載入 `/etc/fucheng/fucheng.env` 後，從新 release 執行 Alembic `upgrade head`。
5. 原子切換 `current` symlink，再啟動服務，檢查 `/api/health`、管理員登入及免登入報名入口。

資料庫遷移後不可假設程式 symlink 回退就等於安全回退；需要還原時使用更新前備份，並保留故障資料庫供調查。

第二階段 migration `0002_competition_registration` 只新增比賽、報名與稽核表，不重建會員表。正式資料套用前仍必須先用 Backup API 備份，再把備份還原到新路徑，在副本執行 `alembic upgrade head`、核對會員／管理員／稽核筆數與 `integrity_check`，最後才安排停機遷移正式庫。本次本機案例副本驗證不等於正式資料庫已遷移。

## 一致性備份與還原

不要把直接複製正在寫入的 SQLite 主檔當成唯一備份。工具使用 SQLite Backup API，完成後執行 `integrity_check`，再原子放置檔案。

```bash
FUCHENG_DATABASE_URL=sqlite:////var/lib/fucheng/fucheng.db \
  /opt/fucheng/venv/bin/fucheng backup /var/backups/fucheng/manual.db

/opt/fucheng/venv/bin/fucheng restore /var/backups/fucheng/manual.db /var/lib/fucheng/restored.db
```

還原先寫入新的乾淨檔案。驗證 `PRAGMA integrity_check`、資料筆數與應用程式讀取後，停止服務，再以受控的檔案切換取代正式資料庫；保留原檔以便回復。`deploy/fucheng-backup.timer` 是每日排程範例，會產生時間戳備份；另需依磁碟容量設定保留政策與異地備份。

## Cloudflare Tunnel（僅記錄，未建立）

1. 在 Cloudflare 管理介面建立 tunnel、網域及 DNS；這些是外部變更，本專案不代建。
2. 將憑證放在 cloudflared 專用秘密目錄，依 `deploy/cloudflared-config.yml.example` 填入 tunnel ID、credentials 與 hostname。
3. Tunnel 只轉送至 `http://127.0.0.1:8000`；瀏覽器看到的公開入口必須是 HTTPS，才能使用 Secure session cookie。
4. 啟用前驗證登入、登出、CSRF、來源 IP／日誌策略及 Cloudflare 存取控制需求。


## 第三階段免登入報名（正式庫尚未套用）

目標 revision 是 `0003_public_registration`，來源為 `0002_competition_registration`。舊帳號方案未提交的 revision 已撤下，只保留本機封存及舊合成預覽庫；不得直接把舊帳號版預覽資料庫交給新版服務。

1. 核對實際庫路徑、revision 及程式版本，使用 CLI Backup API 備份。
2. 還原到新路徑，在副本執行 `uv run --locked alembic upgrade head`，逐欄核對會員、管理員、比賽、正取／候補／取消、候補順序及稽核，執行 integrity_check／foreign_key_check。
3. 再次備份及還原副本，確認可回復。準備鎖定 release 與前端。
4. 取得正式部署授權後安排停機、再次備份，對正式庫套 migration，切換新版再啟動。驗證搜尋／報名、管理員取消／遞補與公開資料邊界。

Migration 用顯式 SQLite 交易保護 batch DDL，提交前檢查外鍵；出錯回滾 schema 及 revision。一般連線 FK 設定不變。不提供破壞性 downgrade，需從升級前備份還原至新檔、驗證、受控切換，同時保留故障庫；不能只回退程式。

只有管理員要登入，使用者不需帳密。正式同源入口必須 HTTPS，保留 cookie Secure=true；反向代理需正確還原 scheme／host 並只信任明確的代理來源。使用者選名字不證明本人，可能代報，錯誤由管理員更正；速率限制不能代替身分驗證。共享代理或球館網路可能共用 IP 額度，部署前確認預期流量。

systemd 範本使用 `--no-access-log`；代理與 APM 也不要保存 body、Cookie、Set-Cookie 或 CSRF。仍採 Linux＋systemd＋SQLite，沒有新增分散式服務。

合成預覽為 data/public-preview.db、8032、frontend/dist-public；只有管理員測試帳號存於 data/public-preview-admin.json。啟停命令見 README。原 8012 與原會員／9/20 案例庫保留。本次未執行正式遷移、Linux/systemd 或 HTTPS 實機部署。

## 球館網站整合版（0004_club_website）

最新 revision 為 `0004_club_website`，新增公告／公告稽核表。原始資料仍未套用新版；在授權的 `data/club-preview.db` 副本完成 0002 → 0003 → 0004、原資料逐欄保留、備份還原及 Alembic metadata check。啟停與帳密位置見 README「球館網站整合預覽」。8032 現在使用原會員副本，舊合成 `public-preview.db` 保留但不使用。

正式套用仍需另行授權：核對原庫實際 revision、備份並還原演練、停止正式寫入、套用 `alembic upgrade head`、建置／切換 release、檢查首頁、公開分級無敏感欄位、公告草稿不外露、管理員登入與比賽報名。恢復時使用更新前備份，不能只回退程式。`0004` 不提供刪除公告稽核的 downgrade。

整合預覽僅綁定 127.0.0.1；Linux/systemd、外網 HTTPS 與球館現場手機尚未驗收。原會員副本不是自動測試資料庫，不可交給 E2E 重建腳本。

## 80 人匯入後的本機預覽服務

本輪沒有新 migration，schema 保持 0004_club_website。8032 保持原程序運作，批次匯入 API 使用額外 8033 程序，兩者同為 data/club-preview.db。可在原 8032 管理頁查看 9/20 的 80 人；8033 的 PID、日誌分別在 data/roster-import.pid、data/roster-import.*.log，停止前核對程序身分。原會員與 9/20 來源庫仍不回寫，只有授權副本新增 15 會員與 80 報名。正式環境仍須另行授權部署。

## 比賽刪除版本（0005_competition_deletion）

最新 revision 為 `0005_competition_deletion`，只新增 competitions.deleted_at。既有原始庫及 8032／8033 使用的 club-preview.db 尚未套用；8034 使用獨立的 club-delete-preview.db 及 frontend/dist-delete，啟停方式與帳密位置見 README。副本完整保留 342 會員、2 場比賽與 81 報名，舊欄位逐欄一致，升級後備份還原與 Alembic metadata check 通過。

不能讓舊版服務與新版共用已升級的可寫庫：舊版不知道 deleted_at，可能顯示或接受已刪除場次的寫入。正式套用前須另行取得部署授權、備份與還原演練，安排停止所有舊版寫入、套用 alembic upgrade head、切換同一新版前後端，再驗證登入、公開時程、確認刪除與還原。不可直接啟動目前程式搭配尚未升級的舊庫。禁止以刪除欄位方式 downgrade，需還原升級前備份並受控切換。

8034 是本機試用副本，8032／8033 與它不會互相同步；後續驗收統一使用 8034，整合時先確認是否有各副本新增操作，不能任選一份覆蓋。本輪沒有停止現有服務、永久刪除比賽或修改 9/20 原始案例庫。

## 當次級數版本（0006_competition_level，僅合成資料已套用）

新增 competition_registrations.competition_level，舊列從自己的 hard_level_snapshot 回填，保留所有原欄位及稽核。0002 與 0005 合成庫升級、逐欄比對、排序、公開／管理 actor、已刪除狀態、故障 DDL rollback、Backup API 備份還原、integrity_check／foreign_key_check 及 Alembic metadata check 已驗證。這些證據不是正式資料庫已遷移的宣告。

8035 是全新合成庫 `data/levels-preview.db`，只使用 `frontend/dist-levels`，沒有讀取／複製真實名單；帳密、PID／父程序 PID 及停止前核對方式見 README。預覽建置與瀏覽器測試只有合成資料；8036 為自動測試服務，測試後退出。不得把 levels-e2e.db、預覽庫、帳密或備份放入 Git。

既有 8032／8033 保持 0004／club-preview.db，8034 保持 0005／club-delete-preview.db，各程序與成品未動。新版程式不能搭配未升級的舊庫，也不能讓舊程式共寫 0006：舊程式新增報名未填非空 competition_level，且不知道新的安排語意。需要導入正式／原會員副本時，先取得相應資料操作及服務切換授權，決定唯一資料來源，核對各副本新增操作；不能直接任選一份覆蓋。

正式切換前仍需 Backup API 備份、還原至新檔演練、逐欄保留驗證、停止所有舊版寫入、套用 `alembic upgrade head`、統一前後端版本後啟動。驗證報名三入口、當次級數隔離、正取／候補／取消、版本衝突與歷史，再開放使用。回退必須從升級前備份還原到新目的地，不能刪欄或單獨回退程式。本階段未正式部署或套用真實資料 migration。


## B 0008 本機交付邊界（2026-09-21）

B從已推送A `89cae09754eaefa4dba6c3dce308482526f33ff2` 建於唯一隔離worktree `D:\projects\fucheng-players-system-worktrees\arrangement-grid`，分支 `feat/competition-arrangement-grid`。A的8041从主目錄src/.venv載入，因此B使用自己的.venv/node_modules/DB/static，主目錄保持main，未重啟f9d0、未改密碼。B未commit/merge/push、沒有建立image、沒有操作Docker/GPU；公開B另由orchestrate安排。

B本機入口8042、schema0008、`data/grid-preview.db`與`dist-grid`。合成initial backup `backups/grid-preview-initial.db`、restore新target `data/grid-preview-restore-check.db` 驗完整性/FK/筆數一致；不得拿它覆寫A資料或稱為正式遷移證據。帳密僅 `data/grid-preview-admin.json`。測試8043/grid-e2e.db獨立且完成後退出。

後續升級須從B凍結source manifest＋static核對身份，使用獨立資料目標，明確停寫/備份後0007→0008。升級只新增layout欄與兩表，不造舊布局、不改舊歷史payload。回退使用相符A程式／0007 pre-update備份還原到新target，保留0008資料，不跑破壞性downgrade。舊Docker演練只適用其記錄版本，不能充當0007→0008容器驗證。當前已有SQLite合成migration/rollback備份驗證，但無B新image/volume演練。

B後續公開預覽不可直接讀正在改動的worktree原始碼；由接手task在停寫後凍結來源、static與新合成備份，核對清單與hash並另安排入口。現用A帳密的沿用由task5依另授權安全處理，task4不讀A私有帳密。worktree保留供驗收與後續修正，未授權清理。

## B 0008 公開合成預覽（2026-09-21）

### 目前 interaction 版執行身份

Windows 11／PowerShell 的原生 B 預覽使用 `data/grid-public-runtime/releases/grid-interaction-20260921-120352/source/src`，56 檔 production 摘要 `c00f5937c00291c58819e2630387d965a0bf3951f0ae9cb1a73c631ae30f83c2`。同一 eb24／127.0.0.1:8044，listener **45560**、launcher **41228**，取代 **45612／47980**；ngrok **57728** 的建立時間／config／URL 不變。runtime 記錄現用絕對路徑由已指定 B 工作目錄解析，文件路徑皆相對該根目錄。來源 import、公開 hash/cache、health 證據在 `data/grid-public-runtime/grid-interaction-update.json`。

停寫後 Backup API 備份為該 release 的 `rollback/grid-public-before-interaction.db`；同 rollback 保存舊 source、完整 static、runtime 與啟停腳本，hash 清單為 `rollback-identity.json`。原 DB 路徑不變、沒有 migration；新 app 啟動及公開非寫入 smoke 後各核對 18 表 hash／count 一致，admin/session／未大存安排與先前來源 UNKNOWN 操作全保留。新 hashed assets 全部寫齊後原子替換 index，舊 assets 保留：HTML `9856bb7a...`、JS `index-mlLEaVwH.js`／`a323e368...`、CSS `index-BjtxJCLN.css`／`61f594b3...`；完整值見 release 的 `delivery-identity.json`。

Windows 限定私有 helper 沿用既有流程：`powershell -NoProfile -File data/grid-public-runtime/stop-preview.ps1 -CheckOnly -AppOnly` 已對新 PID／建立時間／app-dir／父子及 port 歸屬通過。經授權只停 B app 時移除 CheckOnly、保留 AppOnly，ngrok 不動；`start-app.ps1` 從 runtime.app_dir 啟動現用凍結版本。資料比對使用 `uv run --locked python data/grid-public-runtime/grid-interaction-data-check.py smoke`。未重寫跨平台啟停、未測其他 OS，也沒有開機自啟保證。

新 swap/insert/move_empty/shade receipt 與 shade 欄位不能交舊 backend 無損處理；需要恢復時先保留目前資料，評估向前修復或受控停寫，不能覆寫成發布前備份。舊 move client 仍保持插入語義，未知結果沿用原 request_id／receipt 確認。A／8042、Docker／GPU 未操作，沒有新 worktree 或 Git 提交／合併／推送。下面為歷次發布紀錄。

### 歷次 axis 三項功能版執行身份

現用 eb24／127.0.0.1:8044 的 app-dir 為 `data/grid-public-runtime/releases/grid-axis-20260921-113513/source/src`；production54 摘要 `5abb9dd18a96aae083bcab6a5eaf62d703daa6f522537b5b317ae56fb17efc5b`，manifest 為該 release 的 `delivery-identity.json`。新版 listener **45612**／launcher **47980**，取代 32752／36224；ngrok **57728**、網址及 config 不變，A／8042 未動。`runtime.json` 與 `grid-axis-update.json` 記錄現用身份、import、HTTP hash/cache 與重啟事實；下方其他版本均為歷史紀錄。

已保存舊 source／完整 static／runtime／啟停腳本至 release 的 `rollback/`，停寫後 Backup API 備份為 `rollback/grid-public-before-axis.db`。啟動新版與完成唯讀 smoke 兩個時間點的 18 表皆與備份相同；migration、依賴及 schema0008 未改，DB/admin/session/使用者未大存安排保留。新 hashed assets 寫齊後原子替換 index，保留全部舊 assets；public HTML `ee9d65c5...`、JS `index-eRjUGez4.js`／`1f9b6e10...`、CSS `index-CaBnUpIx.css`／`3c0f4222...` 均 200、完整 hash 符合 manifest、Cache-Control:no-store。

本次停止舊 app 後 launcher 在 Stop-Process 呼叫前自然退出，守門脚本於備份前停止；確認兩個舊 PID 均不存在、8044 已釋放後才接續備份與現用版本啟動，並通過 18 表一致檢查。停止守門已補上此已知競態：只有 PID 確實不存在才接受自然退出，任何仍存活／重用 PID 都拒絕。新身份的 `stop-preview.ps1 -CheckOnly -AppOnly` 已通過；只停 B app 用 `-AppOnly`，保留 ngrok／網址，重新啟動沿用 `start-app.ps1` 讀 runtime.app_dir。沒有額外測試重啟或更換 agent。

新版 delete operations／receipts 無法由舊 backend 完整理解，不得因同為 0008 宣稱可無損退舊 app；保留目前資料，優先向前修復或協調受控停寫，不能以備份覆寫發布後操作。此次未 stage／commit／merge／push，沒有新 worktree、Docker／GPU 操作或正式資料部署。完整來源、備份及 rollback hash 清單保留於 release 的 `rollback-identity.json`。

### 歷次 grid-edit 五項功能版執行身份

同一 eb24／127.0.0.1:8044 已切換至 `data/grid-public-runtime/releases/grid-edit-20260921-110654/source/src`，53 檔 production 摘要 `eaf8d9ce6f002a89575710641bd36886c4da59812a89ec6ede17fe670b76eb48`；manifest 副本在該 release 的 `delivery-identity.json`。原 app／launcher 44424／63012 已受控停止，新 listener／launcher 為 **32752／36224**，ngrok **57728** 及其建立時間／config／eb24 不變。`runtime.json` 記錄現用身份；`grid-edit-update.json` 記錄來源 import 路徑、公開 static hash／cache、health 與啟停範圍。下方舊 PID 及來源身份保留為歷次紀錄，不代表現用 app。

先凍結來源並驗證相容、完整保存舊 source/static/runtime 至該 release 的 `rollback/`，停止 B app 寫入後以 SQLite Backup API 建立 `rollback/grid-public-before-edit.db`。原 public DB 路徑與內容保留；新版啟動沒有 migration，切換前後 18 表逐表 hash／count 一致後才寫齊新 assets 並原子替換 index。舊 hashed assets 保留。現用 index `73c019c6...`、JS `index-wYMAYkTQ.js`／`e88a10da...`、CSS `index-DOk1_exm.css`／`22d159a8...`，完整 SHA256 見 manifest。原 A／8042 完全未操作。

停止前在 B 工作目錄執行 `powershell -NoProfile -File data/grid-public-runtime/stop-preview.ps1 -CheckOnly -AppOnly` 核對現用程序；經授權只停 app 時去掉 CheckOnly、保留 AppOnly，ngrok／網址不動。不帶 AppOnly 會連 B ngrok 一起停止，僅供另行授權的整個 B 入口停用。`start-app.ps1` 已改為從 runtime.app_dir 讀取現用凍結版本，避免誤啟舊 backend，並核對／記錄新 listener；目前僅語法核對，沒有為測試再重啟。此次實際受控重啟使用 `restart-grid-edit.ps1`，該一次性腳本鎖定旧 PID，不可再次執行。沒有開機自啟或排程保證。

回退備份僅供救援與比對，不可直接覆寫使用者後續資料。舊 backend 會吞掉 title 且不支援 column_title，接受新 JSON 後不可宣稱無損回退；優先向前修復或停止受影響寫入，評估只回前端亦需相容性核對。舊分頁與未確定請求保留原 key／receipt 語意，不清 session、不替使用者大存；重新整理前如有未知操作先確認結果。切換後觀察到的新操作也已保留。此版本沒有 Git 提交／合併／推送、新 Docker image、GPU 操作或正式資料部署。

### 前次前端切換紀錄

後續 dragfix static 切換已完成，eb24／8044 與 app **44424**、launcher **63012**、ngrok **57728** 均沿用。先備份現用 static 至 `data/grid-public-runtime/static-before-drag-20260921-081027`，新 hashed assets 全數寫齊後用原子替換切換 index，保留舊 assets 供已開分頁使用。新前端 manifest 為 `data/grid-drag-delivery-identity.json`；runtime 的 `frontend-drag-update.json` 記錄公開回應 hash／cache 與 rollback。`identity.json` 的舊 50 檔摘要 `c25556fb...` 仍描述未變的凍結來源；新 frontend build 來源摘要為 `490b5aa7...`，未把新前端來源覆蓋到 frozen source，也未替換 backend／migration。回退僅在取得授權後，核對備份 index 及其舊 assets，將備份 index 以同樣原子方式還原；不回復 DB、不重啟或切換 ngrok。此次停止腳本 CheckOnly 再次通過，既有資料、admin/session、未完整保存差異保留，A／8042 不動；未 commit／merge／push。

上述本機交付後，task5 依獨立授權在 B worktree 建立第二個公開合成入口 `https://eb24-140-116-158-107.ngrok-free.app/admin/competitions`，已通過正常 TLS 登入／管理讀取及精確格位增量驗證。A f9d0／8041 與 B 原 8042 保留，兩個官方 ngrok agent 已並行；本次沒有操作 Docker 或 GPU。

執行身份以 `data/grid-public-runtime/runtime.json` 的 PID、建立時間及設定為準：ngrok **57728**、Python launcher **63012**、app listener **44424**，僅監聽 `127.0.0.1:8044`。使用 B 自有 `.venv/Scripts/python.exe`，`--app-dir data/grid-public-runtime/source/src` 指向凍結來源，`--no-proxy-headers --no-access-log`；公開 static 為同 runtime 的 `static`，資料庫為 `data/grid-public-preview.db`（0008）。來源 allowlist 50 檔與 dist-grid 3 檔的 SHA256 及初始 Backup API 複製證據見 `identity.json`；`ready.json` 已確認實際匯入凍結 app.py，並非 A 或仍可變動的 B src。

設定固定本次 eb24 HTTPS origin、可信代理 `127.0.0.1`、proxy kind ngrok、Secure cookie 開啟、local HTTP preview 關閉。B 專用 `ngrok.yml` 關閉 inspector／request inspection、remote management 及 update check；config、帳密、日誌及 runtime 證據均在 ignored 私有目錄，不能入 Git 或封裝。官方 ngrok 3.39.11 executable 沿用 A runtime 的已驗證檔案，但 agent/config/PID 分離；停止時不可依 executable 名稱殺掉所有 ngrok。

`stop-preview.ps1 -CheckOnly` 已實測通過 PID 建立時間、命令列含 B app-dir／config、父子關係及 8044 歸屬檢查，沒有實際停止。經授權需要停止本入口時，在 B 工作目錄執行 `powershell -NoProfile -File data/grid-public-runtime/stop-preview.ps1`；此腳本只停止本次 B 三個程序，保留 DB、凍結來源與成品，不碰 A／8042。程序身份不符會拒絕，不可硬改 PID 繞過。

`start-app.ps1` 僅保存本次已知 origin／agent 的受控啟動，不是通用重建器；它拒絕占用中的 8044，沒有開機自啟、排程或自動恢復。ngrok 重建可能換網址，屆時必須重新核對 origin、代理、runtime 身份及安全驗證，不能只重用舊命令。當前服務已跨多次工具 shell 及瀏覽器操作仍存活；不承諾電腦重啟後持續可用。

本庫只有 83 名合成會員、3 場、85 筆報名；授權 admin 以正常 CLI 建入新庫，未覆寫原管理員或歷史 actor。公開驗收只改 B 新庫的合成 02 當次級數／格位並新增完整保存版，會員長期級數與 hard snapshot 保持一致。A 帳密／session 及正式／真實資料不變。本次不包含 Git 提交／合併／推送、B image、正式資料 migration、Docker 演練或實機觸控；worktree 與兩個 B 預覽保留供人工驗收及後續修正。


### B 編輯／列印增量交付契約（尚未更新公開執行版本）

`data/grid-edit-delivery-identity.json`描述新allowlist source與`dist-grid-edit`。新`column_title`operation及optional column.title需要同批後端／前端載入；DB仍0008，不跑migration、不reseed、不替使用者大存。task4只修改B工作樹、使用8043/grid-edit-e2e.db合成測試；8042、8044/ngrok、runtime/source/static、公開DB/admin/session未由task4修改。

task5依既定授权序列核對source停寫／manifest、現況identity，受控停寫備份與短暫app換版，保留同eb24/ngrok、原DB與session、尚未大存差異。不能套用舊「只換static」程序，因舊backend不接受column_title且其GridLayout response會丟掉title。舊程式即使能開啟0008，也不能宣稱可無損顯示／處理新欄標題或合併直接編輯。回退不覆寫新產生的使用者資料；保留故障庫及新快照，先核對相容策略與授權，不默默還原舊DB。A/f9d0與8042不在換版範圍。工程與PDF合成證據不等同公開更新或人工接受。


### 待換版：B 刪軸／素食按鈕／歷史順序

本輪task4交付 `data/grid-axis-delivery-identity.json` 與獨立 `dist-grid-axis`，來源仍未提交snapshot。task5須先核對manifest、待task4停寫後凍結；此處尚未宣稱換版。现用公開grid-edit-20260921-110654、B listener32752／launcher36224、ngrok57728、eb24與原DB/admin/session保留；前文11:08／11:11來源UNKNOWN的後續安排不作回退或抹除。

新增delete_row/delete_column operation需同批載入前後端；DB schema仍0008，不migration/reseed、不替使用者大存、不改舊snapshot。沿既有維運契約停寫、備份、凍結source/static、受控更新B app，保留ngrok與登入。換版前唯讀解析既有workspace／保存版／operations；若驗證公開UI，避免實際刪除、插入、drag drop或文字提交污染使用者安排。

旧backend union不認識新刪軸operation/receipt，即使schema相同亦不可聲稱app-only無損回退。若新版已有寫入，先停寫、保留故障庫及所有後續資料，再依相容image/schema與授權恢復策略處理，不覆蓋回舊備份。合成測試只用8043/grid-axis-e2e.db；dist-grid、dist-grid-drag、dist-grid-edit及既有runtime releases均保留。


### interaction 版相容契約與工程交付範圍（已受控更新）

新來源／static以 `data/grid-interaction-delivery-identity.json` 核對，成品 `dist-grid-interaction`；原 `dist-grid`／`dist-grid-drag`／`dist-grid-edit`／`dist-grid-axis`及全部frozen releases不覆寫。DB仍0008無migration/reseed，新增swap/insert/move_empty/shade operation、row/column shade、admin歷次GET需要同批新前後端。舊move client仍保有原插入語義；舊JSON缺shade讀0且GET不改bytes，舊receipt仍可解析。新receipt/色階資料不能交舊backend無損處理，切回舊app可能拒新operation或遺漏色階，不因schema相同略過相容檢查。

task4只在原B工作樹實作與8043新合成DB驗證，沒有操作public資料／管理session／服務；task5 已於停寫交付後依既有備份／相容解析／短停 app 程序換版，實際現用 PID 見本頁目前 interaction 身份。未更換 ngrok、未碰 A／8042，未替主場有效 drop/delete/color/text/save。既有未大存差異及 UNKNOWN 後續操作原樣保留。新歷次查詢無 seed 要求，公開沒有符合紀錄就顯示空，不能為展示補造。

本次验证是Windows及Chromium PDF/觸控模擬；其他OS/實機/列印driver未驗。原生Windows preview/helper維持原用途，未為跨平台偏好重寫。文件中命令／artifact皆相對專案根目錄，task5依已指定工作樹解析，不複製虛擬環境到其他平台。


### 局部底色／復原版工程交付（待 task5 受控換版）

本輪獨立成品為 `frontend/dist-grid-undo`，合成測試為 8043／`data/grid-undo-e2e.db`。前輪 `frontend/dist-grid-cell-shade` 與所有既有成品、frozen releases 保留，不拿半成品換公開版。完成後以 `data/grid-undo-delivery-identity.json` 核對 source/static；交付以該 identity 的 source/static hash 與 freeze 狀態為準。

資料庫仍 0008，不 migration/reseed。新增 cell_shades、shade_cells、undo operation 與 receipt 私有前狀態，需要同批前後端；舊 backend 不認新 operation，也可能丟局部色。即使 schema 相同仍不可無損 app-only 回退。舊 receipt 不補 metadata、舊 snapshot 不改 bytes；換版保留 admin/session、全部安排與未大存差異。公開備份／短停／凍結／換版仍由 task5 依來源授權執行，task4 只做工作樹與隔離合成驗證，無公開操作或正式資料驗收。


### 表頭／待確認恢復版交付（待受控更新）

新成品 `frontend/dist-grid-header`，專用驗證 8043／`data/grid-header-e2e.db`；已發布 `frontend/dist-grid-undo` 及所有舊 static/runtime releases 不覆寫。identity 為 `data/grid-header-delivery-identity.json`，以 source/static hash 及 freeze 狀態核對。仍 0008 無 migration／reseed；新增 shade_header receipt 與 optional header_shade 需同批前後端，舊 backend 可能拒 operation／丟表頭色，不能視為 app-only 無損回退。

task4 不操作 public DB/session、既有 pending、現用 WMI app/ngrok；task5 維持原備份、相容核對、短停與 b021 更新流程。使用者原本未知 request 仍應由原瀏覽器安全確認，部署不能替代使用者修改或抹除未確認請求。公開只讀 smoke 不是有效上色／undo／save 的授權。


### 版本雙欄／選手單雙擊版交付（待受控更新）

新成品 frontend/dist-grid-panels，合成測試使用 8043／data/grid-panels-e2e.db，交付 identity 為 data/grid-panels-delivery-identity.json。這輪只有前端三檔來源及必要測試／文件，backend/API/schema/deps 與 grid-header identity 一致，無 migration／reseed。既有 grid-header、grid-undo 及全部舊 static 不覆寫。task4 凍結後由 task5 依 orchestrate 授權核對身份並受控更新；task4 不操作公開 app/DB/session/ngrok，也不代確認既有 unknown 操作。

## B Excel 匯出精修交付（2026-09-22，待受控發布）

本輪從 acacb876c90aad109af12edd831561fd9fa93914 的 `feat/arrangement-export-print` 產生未提交增量；沿用 B 工作目錄。新增正式前端相依 write-excel-file 4.1.1／fflate，依既有 npm ci 與 build 流程即可，不新增後端／migration／服務／建置外掛。

驗證隔離為 `frontend/dist-grid-export`、`data/grid-export-e2e.db`、8043；測試結束無 listener。此前所有 static、公開預覽 DB／admin／session／ngrok 與 A 服務不由 task4 操作。最終來源、lock、文件／測試及新 static 指紋位於 `data/grid-export-delivery-identity.json`。task5 依 orchestrate 授權核對並凍結來源及成品後才處理公開預覽更新；task4 未 stage／commit／merge／push／部署。

## D 恢復與版面精修（待受控更新）

本輪 source/static 使用 data/grid-recovery-delivery-identity.json 與 frontend/dist-grid-recovery；沿用B同分支與未提交前輪成果。產品只變更5個前端檔，無後端／migration／依賴變更。task4只操作合成grid-recovery-e2e.db／8043，不處理public原unknown。orchestrate核對新freeze後由task5依既有WMI／停寫備份／source與static manifest／原子index／readonly smoke與DB對比流程更新同b021，正常啟動不migration；舊release/static及public admin/session不清除。沒有新排程、Git交付或cleanup授權。


### 同色上色 no-op 修正交付（2026-09-22，尚未部署）

B 新成品 `frontend/dist-grid-shade`，合成驗證 `data/grid-shade-e2e.db`／8043；交付來源與資產指紋 `data/grid-shade-delivery-identity.json`。task4 完成後停止寫入，由 orchestrate 核對再交 task5 受控凍結與更新；沿用原授權的 URL／資料與帳密，不操作原使用者分頁。舊 D 與全部既有成品保留，沒有新增 migration／依賴。已確認本事件為明確未寫入的 no-op422；更新完成後使用者可重整此頁載入修正，其他結果未知請求仍遵守既有原樣核對契約。此段不改寫上方目前服務與發布紀錄。

### F 格位操作選單／表頭合併工程版（2026-09-23，待 task5 受控更新）

沿用 B `feat/arrangement-export-print`、HEAD `acacb876c90aad109af12edd831561fd9fa93914`。task4 成品只寫入 `frontend/dist-grid-menu`，合成 E2E 僅用 `data/grid-menu-e2e.db`／8043；source／static／舊成品核對記錄在 `data/grid-menu-delivery-identity.json`。identity 另列本次文件／測試 hash、十個既有 static 成品 hash 與驗證結果。測試後 8043 listener 為 0；前述 grid／export／print 成品都保留。

新增 `cell_shades` 明確白色與 optional `header_shade`／`header_merges` JSON，以及 `shade_cells`、`merge_header`、`unmerge_header`、`header_text` operations；資料表仍 schema 0008，無 migration／reseed 或新增依賴。舊 backend 不保證保存新增欄位，也不支援全部新 operation；公開更新需 task5 按既有 GO 同批處理前後端，不可只換 app 或假設同 schema 可無損回退。task4 沒有操作 public DB／session／app／ngrok／A／8042／8044，未 stage／commit／merge／push／部署。工程證據不等同正式部署或人工驗收。

人工本機檢視使用的隔離識別為 `data/grid-menu-e2e.db`／`frontend/dist-grid-menu`／`127.0.0.1:8043`；本輪只由 Playwright webServer 暫時啟動，結束自動停止，最後 listener count 為 0。若另需前景手動預覽，先確認 8043 無 listener，再由 repo root 設定以下環境並直接啟動（不經會刪除重建 E2E DB 的 `scripts/run_e2e_server.py`）：

```powershell
$env:FUCHENG_DATABASE_URL='sqlite:///data/grid-menu-e2e.db'
$env:FUCHENG_COOKIE_SECURE='false'
$env:FUCHENG_STATIC_DIR='frontend/dist-grid-menu'
uv run --locked uvicorn fucheng.app:app --host 127.0.0.1 --port 8043 --no-access-log
```

以前景視窗 Ctrl+C 停止，再確認 `Get-NetTCPConnection -LocalPort 8043 -State Listen` 無結果。本輪未留下可登入的人工預覽程序或密碼；E2E 管理密碼由測試程序隨機產生，未寫入 identity。重建 static 使用 `npm --prefix frontend run build -- --outDir ../frontend/dist-grid-menu`，不得改寫其他 `dist-*` 或既有 runtime。

### B Undo／Redo 與差異定位工程版（2026-09-23，尚未部署）

沿用 `feat/arrangement-export-print`、起始 HEAD `acacb876c90aad109af12edd831561fd9fa93914`；新交付身份為 `data/grid-redo-delivery-identity.json`，最終獨立前端成品 `frontend/dist-grid-redo-final`。合成驗證使用 `data/grid-redo-20260923-final-visual-e2e.db`／8043，完整 desktop／mobile spec 10 passed，CSS contrast 定向 spec 2 passed；目前無 8043 listener。Playwright 初始化的只是新 synthetic DB，僅套用既有 migrations 0001–0008；沒有新增 migration file、遷移既有／正式資料或改動服務。

Redo 新增操作與私有 receipt stack 需要相符的新後端和前端一起更新；舊 backend 不認 redo operation，也不保證保存 `_redo_stack`，即使 schema 仍為 0008 也不能 app-only 回退或宣稱無損。公開更新仍需 orchestrate 依既有授權與 GO 流程核對來源、成品、相容性與 freeze；本 task 沒有 stage／commit／merge／push／部署，也沒有更動 public DB／app／session／ngrok／A／8042／8044。此工程驗收不代表正式部署或人工接受；全部舊成品與 synthetic evidence 均保留。
