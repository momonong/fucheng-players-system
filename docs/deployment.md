# Windows Docker 部署、搬移與維運

本階段交付是**本機已驗證、可搬至球館的部署套件**。正式架構是一個 app image，內含 React 靜態成品及 FastAPI，SQLite 存獨立 named volume；備份與維護復用 app image。Cloudflare named tunnel 直接連 app；nginx 僅供本機 HTTPS 測試，不是正式必要層。不增加 PostgreSQL、Redis 或常駐 Node，不更換 Windows。

本機合成驗證不等於球館實機、正式資料或人類驗收已完成。原r7～r9交付未啟公開Tunnel；2026-09-20另獲使用者授權的ngrok公開合成預覽見下節。未搬移正式資料、commit／merge／push或發布registry。

## 已授權的 ngrok 公開合成預覽（2026-09-20）

遠端筆電的localhost不是服務主機，因此另建立 **https://30a1-140-116-158-107.ngrok-free.app/**。這是公開合成驗收環境，沒有真實會員資料；不是將8450 local-http模式接上Tunnel。復用r9正式ngrok Compose與image，全新project `fucheng-ngrok-preview-20260920`、volumes `_data`／`_backups`，獨立origin `172.30.106.0/24`與egress網路。app不發布host port、Secure cookie與精確Host/Origin/CSRF/session維持，trusted ngrok peer為`172.30.106.3`。

原本機ngrok配置含可用authtoken，只讀取並複製到ignored的本次secret檔，沒有修改原設定。沒有發現本機既有ngrok process/container；帳號其他主機session未枚舉，沒有停止其他session。設定關閉agent web UI、request inspection、remote management與update check。未購買方案、保留付費網域或修改帳號付費設定。

私有運行設定：`data/deployment-ngrok-evidence-20260920/release.env`、`ngrok-secret.yml`；合成帳密：同目錄`synthetic-admin.json`。以上不加入Git/image/離線包，勿將token或密碼貼到聊天。只初始化3位合成會員與1個2099年合成場次，未從其他資料庫複製。

CUA IAB已實測首頁、管理登入、儲存合成會員及登出；main與orchestrate亦核對首頁可見合成比賽。首次可能有ngrok自己的Visit Site提示（orchestrate實見ERR_NGROK_6024），這不是瀏覽器TLS警告；本task沒有使用skip header或略過TLS驗證。公開API使用正常TLS驗證，HTTP入口307導向同域HTTPS。

服務主機、Docker daemon、app與ngrok容器必須持續運作且可連網；關機、休眠、斷網、帳號限制或停止容器都會令網址不可用。網址已寫入本次ngrok配置與精確public origin，但不保證永久保留或未登入冷開機自動恢復。若ngrok拒絕重啟或改配網址，先停止該preview並重新核對origin，不放寬Host。

立即关闭公網（保留app與資料）：

```powershell
docker stop fucheng-ngrok-preview-20260920-ngrok-1
```

停止整組本次環境，保留volumes，不影響8032～8035、8448、8450：

```powershell
powershell.exe -NoProfile -File D:\projects\fucheng-players-system\data\deployment-release-20260920-r9\operate.ps1 Stop -EnvFile D:\projects\fucheng-players-system\data\deployment-ngrok-evidence-20260920\release.env
```

來源契約：[ngrok v3設定](https://ngrok.com/docs/gateway/agent/config/v3)、[upstream headers](https://ngrok.com/docs/gateway/endpoints/http#upstream-headers)。實際帳號連線結果與瀏覽器證據以`data/deployment-ngrok-evidence-20260920/ngrok-final.json`為準。

## 套件與現場最短步驟

本輪套件位於 `data/deployment-release-20260920-r9/`：`fucheng-images.tar`、`release.json`、`SHA256SUMS.txt`、逐檔 source manifest／snapshot ZIP、Compose、PowerShell helpers及本手冊。它包含既有未提交的級數功能，是 **working-tree snapshot**；HEAD 並不代表全部來源，應以 image ID 和 manifest SHA256 識別。套件不含會員資料、帳密、Tunnel token、TLS私鑰或備份。

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
