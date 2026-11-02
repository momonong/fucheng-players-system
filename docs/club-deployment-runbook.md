# 球館部署與維運指南

更新：2026-11-03。會員使用固定入口 **https://fucheng.momonong.workers.dev/**。
球館已完成部署，原管理員登入成功；目前不需要重新建立帳號、搬資料或重貼首次安裝碼。

## 現在的架構與版本

```text
會員瀏覽器 HTTPS → fucheng Worker → fucheng VPC Service
  → fucheng Tunnel → 球館 cloudflared → app → Linux named volume
                                           └ backup → 球館本機備份
```

球館不需要固定公網 IP、路由器開 port 或另購網域。固定網址屬於目前 Cloudflare 帳號的
Workers 子網域；只要保留同一帳號下的 Worker 名稱與子網域，球館網路 IP 改變不須換網址。
正式服務使用具名 Tunnel，不依賴每次重啟會變網址的 Quick Tunnel。

| 項目 | 本次成功部署 |
| --- | --- |
| app image | `momonong/fucheng-players-system:1.2.0`，實際按下列 digest 固定 |
| app digest | `sha256:0e5a297b0d16876fa56e1b9bed0470c3b8632d55ded6b23ffc5c18315f39e6e2` |
| cloudflared digest | `sha256:faa8e0a1475f137c910be6025f43c8e4092fdd35461b31e19fd1390657a1ff39`（2026.10.3） |
| 資料表版本 | `0015_deployment_diagnostics` |
| Compose project | `fucheng` |
| 正式容器 | `fucheng-app`、`fucheng-backup`、`fucheng-cloudflared` |
| 正式資料卷 | `fucheng_data`（Docker Desktop 的 Linux named volume） |
| 保留的舊試用卷 | `fucheng-check-v120_data`，不是正式站後續資料的同步副本 |
| 原管理員 | `momonong`／陳鎮濃，沿用本機私密設定的密碼 |

正式 app 不發布 Windows 主機 port；原 localhost:8052 試用站已停止。
`momonong.me` 的首頁、其他應用及原 Turnstile 設定均不隨本次部署更改。

## 已採用的部署流程

首次搬移工具為 [club-vpc-deploy.ps1](../deploy/docker/club-vpc-deploy.ps1)，故障後的
限定接續為 [club-vpc-reconnect.ps1](../deploy/docker/club-vpc-reconnect.ps1)。取用檔案時
固定本文件所在的同一 Git commit，不把歷史聊天中的壓縮片段或任意 main 版本當安裝碼。
工具自包含，球館不需要 clone 原始碼或安裝 Python／Node.js；使用原生 Windows PowerShell。

1. Windows BIOS 開啟 AMD SVM，進入 Windows 後確認 Docker Desktop 的 Linux engine 可用。
   WSL 是 Docker Desktop 的底層需求之一；Git Bash 不是替代虛擬化的工具。
2. 核對舊試用容器、固定 image、8052 loopback、原資料卷及無其他 writer；不符就停止。
3. Cloudflare 建立專用 Worker／Tunnel／VPC Service，名稱均為 `fucheng`。
   Service 使用 HTTP、Host **172.30.98.2**、port **8000**；Worker binding 名稱為 `fucheng`。
   [Worker 程式](../deploy/workers-vpc/worker.mjs)保留公開 Host、Origin、Cookie 及 CSRF。
4. 建立 lowercase `fucheng` Turnstile widget：hostname 為
   `fucheng.momonong.workers.dev`、Managed、無 pre-clearance。不要修改原本 momonong.me widget。
5. Tunnel token、此 widget 的 sitekey／secret 僅在球館終端隱藏輸入。Tunnel token 從該
   Tunnel 的 connector 安裝命令取得；Turnstile 兩種 key 從該 widget 的詳細頁取得。
   不貼聊天、不截取金鑰畫面、不把完整 Docker token 命令寫入 history／文件。
6. 停止舊 preview，透過同一 runtime 成組備份 DB＋媒體，匯入並還原至新的正式卷。
   保留原卷、備份及每個 operation 的容器／UUID；逐表比較業務、管理員、schema、媒體。
   新卷舊 session 失效，但帳號密碼不變。不是把 4090 的舊資料庫覆蓋到球館。
7. 確認 app／backup healthy，再啟動 connector，核對固定公開 `/api/health` 正確 JSON，
   journal 才標記 `COMPLETE`。本次接續沒有重新 init、migration、import 或 restore。
8. 在固定網址重新登入。本次使用者已確認成功；仍需另外驗收會員報名及冷開機。

VPC Host 不要填 `app`：app 與 connector 共用多張網路，名稱可能解析到出站網路，
導致來源不符合可信代理 `.3` 而被拒絕。固定私有 `.2` 保留單一可信代理，不放寬驗證。
完整資源 ID、網路與故障證據見 [Workers VPC 接入](club-workers-vpc.md)。

## 資料、備份與秘密放在哪裡

在球館按 Win＋R，輸入 `%LOCALAPPDATA%\Fucheng` 即可開啟工具目錄。
AppData 是 Windows 隱藏目錄，不必手動從 C 槽逐層找。

| 位置 | 用途與注意事項 |
| --- | --- |
| `compose.yml`、`owner.txt`、`setup.lock` | 已核對的部署 recipe、身份及排他鎖；不要手改或刪除繞過 guard |
| `deploy-journal.json` | 原部署階段、operation 及資料核對結果；失敗／未知時先留存核對 |
| `protected.env`、`turnstile.secret`、`tunnel.token` | 私有配置；不得上傳 Git、聊天或當一般附件分享 |
| `backup\checkpoint-<部署ID>` | 停寫搬移前的 DB＋JSON metadata＋媒體成組備份 |
| `backup\live` | 正式站持續備份；每週排程保留 8 組已驗證週備份 |
| Docker named volume `fucheng_data` | 正式 SQLite、媒體及網站內建檢查報告；不是 Windows 目錄中的單一 JSON |

備份仍只在球館這台電腦，不能抵禦整顆硬碟損壞。雲端／異機備份尚未配置。
手動保存備份時複製完整同組 DB、JSON、media.tar，不只拿資料庫或 metadata。
需要手動建立一組時，可在確認 `fucheng-backup` 正常運行後執行：

```powershell
docker exec fucheng-backup python /app/runtime.py backup
```

不要直接複製運行中的 SQLite／WAL 作為完整備份。還原須先停寫、保留故障卷、選匹配
image/schema，再經 runtime 還原至新卷並核對；不要直接覆蓋正式卷或刪除 preview marker。

## 平常怎麼看狀態

球館電腦要保持開機、連網，Docker Desktop engine 要運行；可關螢幕，不要關主機或 Docker。
不要移除 volume、使用 Docker prune 或 `down -v`。Windows 無登入密碼不代表網站帳密不存在。

以下只讀目前狀態，不重開機、不改服務、不讀金鑰：

```powershell
docker ps -a --filter label=com.docker.compose.project=fucheng --format 'table {{.Names}}\t{{.Status}}'
Invoke-RestMethod 'https://fucheng.momonong.workers.dev/api/health'
```

預期 app／backup 是 healthy、cloudflared 是 running，health 為 `status: ok`。
登入仍需球館原帳密；與已停用 4090 接收站的 `home-admin` 是兩份獨立資料，不互換。

日後若正常關閉過容器，只能在確認原 journal 為 COMPLETE、保留原 recipe／秘密且
沒有另一個 writer 後啟動原 stack；不重貼首次搬移碼，也不建立第二套空資料庫。
Docker Desktop／Windows 開機啟動、登入及 `unless-stopped` 是不同層次：本次未調整
Windows 服務、電源、登入或防火牆，冷開機恢復尚未驗收，不能只靠 restart policy 推定。

## 失敗時先做什麼

| 現象 | 處理 |
| --- | --- |
| 公開 503／health 失敗 | 核對 app／backup、Tunnel connector，再核對固定 Service IP；回退後的 503 不能反推原失敗狀態 |
| `PRIVATE_ACL_UNCONFIRMED` | 保留現場；工具只接受本人／SYSTEM／Administrators 的私有 ACL，不用 takeown 或寬鬆授權跳過 |
| import／restore timeout 或 UNKNOWN | 保留原 journal、operation ID／receipt 及兩份卷；先查原操作，不能重發或換 UUID |
| 新 stack 停止未確認 | 不啟動舊 preview，避免兩個可寫站點分別寫入；不可直接重跑還原 |
| 資料核對不一致 | 兩份資料保留，停止搬移；以差異及匹配備份處理，不讓舊 preview 覆蓋正式新資料 |
| 複製貼不上 Git Bash | 改用原生 PowerShell；AnyDesk 剪貼簿同步與 Git Bash 貼上是不同設定 |

只回報階段、代碼、容器狀態等非秘密內容，不提供完整 inspect/env、原始認證錯誤或 token。

## 已驗證與待驗收

- **已確認**：球館原生 Windows ACL、資料／帳號／媒體保全核對、app／backup healthy、
  具名 Tunnel 接通、固定網址 health、使用者原帳號登入。停 4090 後瀏覽器再次讀到 `{"status":"ok"}`。
- **待驗收**：另一支手機以行動網路開啟、真實 Turnstile／報名→管理端名單連動、Windows
  冷開機及斷網恢復、完整災難還原。不要為驗收自行重開球館電腦或新增真實測試報名。
- **停止的相依**：4090 `momonong.me/fucheng` 報告接收端與工具下載隨舊站停止；歷史
  固定 SHA bootstrap／ZIP 不再作為新安裝入口。球館正式服務沒有啟用 report send／upload，
  內建檢查仍可保存／下載，本機舊 JSON、UUID 及收據也保留。

升級需另選新版本、驗證與授權，不把 `latest` 當自動升級策略，不覆寫既有 1.2.0 image。
本次 Git 交付包含維運工具／接收端來源與文件；不代表這些新來源已取代球館固定映像。

## 本次工程驗證

2026-11-03，Python／PowerShell 合成回歸完整 **585 passed**，包含部署／接續／ACL 的
59 項案例。修正前新增的兩項 stop timeout／停止後仍 running 案例均重現舊 preview 被
啟動；修正後兩項及其餘案例通過。獨立唯讀審查確認無剩餘合併阻擋。

前端 typecheck、隔離成品 build、6 項 Worker Node 測試、`uv lock --check --offline`、
`npm audit --audit-level=high`（0 vulnerabilities）、來源 allowlist／hash／秘密路徑檢查
及文件連結檢查通過。沒有新依賴、migration 或正式站測試資料。

使用既有 Chrome 取得受影響 UI 的桌面 9 項、手機 9 項通過證據。最初 Playwright
預設的瀏覽器 revision 未安裝，未因此安裝新軟體；改用現有 Chrome。桌面與手機同批
共用合成 DB 時為 16 passed／2 個手機案例觸發登入頻率限制，手機獨立新建合成 DB
重驗 9/9 通過，產品的頻率限制沒有放寬。這些 E2E 不等於球館真實報名／冷開機驗收。

工程收據與隔離成品在 ignored `data/club-cutover-20261103/`；不將 DB、備份、token、
金鑰、密碼或認證 hash 加入 Git。本次不新增版本 tag／GitHub Release／registry image。
