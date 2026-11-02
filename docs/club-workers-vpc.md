# 府城 Workers VPC 接入

這份文件記錄球館 Windows Docker 接入 Cloudflare 的設定。2026-11-03 球館已回報
`COMPLETE`、app／backup healthy、公開健康通過，使用者確認原帳號登入成功。
4090 舊試用站已停寫保留資料；球館成為實際使用入口。日常操作與備份位置見
[球館部署與維運指南](club-deployment-runbook.md)。真人驗證報名、獨立手機網路及
Windows 冷開機尚未完成驗收，不以健康檢查代替。

## 已確認資源

| 資源 | 值 |
| --- | --- |
| 固定入口 | `https://fucheng.momonong.workers.dev` |
| Worker / Tunnel / VPC Service 名稱 | `fucheng` |
| Tunnel ID | `fa458cdb-0bf4-43a2-89ef-e9d15b348d14` |
| VPC Service ID | `01a192c8-1155-7dc2-9c51-acec10809396` |
| Service 私有目的地 | HTTP `172.30.98.2:8000`（2026-11-03 已修正） |
| Service DNS | 使用固定私有 IP，無須解析 `app` |
| Worker binding name | `fucheng`，程式透過 `env.fucheng` 存取 |

## Cloudflare 設定

在 Worker `fucheng` 的 Bindings 選 Add binding → VPC Service，variable name 填
`fucheng`，選取上列 Service ID 對應的 `fucheng` Service，儲存並完成介面要求的部署。
使用者已在 2026-11-01 確認其介面有 VPC Service 選項。

將 `deploy/workers-vpc/worker.mjs` 完整貼到 Worker 編輯器再部署。
`deploy/workers-vpc/wrangler.jsonc` 提供同一設定的 CLI 版本，網頁操作不需要再部署
另一個 Worker，也不需要在球館安裝 Node.js。

Worker 透過 VPC Service binding 決定目的地，fetch URL 的 authority 保留公開 Host。
Service 必須指定固定 origin IP `172.30.98.2`，不能使用裸名稱 `app`：目前 app 與
connector 同時共用 origin 與出站網路，Docker DNS 實測可能只回出站網路的 app IP；
該路徑上的代理來源不是明確信任的 `172.30.98.3`，後端會拒絕轉送標頭。指定 origin
IP 會保留嚴格的單一可信代理設定，不擴大信任範圍。
到私有服務的 scheme 為 HTTP，Cloudflare 到 connector 的流量由 QUIC Tunnel 保護。
僅相信 Cloudflare edge 提供的 CF-Connecting-IP，移除其他 forwarding authority，設定
X-Forwarded-Proto=https。Origin、Cookie、CSRF 保持原值，由既有後端權限邊界驗證。
沒有 binding 或服務連不上時只回不快取的 503，不回傳原始例外。

## 球館完整部署

在球館的一般 Windows PowerShell 完整貼上 `deploy/docker/club-vpc-deploy.ps1`。
這是一段自包含工具，不需要 Git clone、傳送資料夾或在球館安裝 Python／Node.js。
它只操作本機 Docker Desktop 與 `%LOCALAPPDATA%\Fucheng`；不操作 `momonong.me`
的部署、帳號、網域、Turnstile 或報告接收服務。

工具先核對現有 `fucheng-check-v120`、固定 1.2.0 映像、preview 設定、loopback 8052
與 `fucheng-check-v120_data`。找不到或不一致即停止，不建立空資料庫代替原有資料。
輸入均在本機隱藏提示中完成：專用 Tunnel token、lowercase `fucheng` Turnstile 的
sitekey 與 secret。金鑰保存於目前 Windows 使用者、SYSTEM 與 Administrators 可存取
的私有目錄；secret 以檔案掛載，不放命令列或容器環境變數。

流程會停止已核對的試用容器，將 DB＋媒體成組備份到私有目錄，再以同一固定映像
匯入並還原到新的 Linux named volume `fucheng_data`。原 `fucheng-check-v120_data`
保留。唯讀比較所有非 session 資料表、管理員完整資料、schema／integrity／foreign
keys 與媒體後，才啟動正式 app、backup 及 cloudflared。還原會清除新卷的舊登入
session，原帳號密碼與其他資料保留，需在新網址重新登入。

正式 app 不發布主機 port。專用內部網段為 `172.30.98.0/24`，app `.2`，可信代理 `.3`；
部署前核對 Docker 網段與 Windows IPv4 routes，有衝突即停止，不改路由或防火牆。
app 與 cloudflared 另有出站網路，供 Turnstile siteverify／Tunnel 使用；backup 無網路。
本機備份位於 `%LOCALAPPDATA%\Fucheng\backup`，每週排程保留 8 組已驗證備份。

只有 app 與 backup healthy，且固定公開入口 `/api/health` 通過正常 TLS、無轉址及
正確 JSON 檢查才印出完成。失敗會嘗試停止這次的新 stack，並在確認原容器身份後
恢復原先運行的 preview，保留新卷、備份與 journal。未知／部分操作不會自動重送
import 或 restore；已 COMPLETE 的重跑僅核對健康，不從舊 preview 覆蓋新資料。

這次不重開機、不修改 Windows 服務或電源設定。`unless-stopped` 只保證 Docker
engine 啟動後的容器恢復策略，不代表 Docker Desktop、Windows 登入或冷開機驗收完成。

## 公開連線失敗後接續（2026-11-03）

球館曾完成 BACKUP／IMPORT／RESTORE／DATA_VERIFIED 與 APP_BACKUP_HEALTHY，
但在公開健康檢查失敗後回退。已核對 Tunnel 歷史有 4 條 QUIC registered，球館 curl
與 .NET 都能收到 Worker 的維護 503；該 503 是回退後的觀察，不等於原失敗 HTTP 狀態。

隔離合成重現使用固定 1.2.0 image 的實際 `DeploymentBoundary`：兩張共用網路下，
`app` 解析到出站 IP，8/8 回 `400 Untrusted forwarding headers`；直接指定 origin IP
則回 200；移除共用出站路徑後，名稱解析與 8/8 HTTP 也回 200。這證明原部署存在路徑
歧義，不代表球館現場沒有其他問題。實測未掛資料卷、未開主機 port，測試資源已清理。

使用者於本對話當次明確授權後，只將專用 VPC Service 的 Host 改為 `172.30.98.2`，
HTTP 8000、Service ID、Tunnel、Worker、TLS 驗證與所有金鑰保留。控制台已確認儲存；
其後球館執行 `deploy/docker/club-vpc-reconnect.ps1` v2 完成公開驗證，使用者確認登入。

該接續工具為獨立自包含 PowerShell，保留當次原部署 recipe／ownership／journal
驗證：只接受 COMPLETE 或已確認資料保留後的 PUBLIC_HEALTH_UNCONFIRMED 回退。
停止已核對的舊 preview 後，重跑原本的唯讀 verifier 容器，比較目前來源與新卷。
只讀掛載、固定 image／entrypoint／Python 程式與完整資料一致均確認後，才依序 start
既有 app、backup、cloudflared。沒有 init、migration、import 或 restore 寫入。
資料不同就停止，不覆蓋任一份；公開健康通過才將原 journal 更新為 COMPLETE。

失敗會停止本次既有新 stack，確認停止後才嘗試恢復原先運行的 preview；若停止結果
未知，保留現場並避免啟動另一個可寫站點。原先已停止的 preview 不會被擅自啟動。
COMPLETE 重跑僅健康核對。球館 Windows 接續及登入已確認；真人驗證、報名與冷開機
仍需現場驗收。完整部署腳本也採相同保護：新 stack 停止逾時或回讀仍運行時，不啟動
原 preview，保留原 operation／兩份資料，不自動重做還原。

### 接續工具 v2 的 Windows ACL 修正

現場回報 `preflight / UNKNOWN_OWNER`；該錯誤發生在任何容器操作之前，只證明舊的
「owner 必須等於目前使用者」比較未通過，尚未取得現場實際 owner 類別。舊測試曾
直接略過這個 guard，不能充作 Windows 權限驗收。

v2 不修改 ACL 或取得擁有權。它以原生 Windows API 讀取 SID／DACL，只接受目前
使用者、SYSTEM、BUILTIN Administrators 為擁有者與允許存取的對象；根目錄必須
阻斷上層權限繼承，檔案可繼承已核對的私有根目錄權限，且必須有目前使用者的明確
Allow 規則。其他擁有者、Everyone／Authenticated Users 等外部 Allow 規則、未受保護
根目錄或無法確認的權限均停止。輸出僅含檔名、owner 類別與 private_acl 布林。

已補上兩份腳本的權限政策與接續行為案例，共 57 項 focused 測試通過，包括
Administrators／SYSTEM owner 的合法私有權限，以及過寬權限在容器操作前必須拒絕。
測試以 portable PowerShell 執行。其後球館原生 Windows 輸出確認：根目錄 owner 為
目前使用者，compose／journal／owner marker／lock 為 Administrators，全部 private_acl
為 True；接續啟動、公開 health 與原帳號登入均已取得現場確認。
當前交付為可讀的 `fucheng-reconnect-v2-20261103.ps1`；先前不完整聊天壓縮片段作廢，
不得執行。v2 沿用既有資料、容器及全部資料比對，不重做 import／restore。

## 舊 connector-only 工具

在一般 Windows PowerShell 完整貼上 `deploy/docker/club-vpc-tunnel-setup.ps1`。
腳本只在當前使用者的 LocalApplicationData/Fucheng 建立私有工具目錄、token 檔與
單一 cloudflared 的 Compose project `fucheng`。它不部署 app，不碰
`fucheng-check-v120_data`，不遷移 DB、不改帳號、不重開機。

token 只在安全輸入提示中私下輸入，保存於受 Windows ACL 保護的 token 檔，
以 Compose secret 掛載，不放命令列或環境變數。不要將 token、含 token 的安裝指令、
token 檔或整個私有工具目錄送到聊天、Git 或公開下載服務。

connector 使用固定 cloudflared digest 並明確要求 QUIC。QUIC 註冊觀察與 container
running 不等於會員系統已公開可用；Cloudflare 控制台的即時狀態仍須現場確認。
固定 Worker 此時可能回 503，因為 app 尚未接入 `172.30.98.2:8000`。

## Turnstile 與網站接入相依

目前映像的正式 `cloudflare` 模式要求 Turnstile enabled。
已建立專用 widget：name=`fucheng`、hostname=`fucheng.momonong.workers.dev`、
mode=Managed、pre-clearance=No。原有 capital `Fucheng`／`momonong.me` widget
及金鑰未修改。Site key 與 Secret key 由部署者私下保管，在球館終端輸入，不傳到聊天。

既有 localhost 試用 volume 有 local-http-synthetic marker，runtime 明確拒絕直接
轉為 HTTPS。後續正式部署要先核對目前容器/image/volume，再依成組備份、匹配版本
還原到新 Linux named volume 的流程接入；保留原 volume，不能刪 marker 繞過守門。
正式 app、backup、cloudflared 必須使用一致的 origin/base path、可信代理與私有網路。
腳本完成後仍須現場驗證管理員登入、Turnstile 互動、公開會員報名及重連後固定 URL；
健康檢查不等於這些使用者流程已驗收。Windows 冷開機驗收另行安排。

## 本機驗證

Worker 候選的 focused 測試：

```sh
node tests/test_worker_vpc_gateway.mjs
```

PowerShell 候選使用已有的 portable pwsh 做 synthetic subprocess 測試；沒有拿球館
正式 token 開 Tunnel，也沒有把本機模擬結果寫成 Windows 5.1 實機成功。

固定 1.2.0 映像的實際合成備份、還原、管理員與資料比對、備份排程及容器重啟證據見
[搬移相容性驗證](club-vpc-pinned-image-verification-20261101.md)。

參考：
- https://developers.cloudflare.com/workers-vpc/get-started/
- https://developers.cloudflare.com/workers-vpc/api/
- https://developers.cloudflare.com/turnstile/get-started/widget-management/dashboard/
