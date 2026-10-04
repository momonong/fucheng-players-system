# 家中 4090 試用部署

2026-10-04 狀態：4090 已更新至 0.3.5，GitHub／Docker Hub 已發布，帳號與既有資料保留。公開管理頁已核對小圓形素食名單入口，以及靠右的備份／管理員名稱。真機操作手感、真實 Turnstile 報名與斷電恢復仍待驗收；歷史紀錄保留於下方。

## 主機與入口

使用 4090 的原生 Linux Docker Engine（context `default`）。單一 app image 包含前端與 FastAPI，不使用 GPU。入口沿用 selfhost-servers 的 Cloudflare Tunnel → HP Caddy，透過加密 SSH reverse forward 到本機 loopback；不另建 Tunnel、不占用首頁或 OrderFlow 路由。Caddy 候選與現用狀態由 selfhost-servers 的 `docs/fucheng-ingress-preparation.md` 管理。

`compose.home.yaml` 疊加在 `compose.yaml` 上：

- app 僅發布 `127.0.0.1:8064`，HP forward 僅監聽 `127.0.0.1:18084`。
- app 與備份各使用本 project 的 Linux named volume；不掛 Windows 路徑，也不共用其他 app 資料。
- app 僅信任指定 Docker bridge gateway。網路允許 Turnstile Siteverify 所需 outbound HTTPS。
- 不啟用 base Compose 的 cloudflared、ngrok 或 https-test profiles。
- 固定 image digest，`pull_policy: never`：先明確 pull 並核對 image，再操作。

## 設定與操作

從專案根目錄執行。先將 `deploy/docker/home.env.example` 複製至 Git 忽略且受限的 `data/home-deployment/home.env`，依現場確認網段／port。Turnstile sitekey 使用真正的 momonong.me widget，secret 放受限本機檔案，只提供路徑；secret 必須能由容器 UID 10001 讀取。不要把 secret 值放入命令、Git 或聊天。

```bash
dc=(docker --context default compose --env-file data/home-deployment/home.env
    -f deploy/docker/compose.yaml -f deploy/docker/compose.home.yaml)
```

真實資料只能以核定來源的成組備份 `ops import-backup` → `ops restore` 還原至全新 project/volume；不要執行 `init` 產生空資料取代既有來源。schema 必須匹配 image。舊式原生 SQLite 先保留原檔，在獨立、無 writer 的副本顯式 migration、逐欄核對既有資料，再製作符合 runtime 契約的成組備份。容器 volume 中所有寫入仍經 runtime 鎖，不直接掛載 SQL 修改。

```bash
# 只在資料／秘密／管理員帳號與還原前提完成後啟動：
"${dc[@]}" up -d --wait --wait-timeout 90 app backup
"${dc[@]}" run --rm ops inspect
"${dc[@]}" run --rm ops backup
```

`fucheng-hp-tunnel@.service` 是 systemd 範本，以實際本機使用者執行，例如 `fucheng-hp-tunnel@ubuntu.service`。它使用該帳號家目錄的 `~/.ssh/fucheng-hp-tunnel` 專用金鑰，明確停用 SSH agent，避免重開機後依賴桌面解鎖。私鑰只留 4090，權限 0600；HP 僅加入公開金鑰並保留原有 authorized_keys。對應授權使用 `command="/bin/false",restrict,port-forwarding,permitlisten="127.0.0.1:18084",permitopen="127.0.0.1:1"`：只允許指定 remote listener，不允許 shell、PTY 或 agent forwarding；local forward 僅限不可用的 loopback port 1。安裝前核對 `hp-server` alias 與 known_hosts，並驗證在沒有 agent 時正確 forward 可用、其他 listener 與 shell 被拒絕。金鑰若遺失須重新配對，不回退到一般管理金鑰。

需使用者終端的 sudo 認證才能安裝／enable，不能把測試 SSH 當正式服務。先驗 app，再驗持續 forward，最後依基礎設施契約備份、validate、reload Caddy。

## 本輪證據與剩餘條件

- 0.3.2 image ID `585befc2f28a075467ce15ce32ab5d41f20134b34523cb6ae759e93da097ffe5`，digest 固定於 env 範例。
- 隔離 project `fucheng-home-ingress-check-20261003`、8065、10.203.33.0/24、合成空資料：app/backup healthy；子路徑 health/HTML 200、匿名管理 401、根路徑 API 404、錯誤 Host／缺少轉送識別 400。測試金鑰是無效占位值，僅供 loopback 配置驗證，未呼叫 Siteverify、不代表 Turnstile 通過。
- SSH systemd 範本通過 `systemd-analyze verify`；HP 實際 Caddy 版本 validate 候選通過。臨時 HP loopback 18086 → SSH → 4090 8065 → Docker health 通過，測試 forward 與 app/backup 已停止、合成 volumes 保留。此為切換前驗證；後續正式安裝與公開切換見下節。
- 使用者已接受收到的舊資料快照作為試用基準，不要求補取 Windows WAL。原始檔另行保留；獨立副本 0005 → 0010 升級後，14 張原表的所有既有欄位逐列一致，integrity ok、FK error 0。未補造安排歷史，切換前尚未公開副本；後續以使用者接受的快照還原正式 volume。
- 正式 project `fucheng-home` 已經 runtime import/restore 還原指定副本。依使用者選擇，先在獨立副本建立及驗證新管理員，再停用舊管理員登入，保留其 actor 與業務資料；runtime 還原使舊 sessions 失效。本機新管理員登入／登出、Secure/HttpOnly 與 /fucheng/ Cookie、342 位會員及公開欄位界線通過。
- 有效設定檔已放入私密目錄；Siteverify 對無效測試 token 回 invalid-input-response，未回 secret-key 錯誤。這僅核對連通與基本設定，真正的瀏覽器挑戰尚未驗收。
- app/backup healthy；成組 export 與 archive/member hashes 通過，另以新 project `fucheng-home-restore-check-20261003` 驗 import/restore/inspect。第一次匯入因唯讀來源目錄欠缺容器 UID 穿越權限而停止，未建立產物；修正私密父目錄下的匯出子目錄權限後重新驗證。原始來源與全部資料卷保留。
- 專用 SSH key 無 agent 的正向轉送通過，shell 與其他 remote listener 被拒絕；金鑰不進 repo。使用者其後已互動 sudo 安裝持續 SSH／套用 Caddy，公開驗證見下節；登入後人工操作、真實報名、媒體及重啟恢復與異地備份仍待驗收或安排。受限證據在 ignored `data/`，不提交 DB 或認證內容。

備份 volume 與 app 同機，不能算異地備份。更新前手動備份與成組 export；回退在新 volume 還原匹配 image/schema，保留故障資料。不得 prune 或 down -v。

## 日後搬到球館

球館 Windows Docker Desktop／WSL2 仍可使用同一 Linux/amd64 release image、runtime 及成組備份。改採該場域的入口配置，不沿用 HP SSH overlay；根路徑時 `FUCHENG_BASE_PATH` 留空，`FUCHENG_PUBLIC_ORIGIN` 改為當地 HTTPS origin，前綴不寫入會員資料。不因改前綴重建 image。實機登入、資料還原、照片、斷電／重啟及 Windows 登入後 Docker 恢復仍需驗收。

## 公開切換驗證（2026-10-03）

使用者在終端完成兩台主機的互動 sudo。獨立核對 4090 的 `fucheng-hp-tunnel@ubuntu.service` active/enabled、NRestarts=0；app/backup healthy，app 僅發布 127.0.0.1:8064。HP forward 僅 127.0.0.1:18084；Caddy、cloudflared、既有 OrderFlow forward 皆 active。現用 Caddy SHA-256 為 `0e9b6473c465309ea5fad4dde547b9f286d3a363acd69142a3bd3157505da209`，與已審查候選一致；root-only 舊設定備份在 HP `/var/backups/fucheng-ingress/cutover-IQhjPaJx`。

公開瀏覽器可完整載入首頁公告、342 位會員的分級頁、比賽頁與管理員登入表單；共用根首頁及 OrderFlow 登入頁正常。舊場次已截止，公開報名頁正確顯示沒有開放場次；未為驗證向真實試用資料新增合成比賽或報名。

Python urllib 的外部探測被 Cloudflare 拒絕（403 / 1010）；瀏覽器正常進站。IAB 直接導覽 API 路徑另被 client 阻擋，因此未把它記成公開 API 成功，也未調整 Cloudflare 或繞過保護。先前透過可信本機入口的管理員登入／讀取／登出已通過；本輪公開瀏覽器登入後流程、真正的 Turnstile 挑戰及成功報名尚待使用者驗收。沒有斷電／重開機或另一條行動網路的驗證。

現用 image 保持 0.3.2 與原 digest；本輪僅同步部署設定及證據，未重建 image。帳密、來源資料、備份和完整受限紀錄保存在 ignored `data/home-deployment/`，不進版本庫。


## 0.3.3 手機管理升級（2026-10-04）

先完成 [PR #5](https://github.com/momonong/fucheng-players-system/pull/5) 合併與 [v0.3.3 Release](https://github.com/momonong/fucheng-players-system/releases/tag/v0.3.3)，再發布並核對 Docker Hub `0.3.3`／`latest`，最後更新既有 `fucheng-home` project。合併／tag 提交 `29db9c9e0f68fd4d807aa774bae1a753dae64239`；建置來源 `44d2386938658259824132ab2533dcea516c4da8`，兩者 Git tree 相同。

- 映像 digest：`sha256:001cae3e708512c95308cc672e26b1c0aa6d94172eff428eded1aa10883905da`。
- Image ID：`sha256:ad8461b6fa5330c01b6ad3d1c3d55709b9e20f3b75f146a7a5db4ae5bceb0432`。
- Source manifest：`ed50f853f7076b6bbdb454f0d205df91349d746f80afc00840322737780de935`，74 個 allowlist 檔案；乾淨已提交來源，無資料、秘密、備份或既有 dist。
- 後端 211 passed（2 warnings）、typecheck／build、npm audit 0 vulnerabilities；前端分批 56 項證據見 [手機流程](mobile-workflows.md)。新映像用獨立 root／prefix 合成 project 驗 health、登入登出、Cookie Path、未登入拒絕及完整性；JS/CSS 與前述 E2E 成品逐位元相同。
- 正常停止 app／backup，以 0.3.2 runtime 取得成組 backup／export，核對 archive 及所有成員 hash。停寫 checkpoint 為 `manual-export-20261003T181323809254Z-480d0e26.db`；私密匯出與原設定保留在 `data/release-0.3.3/`，原 volume 及 0.3.2 映像保留。
- app／backup 同批換成新 digest；ops 使用同一設定。沿用 `fucheng-home_data` 與 `fucheng-home_home_backups`，不做 migration／reseed。schema `0010_deployment_report`、integrity ok、FK error 0。16 張業務表逐表內容 fingerprint 不變：342 會員、2 場次、81 報名、2 安排保存版、2 公告。
- app／backup healthy，備份健康正常。可信 loopback／HP Caddy 路徑的 health、HTML、資產、管理員登入／讀取／登出、Secure/HttpOnly 前綴 cookie、匿名 401、錯誤 Host 400、裸 API 404 通過。沒有新增、刪除或修改真實業務紀錄。
- 公開瀏覽器載入新版 `index-Bt0za5_-.js`／`index-DfqKPVwR.css`，首頁公告、342 位會員及管理員登入表單正常；共用首頁及 OrderFlow 保留。未更改 Caddy／Tunnel／SSH／DNS，HP Caddy SHA 與 10-03 相同。

部署帳密沿用，無須重建管理員。這是程式更新與讀取驗證；公開登入後的手機操作手感、軟鍵盤、真正 Turnstile 報名及現場 Windows／斷電恢復仍待驗收。本次隔離合成 app 已停止，測試 volumes 與完整證據保留；未 prune 或刪除資料卷。同機備份不是異地備份。


## 0.3.4 手機表格修正部署（2026-10-04）

使用者明確授權先合併推送版本與映像，再部署試用。[PR #7](https://github.com/momonong/fucheng-players-system/pull/7) 合併後發布 [v0.3.4](https://github.com/momonong/fucheng-players-system/releases/tag/v0.3.4)，Docker Hub `0.3.4`／`latest` 遠端 digest 相同並拉回核對，才更新既有 4090 project。

- 合併／tag／映像來源：`d01a643ff669fcf0d89c273362ad78fb1613d861`。
- Digest：`sha256:6c3d1ad4b83ba4747e47d36ff994e309ce8c0a1a789e6dd0667d91848b15feb9`；Image ID：`sha256:1fc32dab958d6372f1acb314f7630fc24e8fe50e13570963e989382ce2cf846e`。
- Source manifest：`6ae1c78dc24c619514009fc9d8cf7afbc8cd0baedea0af4ed55a05df5e6bfe9e`，74 個 allowlist 檔案，乾淨已提交來源；context audit 通過，未包含 data／秘密／備份／舊 dist。
- 根路徑與 `/fucheng/` 新映像合成 project 分別驗 health、登入／登出、Cookie Path、匿名管理拒絕、prefix 下裸 API 404 與完整性。映像內 JS/CSS 與前輪 24 項核心及 20 項回歸使用的成品逐位元相同。版本 metadata 變更後 uv sync --locked、typecheck／build 通過，依賴、後端與 migrations 未變。
- 先正常停止 app／backup，由舊 runtime 建立 backup 與成組 export，archive 及所有成員 hash 驗證通過。停寫 checkpoint：`manual-export-20261004T025713572779Z-ecd8beee.db`；舊 env／export 保留在受限 ignored `data/release-0.3.4/`。
- app／backup／ops 同批固定新 digest；沿用 `fucheng-home_data`／`fucheng-home_home_backups`，沒有 migration 或重新灌入資料。schema 0010、integrity ok、FK errors 0；16 張業務表指紋一致，342 會員、2 場次、81 報名、2 安排保存版、2 公告均保留。
- app／backup healthy；可信 loopback 的登入／讀取／登出、Secure/HttpOnly 前綴 Cookie、匿名 401、錯誤 Host 400、裸 API 404、備份狀態讀取通過。HP Caddy 的 `/`、`/orderflow/`、`/fucheng/` 與府城 health 均 200。
- 公開瀏覽器實際載入 `index-1ACfpEqv.js`／`index-OjSq-5uT.css` 並顯示公告。沿用既有 session 的管理頁確認素食名單按鈕、備份旁管理員名稱及「名單操作」已消失；沒有在正式資料拖曳、保存或新增業務資料。使用者原分頁未被重新整理或修改。
- 4090 SSH forward active；HP Caddy／cloudflared active，Caddy SHA 仍為 `0e9b6473c465309ea5fad4dde547b9f286d3a363acd69142a3bd3157505da209`。未更改入口、DNS、Tunnel、SSH、服務目錄或其他應用；ASUS 不承接府城 app。

帳密沿用，使用者重新整理頁面即可試用。工程及公開讀取檢查不代替 Android／iPhone 真機手感驗收；無斷電／重開機或真正 Turnstile 報名測試。舊映像、資料卷、備份及隔離合成證據保留；兩個合成 app 已停止，沒有 prune 或 down -v。回退可恢復 0.3.3 程式；若還原資料則另以匹配 image/schema 的新目標保留後續寫入。同機備份仍不是異地備份。


## 0.3.5 素食名單與管理列排版部署（2026-10-04）

先合併 [PR #9](https://github.com/momonong/fucheng-players-system/pull/9)，發布 [v0.3.5](https://github.com/momonong/fucheng-players-system/releases/tag/v0.3.5) 與 Docker Hub `0.3.5`／`latest`，兩個標籤遠端 digest 相同且拉回 image ID 正確後，才升級既有 4090 project。

- 合併／tag／映像來源：`36469149d9bff1e5d6aacf7530ca35d078b1b3e9`。
- Digest：`sha256:a6a6a8cda18517ed082bbd5c13545d21e4d729bf75e5c3c3cd0d5b4d312f9ca2`；Image ID：`sha256:04b30d787f44ff00cfe9b4cc2371bd0188d8ff9081920ce59178ce149f59222a`。
- Source manifest：`0a480d64505d859240b502725fbee9e1cc162194ac83f858c2ab51cac0e8ec5a`，75 個 allowlist 檔案；乾淨已提交來源、context audit 通過，沒有 data／秘密／備份／舊 dist。
- 全後端 211 passed（2 個既有棄用警告），uv sync --locked、production build／typecheck、npm high audit（0 vulnerabilities）及 diff／秘密掃描通過。根路徑與 `/fucheng/` 合成 image 驗 health、登入登出、Cookie Path、匿名拒絕及完整性；映像 JS/CSS 與本輪桌面／手機測試成品逐位元相同。
- 更新前正常停止 app／backup，以舊 runtime 建立 backup／成組 export，archive 及所有成員 hash 正確。停寫 checkpoint：`manual-export-20261004T053232217100Z-7fd06fa2.db`。私密 env／備份與完整證據保存在 ignored `data/release-0.3.5/`；不提交來源資料或帳密。
- app／backup／ops 同批固定新 digest，原 named volumes 保留；無 migration／reseed，schema 0010、integrity ok、FK errors 0。16 張業務表內容 fingerprint 不變：342 會員、2 場次、81 報名、2 安排保存版、2 公告。
- app／backup healthy；loopback 管理員登入／讀取／登出、Secure/HttpOnly 前綴 cookie、匿名 401、錯誤 Host 400、裸 API 404、備份狀態通過。HP Caddy 的根首頁／OrderFlow／府城首頁及 health 均 200。
- 公開 HTTPS 實際載入 `index-NQDf3-Ql.js`／`index-D48eAE_k.css`。獨立瀏覽器分頁沿用既有 session，確認管理列 flex-end、名稱右側與狀態列齊邊、28px 圓形、名單可開啟／關閉。沒有在真實資料拖曳、保存或增刪；使用者原分頁未重新整理。
- HP Caddy／cloudflared 與 4090 SSH forward active，Caddy SHA 仍為 `0e9b6473c465309ea5fad4dde547b9f286d3a363acd69142a3bd3157505da209`。沒有入口、DNS、Tunnel、SSH 或其他 app 變更，ASUS 不承接府城 app。

重新整理頁面即可載入新版，帳密沿用。兩個合成 app 已停止，合成 volumes、舊映像、原資料卷與備份保留，沒有 prune／down -v。沒有斷電／Windows 實機／真實 Turnstile 或 Android／iPhone 手感驗收；同機備份不等於異地備份。
