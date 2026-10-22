# 家中 4090 試用部署

2026-10-22 台北時間19:58:47，4090既有 [momonong.me/fucheng/](https://momonong.me/fucheng/) 已更新至正式0.4.3固定registry digest，app／backup健康，schema維持`0012_device_reports`，球館健檢接收沿用啟用。驗證登入前22表全欄全值、帳密及原sessions相同，HTTPS登入驗證後19張非認證表仍相同；既有一份合成健檢報告保留，沒有新增報告。詳見[0.4.3正式發布與部署](#043-健檢回傳正式發布與部署2026-10-22)。先前[未提交snapshot部署](host-report-home-deployment-20261022.md)及下方舊版本紀錄保留為歷史，不代表現用image身份；球館Windows與人工驗收仍未完成。

## 主機與入口

使用 4090 的原生 Linux Docker Engine（context `default`）。單一 app image 包含前端與 FastAPI，不使用 GPU。入口沿用 selfhost-servers 的 Cloudflare Tunnel → HP Caddy，透過加密 SSH reverse forward 到本機 loopback；不另建 Tunnel、不占用首頁或 OrderFlow 路由。Caddy 候選與現用狀態由 selfhost-servers 的 `docs/fucheng-ingress-preparation.md` 管理。

目前依序疊加 `compose.yaml`、`compose.home.yaml`、`compose.report-upload.yaml`；後續操作須保留第三份 receiver overlay：

- app 僅發布 `127.0.0.1:8064`，HP forward 僅監聽 `127.0.0.1:18084`。
- app 與備份各使用本 project 的 Linux named volume；不掛 Windows 路徑，也不共用其他 app 資料。
- app 僅信任指定 Docker bridge gateway。網路允許 Turnstile Siteverify 所需 outbound HTTPS。
- 不啟用 base Compose 的 cloudflared、ngrok 或 https-test profiles。
- `pull_policy: never`：正式release使用固定registry digest；現用0.4.3已核對registry manifest、拉回的native image ID及source manifest。先備妥並核對映像，再操作。

## 設定與操作

從專案根目錄執行。全新部署時，才將 `deploy/docker/home.env.example` 複製至 Git 忽略且受限的 `data/home-deployment/home.env`，依現場確認網段／port；既有站點沿用現用私密設定。Turnstile sitekey 使用真正的 momonong.me widget，secret 放受限本機檔案，只提供路徑；secret 必須能由容器 UID 10001 讀取。不要把 secret 值放入命令、Git 或聊天。

既有站點的 `data/home-deployment/home.env` 已持久更新為0.4.3固定registry digest，原device ID及`FUCHENG_REPORT_UPLOAD_TOKEN_FILE`私密檔案路徑保留，不要用範例覆寫。上傳token與原Turnstile secret分開，receiver overlay只對app掛載`/run/secrets/report_upload_token`，原Turnstile secret保留；一般工具ZIP不含秘密，球館端另行私密配置。現用schema0012不可直接換回舊registry 0.4.2映像；前一同schema snapshot保留供審查回退，詳見[本次紀錄](#043-健檢回傳正式發布與部署2026-10-22)。

```bash
dc=(docker --context default compose --env-file data/home-deployment/home.env
    -f deploy/docker/compose.yaml -f deploy/docker/compose.home.yaml
    -f deploy/docker/compose.report-upload.yaml)
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


## 0.3.6 手機整張方塊拖曳部署（2026-10-05）

先合併 [PR #11](https://github.com/momonong/fucheng-players-system/pull/11)，發布 [v0.3.6](https://github.com/momonong/fucheng-players-system/releases/tag/v0.3.6) 與 Docker Hub `0.3.6`／`latest`。兩個標籤遠端 digest 相同且拉回 image ID 相符後，才升級 4090 的既有 `fucheng-home`。

- 合併／tag／映像來源：`3a702d231b711781d5b6236a4861ab7544237f63`。
- Digest：`sha256:1fa1efc8361aa393327e1db8a7b65e5f77d23cda76fa610dc0cee60335b5599a`；Image ID：`sha256:e3335dfabaec39a50aed7d7b9f851f93ea4e6acff29774a922dc295a5d983878`。
- Source manifest：`3d9b85e17bd57a0c20dc01c327087f7d3f9d29b1015de026832c04967da3f6e8`；75 個 allowlist 檔案，乾淨已提交來源，context audit 通過，無 data／秘密／備份／舊 dist。建置生成的 tracked manifest 已恢復原內容，發布證據保留在受限 ignored `data/release-0.3.6/`。
- 前端根路徑／前綴的桌面與手機 18 項通過；全後端 211 passed（2 個既有棄用警告）、locked sync、build／TypeScript、npm high audit（0 vulnerabilities）通過。新 image 在獨立 root／prefix project（8320／8321）通過 health、登入登出、Cookie Path、匿名拒絕及完整性；JS/CSS 與 E2E 成品逐位元相同。
- 更新前正常停止 app／backup，使用 0.3.5 runtime 成組備份與 export，archive 及所有成員 hash 正確。停寫 checkpoint：`manual-export-20261005T015509704604Z-d3e08ab6.db`。原 env、匯出與舊 image 保留，無 migration／reseed。
- app／backup／ops 同批固定新 digest，原 `fucheng-home_data`／`fucheng-home_home_backups` volumes 保留。schema `0010_deployment_report`、integrity ok、FK errors 0；16 張業務表指紋一致，342 位會員、2 比賽、81 報名、2 安排保存版及 2 公告保留。
- app／backup healthy；可信 loopback 登入／讀取／登出、Secure/HttpOnly 前綴 Cookie、匿名 401、錯誤 Host 400、裸 API 404、備份狀態讀取通過。HP Caddy 根首頁、OrderFlow、府城首頁及 health 均 200。
- 公開 HTTPS 瀏覽器載入 `index-BWyKMIan.js`／`index-DXZ2MNZr.css`，首頁兩則公告及管理登入表單正常。獨立驗證分頁沒有既有 session，故本輪不宣稱公開登入後手勢驗收；沒有在真實資料拖曳、保存或增刪，使用者原分頁未重整。
- HP Caddy／cloudflared／OrderFlow forward、4090 府城 SSH forward active；Caddy SHA 仍為 `0e9b6473c465309ea5fad4dde547b9f286d3a363acd69142a3bd3157505da209`。沒有 Caddy／Tunnel／DNS／SSH／服務目錄或其他應用變更，ASUS 未承接府城 app。

重新整理即可試用，帳密沿用。兩個合成 app 已停止，volumes、舊 image、原資料與備份保留，未 prune／down -v。未做 Android／iPhone 手感、Windows／斷電恢復或真實 Turnstile 驗收；同機備份不等於異地備份。程式回退可恢復 0.3.5；資料還原仍以匹配 image/schema 的新目標保留後續寫入。


## 0.3.7 介面整理部署（2026-10-05）

先前已完成 [PR #13](https://github.com/momonong/fucheng-players-system/pull/13)、[v0.3.7 Release](https://github.com/momonong/fucheng-players-system/releases/tag/v0.3.7) 與 Docker Hub 發布；本輪使用者另行授權部署後，才更新既有 4090 `fucheng-home`。HP 仍僅負責入口，ASUS 未承接應用。

- Source/tag：`39f5d8e6359358495f7eff4009bfba1dc0840941`；digest：`sha256:47b9ab0978e8f2934a6efd82413d6b471286c1d2ee6781197768b6faccfda9aa`；image ID：`sha256:6ca47d6b397a45a8a69b1871a7e1f4fb0f988adf1802f2095ff37da962f9ac02`。
- 停止 app／backup 後，由 0.3.6 runtime 建立 backup 與 export，核對 archive 及全部成員 hash；checkpoint `manual-export-20261005T035826098080Z-6fe2a11c.db`。受限 env／export／證據保存在 ignored `data/release-0.3.7/`。
- app／backup／ops 同批固定新 digest，沿用 `fucheng-home_data` 與 `fucheng-home_home_backups`，無 migration／reseed。schema `0010_deployment_report`、integrity ok、FK errors 0；16 張業務表 fingerprint 前後相同，342 會員、2 場次、81 報名、3 個安排保存版、2 公告保留。
- app／backup healthy，app 僅發布 127.0.0.1:8064；可信 loopback 登入、讀取、登出、Secure/HttpOnly 前綴 Cookie、匿名 401、錯誤 Host 400、裸 API 404 與備份狀態通過。HP Caddy 根首頁、OrderFlow、府城首頁及 health 均 200。
- 公開瀏覽器重新載入確認 `index-DVvaf_nO.js`／`index-mPsL-t1K.css`、2 則公告、會員分級表 342 人及管理登入表單；公開首頁與會員頁無綠色標題區，會員頁無橫向溢出。沒有用真實資料進行拖曳、保存或報名。
- HP Caddy／cloudflared／OrderFlow forward 與 4090 府城 forward active。Caddy SHA 仍為 `0e9b6473c465309ea5fad4dde547b9f286d3a363acd69142a3bd3157505da209`；未變更 Caddy／Tunnel／DNS／SSH 或服務目錄。

舊 0.3.6 映像、設定、資料卷與停寫備份保留；未執行回退、prune 或 down -v。公開瀏覽器沒有既有管理 session，本輪登入後檢查採可信 loopback；公開管理操作與 Android／iPhone 手感由使用者試用，未宣稱真機驗收完成。


## 0.3.8 頁首配色部署（2026-10-05）

[應用 PR #14](https://github.com/momonong/fucheng-players-system/pull/14) 合併並發布 [v0.3.8](https://github.com/momonong/fucheng-players-system/releases/tag/v0.3.8) 及 Docker Hub `0.3.8`／`latest` 後，更新 4090 既有 `fucheng-home` app／backup。最上方導覽採深綠，管理頁首採淺灰綠；連結、目前頁面、備份提示及鍵盤焦點同步配色，保留手機與桌面操作及響應式留白。

- Source/tag：`12fdd5a0d4d5c02d56245454ab4003d2fc6922df`；digest：`sha256:10e016ac08c5fa7187dfa9ee3910041f38e8ccae2b711eded57e3839af6e739e`；image ID：`sha256:7e92c098e689cab27b1692ca3d1ecd4fe07a10c47c2ae55a3d30f74121f9b6ed`。
- Source manifest：`58679e0cd4b05853c5fe8b660b8dc0f4ec02c4a832776153d1cd8bcab792cfc2`；75 個 allowlist context 檔案，乾淨已提交來源，無資料、秘密、備份或舊成品。
- uv locked sync、typecheck／build、npm audit（0 vulnerabilities）、後端 211 passed、prefix 桌面／手機 4 passed；30 組 360–3840px 版面檢查與 9 組至少 5.11:1 文字對比核對通過。映像 root／prefix 合成驗證通過，資產與測試成品一致。未宣稱 GitHub Actions 測試或真機人工驗收。
- 停止 app／backup 後由 runtime 成組備份／export；checkpoint `manual-export-20261005T063819720898Z-f06846e4.db`，archive 及全部成員 hash 已核對，原 env、映像、volume 及匯出保留於受限位置。
- schema `0010_deployment_report`、integrity ok、FK error 0；16 張業務表 fingerprint 完全不變：342 會員、2 比賽、81 報名、3 保存版。app／backup healthy，無 migration 或資料重建。
- 可信 loopback 登入／讀取／登出、Secure/HttpOnly 前綴 Cookie、匿名拒絕、錯誤 Host 與裸 API 邊界通過。HP Caddy 根首頁、OrderFlow、府城與 health 均 200；Caddy／Tunnel／SSH 設定不變。
- 公開 HTTPS 瀏覽器已核對新版資產及深綠導覽，會員分級表與管理登入表單正常。管理配色由合成桌面／手機截圖驗證；公開登入後實際使用手感留待使用者試用。

本機證據在 ignored `data/release-0.3.8/`，帳密、備份及資料庫不進 Git。手機真機、真正 Turnstile 報名、斷電恢復與異地備份仍不在本次驗證內。


## 0.3.9 級數欄自由調整部署（2026-10-05）

先合併 [PR #16](https://github.com/momonong/fucheng-players-system/pull/16)，推送版本標籤並發布 [v0.3.9](https://github.com/momonong/fucheng-players-system/releases/tag/v0.3.9) 與 Docker Hub `0.3.9`／`latest`，再更新 4090 既有 `fucheng-home` app／backup。空級數欄可刪除並加回，含選手先移走；保存、歷史、列印與 Excel 依實際欄位呈現。

- 合併／tag／映像來源：`cce12db6a327892b6b703c0fda6cefefcecb524d`。
- Digest：`sha256:72a8582278bd6412432a1e32ec265c2018215053660defd13dccaba32dca8262`；image ID：`sha256:eb2e876eb3420adbbd2a385578941be067f8c5ef844d07a56cf78f4376251ce4`。兩個 Docker Hub tag 的 digest 相同，遠端 config digest 與拉回 image ID 均核對相符。
- Source manifest：`c0b1f7d9f16422b811c1a77036f0ab06f52e37f823c6581e9e67e13e918900dc`，75 個 allowlist 檔案；context audit 通過，無資料、秘密、備份或舊成品。
- 後端完整217項＋候補遞補補測1項、桌面／手機新流程2項及匯出／PDF解析證據沿用相同功能來源。升版 locked sync、typecheck／build 通過，npm audit 0 vulnerabilities；映像 JS/CSS 與上述 E2E 成品逐位元相同。
- 根路徑及 `/fucheng/` 獨立合成映像測試均通過 health、登入登出、Cookie 路徑、匿名拒絕、資產一致性、空級數欄刪除／加回與資料完整性。首次子路徑測試遇 Docker 預設地址池耗盡，核對網路後改用本次專屬10.203.39.0/24及10.203.40.0/24重驗；保留既有網路／volume，不 prune。測試 app 已停止。
- 更新前正常停止 app／backup，以舊 runtime 成組 backup／export，archive及成員 hashes 全通過。停寫 checkpoint：`manual-export-20261005T091651591832Z-b3408121.db`；私密備份、舊 env 及證據留在 ignored `data/release-0.3.9/`。
- 原 `fucheng-home_data`／`fucheng-home_home_backups` 保留，無 migration或reseed；schema `0010_deployment_report`、integrity ok、FK error 0。16張業務表完整內容 fingerprint 不變，342會員、2場次、81報名、3安排保存版、45安排操作及2公告保留。
- app／backup 同一新 image ID 且 healthy，備份健康正常。可信 loopback 管理員登入／讀取／登出、Secure/HttpOnly前綴Cookie、匿名401、錯誤Host400及裸API404通過。HP Caddy 根首頁、OrderFlow、府城首頁及health均200。
- 公開HTTPS瀏覽器載入新版 `index-DvG74ytG.js`／`index-DKqNSIay.css`、首頁、342位會員與管理員登入表單。未在真實資料測試刪欄／調級；公開登入後操作與手機真機手感仍待使用者驗收。
- 4090轉送、HP Caddy／cloudflared／OrderFlow轉送 active。Caddy SHA保持 `0e9b6473c465309ea5fad4dde547b9f286d3a363acd69142a3bd3157505da209`；無入口、DNS、SSH、其他應用或ASUS變更，服務目錄沿用。

精簡欄位開始使用後，不可因schema相同就直接降回強制十欄的舊app；新版啟動後不自動降版，先保留資料排查並向前修復。必要還原使用匹配備份與新目標，保留後續操作及故障庫。帳密沿用；同機備份仍不代表異地備份。


## 0.4.0 管理員管理部署（2026-10-20）

使用者選擇升級既有家中試用站並保留目前資料與登入帳號後，更新原生 Linux Docker Engine（context `default`）的 `fucheng-home` app／backup；球館電腦未操作。

- Image digest：`sha256:bf9126c1d3302474a639999b8987648aa4c813e97edbc22cdc2c0f3f2f37cfe8`；linux/amd64 manifest `sha256:2fbb98aa541a0e6f553adbeefe3cf9ed6f0de99552a079327a55b76577adf049`、native image ID `sha256:0d9c339683c7b60f1bf9c3fc3fe8a9853be4b6d45da0b85e50754e18897f2375` 與 source manifest `71cc92a0a535037a9348afc343e4fda6ec9155224460f090a3e3631b11fa6138` 均已核對。
- 先停止 app／backup，用 0.3.9 runtime 成組備份 DB＋媒體並 export；archive 及全部成員 hash 通過。停寫 checkpoint 為 `manual-export-20261020T093411276937Z-eef84249.db`。原 env、export、舊 image、原 volumes 與新目標回退設定／方案保存在受限位置，未執行回退。
- 由新版 runtime 經 writer／maintenance guard 明確 `ops migrate` 至 `0011_admin_management`，沒有 init、bootstrap、重設密碼或新增管理員。啟動前 20 張舊表的所有既有欄位逐列一致，包含 4 個管理員、帳密及原 sessions；新增欄位預設正確，`admin_audits` 為空，未補造歷史。
- app／backup 同批固定新版 image，沿用 `fucheng-home_data`／`fucheng-home_home_backups`，兩者 healthy；schema、integrity ok、FK errors 0 及新版 runtime 成組備份通過。驗證後 16 張業務表最終指紋仍相同：342 會員、2 場次、81 報名、6 個安排保存版、82 個安排操作及 2 則公告保留。
- 可信 loopback 的既有帳密登入／管理 GET／登出、4 個既有管理員清單與空稽核、Secure／HttpOnly／`/fucheng/` Cookie、匿名管理 401、錯誤 Host 400、裸 API 404 及前綴重新導向通過；JS `index-gKPFKSNq.js`、CSS `index-BFqDcH_A.css` 與已驗證 release 成品一致。未在真實資料新增、拖曳、保存或修改會員／比賽／報名。
- 公開內建瀏覽器重新載入 `/fucheng/admin`，登入表單與新版 JS／CSS 正常；透過導覽開啟首頁後，公告與比賽時程完整渲染並完成視覺核對，截圖保存於 `data/deployment-20261020/public-home-v040.jpg`。未在公開瀏覽器登入、新增管理員或報名。
- 入口、8064 loopback、HP 專用 SSH forward、Caddy／Tunnel／DNS 與其他服務均沿用，沒有入口設定變更。本機持續 forward active／enabled；一般 `hp-server` SSH 登入本輪被拒絕，未換金鑰或變更 SSH，因此未宣稱重新查驗 HP 服務或設定 hash。
- 已依本次清理授權移除本專案結束的測試資源：default context 22 個容器、16 個空網路、8 個舊映像；desktop-linux context 4 個容器、3 個舊映像。全部資料卷、回退所需版本／備份及其他服務保留，沒有 prune 或 down -v。

部署與驗證證據位於 ignored `data/deployment-20261020/v040-home/`；私密目錄 0700，原 env、DB 與 export 0600，不提交憑證、密碼 hash 或資料庫。真實 Turnstile 成功報名、公開登入後管理操作、Android／iPhone 手感、斷電／重開機與球館 Windows 實機尚未驗收；同機備份不等於異地備份。0.3.9 不可直接啟動現有 0011 資料；必要回退須保留故障庫，使用升級前備份還原至新目標並配匹配 image/schema。


## 名單 A 版 snapshot 更新（2026-10-20）

使用者指定會員／比賽均採 A 版、不顯示級數人數，並確認只有會員名單按姓名筆畫排序，比賽名單及既有格位不重排。台北時間 23:33（UTC 15:33）完成既有 `fucheng-home` 更新；球館電腦未操作。

- 本次為 `fix/print-roster-layout` 的未提交工作樹 snapshot，HEAD `b1859eaf13d6ce0028fd749880d6819ce09258a3` 不是完整來源。現用 `local/fucheng:snapshot-1115779cac0436ff`，native image ID `sha256:6727f8c404a4576b9c4e7930f332ec605c595e7a508b2700bcb8a63cb595c5b1`；source manifest `1115779cac0436ff8054e8c1973089ec8d408069a7b97735651e5f809513cb85`。沒有 Git commit／push、tag／Release 或 registry 發布。
- 明確以 `DOCKER_CONTEXT=default` 執行 `scripts/deployment_package.py`；79 檔 allowlist context、context-audit、freeze 與內嵌 manifest 一致，未包含 data、output、憑證、DB、備份或既有 dist。原 tracked source manifest 原樣保留，完整 snapshot context 留在本輪證據。後端、migration、runtime、Dockerfile 及依賴等 42 檔與 0.4.0 相同。
- 獨立合成目標 `fucheng-print-a-smoke-1115779c`／loopback 8067 通過 `/fucheng` health、登入／登出、匿名拒絕、Cookie 路徑、資產與 schema／integrity／FK。合成容器已停止，兩個合成 volumes 保留。映像與實測成品 JS `index-BrNtzusK.js`、CSS `index-Cv2u8fR5.css` 逐位元一致。
- 停止現站 app／backup，以舊 0.4.0 runtime 成組備份 DB＋媒體並 export，archive 及全部成員 hash 通過。停寫 checkpoint：`manual-export-20261020T153243382115Z-fb8f42f9.db`。原 env、舊 image、原 volumes 及成組備份保留；現站只修改 `FUCHENG_IMAGE`，沒有 init、migration、bootstrap 或帳號變更。
- 同 image 的 app／backup 均 healthy，schema 仍為 `0011_admin_management`、integrity ok、FK errors 0。啟動前後 21 張現有資料表全部欄位逐列相同，含管理員密碼及原 sessions；登入／GET／登出後，16 張業務表及管理員／管理稽核仍相同。342 會員、2 場次、81 報名、6 保存版、82 安排操作、4 管理員、2 公告及停寫時的 1 張媒體完整保留；未為驗證寫入真實業務資料。新版 runtime 成組備份也通過。
- 可信 loopback 的 health、既有帳密登入／管理 GET／登出、Secure／HttpOnly／前綴 Cookie、匿名管理 401、錯誤 Host 400、裸 API 404 及資產 hash 通過。列印、會員筆畫、白色 override／跨頁 merge 與 XLSX 等同來源驗證詳見 [列印驗證紀錄](print-layout-verification-20261020.md)；未把較廣手機舊互動流程的前置 timeout／422 記成全套通過。
- 公開內建瀏覽器確認新版 JS／CSS、342 位會員、10 個不帶人數的級數標頭；會員預覽 DOM 為 2 個 A4 頁區塊、完整 342 姓名、14 pt、所有格線 1 CSS px，登入表單 gap 為 16 px。以既有部署帳號登入後唯讀查看原 80 人場次的安排預覽：1 個 A4 頁區塊、80 個非空人員格、11 個 body 行、甲乙丙丁四個雙欄合併、姓名 16 pt（21.3333 px）、th／td 四邊均為 1 CSS px；登出回登入頁。沒有編輯、保存、拖曳或實際列印。`public-members-preview.png`／`public-competition-preview.png` 位於本輪受限證據；實際 PDF 頁數／字元邊界證據使用合成 342／80 人樣本，與實站 DOM 檢查分開。21 表及原 sessions 保留檢查的時間界線為 UTC 15:33:18、後續登入驗證前；不把之後的正常 session 建立／撤銷當成資料不符。
- 共用契約固定為 `momonong/selfhost-servers@5a8894ed3c00719f5fed613c706520e2d2c1b4cf`，2026-10-20 經可信遠端 default branch 核對，按該 SHA 讀取全文。既有 `/fucheng/`、8064、HP forward／Caddy／Tunnel／DNS、其他服務與拓樸均未改；未重試已拒絕的一般 HP SSH，也未宣稱重驗現用 Caddy hash。無服務目錄發布或 Docker 清理。

受限 ignored 證據位於 `data/deployment-20261020/print-a-home/`，最終映像與 context 在 `release-readable/`；原 env、DB／媒體 export 權限受限，秘密不進文件或 Git。沒有實體列印、Android／iPhone 真機、真正 Turnstile 成功報名、斷電／重開機或異地備份驗收。本次 schema 與後端相同，資料確認正常時可停寫後只回舊 0.4.0 image 並保留原 volume；若有資料疑慮，仍須保留故障庫，以匹配備份還原新目標。


## 會員卡片與圓圈素標記 snapshot 更新（2026-10-21）

沿同一表格／試用站目標更新，台北時間 11:04（UTC 03:04）完成。會員網頁恢復深綠分離緊湊卡片，A 版列印頁面結構保留；圓圈直徑 16 pt、框線 0.75 pt、旁距 2 pt，圈內「素」為 12 pt／600，兩處列印圖例同步。

- 現用 `local/fucheng:snapshot-a8b9f2243c65a79c`，native image ID `sha256:2f9d5f3bcd874684d71687e6202265cd01ad06677b043db41f046e09a8105014`；source manifest `a8b9f2243c65a79c512fd3fb16bb94578aaffc331f8245d68797eb9f923b1ce9`。這是未提交工作樹 snapshot，HEAD 不代表完整來源，沒有 commit／push、版本或 registry 發布。舊 `snapshot-1115779cac0436ff`／`6727f8c4…` 及其 context 保留。
- 以原生 default context 的 allowlist builder 建置，父證據目錄 0700、builder umask 022。79 檔 context／audit／freeze／內嵌 manifest 一致，排除資料、憑證、備份、output 與既有 dist；原 tracked source manifest 還原。相對前一 snapshot 只改 `styles.css` 與 `ArrangementPrint.tsx`／`CompetitionManager.tsx` 各一處 legend；後端、schema、runtime 及依賴等 42 檔相同，Compose 沿用。
- 最終測試 freeze 為 `data/print-circle-type-20261021/freeze.json`；JS `index-COwDRJex.js`、CSS `index-B3QvLKWe.css` 與映像及現站資產逐位元一致。獨立合成目標 `fucheng-cards-veg-smoke-a8b9f224`／8067 通過 prefix、health、登入／登出、匿名拒絕、Cookie、資產與完整性；合成容器已停，volumes 保留。
- 停止現站 app／backup，以原 snapshot runtime 成組備份 DB＋媒體並 export，archive 及全部成員 hash 通過。停寫 checkpoint：`manual-export-20261021T030332093317Z-bc470e4a.db`。只替換私密 env 的 `FUCHENG_IMAGE`，同批更新 app／backup，沒有 init、migration、bootstrap、密碼或帳號變更，原 data／backup volumes 保留。
- app／backup healthy，schema `0011_admin_management`、integrity ok、FK errors 0。登入前 21 張現表所有欄位及原 sessions 逐列一致；既有帳號登入／管理 GET／登出後，16 張業務表、管理員及管理稽核不變。342 會員、2 場次、81 報名、6 保存版、82 安排操作、4 管理員、2 公告與 1 張媒體保留。新 runtime 成組備份與健康檢查通過；沒有真實業務寫入。
- 公開內建瀏覽器載入指定新資產：1280 px 會員頁為 5 欄、10 px gap、12 px 圓角、`#246b5e` 深綠白字、18 px 姓名且無橫向溢出，10 級表頭無人數；會員預覽 DOM 保留 2 個頁區塊／342 姓名／14 pt。既有帳號登入後只讀查看原 80 人安排：1 個預覽頁區塊、80 個人員格、4 個雙欄合併、2 個選手圈素及 1 個圖例圈素。圓徑 16 pt、圈內 12 pt／600、邊框 0.75 pt／50% 圓角，姓名 16 pt，th／td 四邊均為 1 CSS px；圖例僅圈素加「素食」。已登出並停在會員頁，沒有編輯、保存、拖曳或實際列印。實站只核對預覽 DOM，實際 PDF 頁數／字元邊界來自分開的合成證據；收據為 `public-browser-verification.json`，截圖為 `public-members-cards.png`／`public-competition-circle.png`。
- 既有 `/fucheng/`、loopback 8064、SSH forward、Caddy／Tunnel／DNS、其他服務均未變；無清理、HP SSH 重試或服務目錄發布。同階段沿用已全文核讀的 `selfhost-servers@5a8894ed3c00719f5fed613c706520e2d2c1b4cf` 契約與指南 pin `25791af93cadffdbf9b41be902f8da063f32ffde`，不宣稱重驗 live Caddy hash。

受限證據在 ignored `data/deployment-20261021/cards-vegetarian-home/`，包含 snapshot／manifest、合成 smoke、停寫成組 export、21 表／帳密保留布林、登入與備份收據；DB、媒體 archive 及 env 保持 0600，不保存秘密到文件或 Git。實際 PDF 規格驗證使用 freeze 的合成樣本，實站預覽 DOM 與其分開記錄。沒有實體列印、真機、真正 Turnstile、斷電／重開機或異地備份驗收。必要回復可在確認 schema／資料正常後停寫只回原 snapshot；資料有疑慮時仍以匹配備份還原新目標並保留故障庫。


## 0.4.1 正式發布與部署（2026-10-21）

[PR #20](https://github.com/momonong/fucheng-players-system/pull/20) 合併來源、`v0.4.1` tag 與 [GitHub Release](https://github.com/momonong/fucheng-players-system/releases/tag/v0.4.1) 指向 `2a4ff1aec8d4554cce13473db0624d75bc4def8a`。從乾淨已提交來源建置後發布 Docker Hub `0.4.1`／`latest`，台北時間 15:52（UTC 07:52）更新既有 `fucheng-home`；後續維運文件提交不改此產品建置來源。

- Registry **manifest digest**：`sha256:d9a75ee568e651ce9dbaf7877dcdeda8acad1b57a5c75aebec481324146d7b74`，media type 為 Docker distribution manifest v2，沒有額外 index；linux/amd64 manifest 即同值。兩個遠端 tag digest 相同，固定 digest 拉回後的 **config/native image ID** 為 `sha256:67d7830411fdbe0e4505fe2d49f2271c5fc7c1ab105c3015b9830cc79d0b095b`，與已測建置一致。現站固定使用 `momonong/fucheng-players-system@sha256:d9a75ee568e651ce9dbaf7877dcdeda8acad1b57a5c75aebec481324146d7b74`，不使用浮動 tag。
- Source manifest `d3730a219832da470d7850f7c4103fbba5b07fcfd676716e1cda7abd4ce971c8` 標記 `committed-git-release`；79 檔 allowlist、freeze、context-audit 與內嵌 manifest 一致，原 tracked manifest 已還原，新 manifest 保留供發布紀錄。最終 JS `index-tvNyHE5u.js`／CSS `index-PsSUwEnH.css` 與 Vite 7.3.7 最終測試成品逐位元相同。根路徑與 `/fucheng` 使用獨立合成 data／secret volumes，health、登入／登出、Cookie 路徑、匿名拒絕、資產及完整性均通過；兩個合成容器已停止，資料卷保留。
- 更新前停 app／backup，由舊 `snapshot-a8b9f2243c65a79c` runtime 成組備份 DB＋媒體並 export，archive 及每個成員 hash 通過；checkpoint `manual-export-20261021T075145123714Z-57412afa.db`。只修改私密 env 的 `FUCHENG_IMAGE`，同批 app／backup 換固定 registry digest，無 init、migration、bootstrap 或帳密修改，保留原 volumes、舊 snapshot／image／context 與原 env。
- schema 0011、integrity ok、FK errors 0，app／backup healthy。登入驗證前 21 張現表所有欄位及原 sessions 逐列相同；登入／GET／登出後，16 張業務表與 admins／admin_audits 共 18 表仍相同。342 會員、2 場次、81 報名、6 保存版、82 安排操作、4 管理員、2 公告及 1 媒體保留；新版成組備份、Secure／HttpOnly／前綴 Cookie、匿名 401、錯誤 Host 400 與裸 API 404 通過，沒有真實業務寫入。
- 公開 HTTPS 瀏覽器重新載入確認新資產、342 會員／10 張深綠卡片及 10 px gap；原帳號登入後，80 人安排預覽 DOM 為 1 頁區塊，2 個選手圈素上移 4 CSS px（3 pt），姓名 16 pt、圖例未移動；會員預覽為 2 頁區塊／342 姓名／14 pt。已關閉預覽並登出，停在公開會員頁，沒有業務寫入或真實 PDF／實體列印。收據 `public-browser-verification.json`／`root-container-verification.json` 與截圖 `public-arrangement-preview.png` 位於本輪證據；合成 PDF 與實站 DOM 分開核對。
- 沿用既有 8064／`/fucheng/`／HP forward／Caddy／Tunnel／DNS 與其他服務；未重試 HP SSH、未清理或發布服務目錄。同階段共用契約仍為 `selfhost-servers@5a8894ed3c00719f5fed613c706520e2d2c1b4cf`。同 schema 且資料確認正常時可停寫回舊 snapshot；資料有疑慮則保留故障庫，以匹配備份還原新目標。

完整 typed registry chain、build／smoke、受限 env／export 與資料保留收據位於 ignored `data/release-0.4.1/`；`image/source-manifest.json` 對應正式來源，`home-deployment/` 保存部署證據。registry digest 與 config/image ID 分開記錄，不將 Docker Desktop store ID 代替 registry digest。實站 DOM、合成 PDF、實體列印與真機驗收維持分層；沒有實體列印、真正 Turnstile、重開機、球館 Windows 或異地備份驗收。


## 0.4.2 列印表頭與格線部署（2026-10-21）

[PR #22](https://github.com/momonong/fucheng-players-system/pull/22)、`v0.4.2` tag 與 [GitHub Release](https://github.com/momonong/fucheng-players-system/releases/tag/v0.4.2) 的正式來源為 `08b12bff6a8976434b55300f7cb1d9f1dde9e3b0`。乾淨已提交來源經 allowlist 建置及 79 檔 context audit 後，發布 Docker Hub `0.4.2`／`latest`；台北時間 17:21（UTC 09:21）同批更新既有 app／backup。產品後端、runtime、migration、Compose 與依賴未變。

- Registry **manifest digest**：`sha256:faaa578ad5fa48a642f6ee80892986b20af82286111bf9f1f5309556236752cd`，Docker manifest v2、linux/amd64，無額外 index；兩個遠端 tag 相同。固定 digest 拉回後的 **config/native image ID** 為 `sha256:0bb6bdcdfab16b0c627589cd895f140bd3bd52ccbf1358b085d0748361e2d46f`，與已測映像一致。現站固定使用該 registry digest，發布前確認版本 tag 不存在、原 latest manifest／config 未漂移。
- Source manifest：`92c4bde59dd918f75707a43096c151248ab616cc0922c46187ab252ae46c9e0a`。最終資產 `index-Bq87i6rl.css`／`index-DR8KBonb.js` 與工程 freeze byte 相同；獨立 root／`/fucheng` 合成 smoke 的 health、登入／GET／登出、Cookie、匿名權限與 schema 檢查通過，測試容器已停止。
- 停止本 project app／backup 寫入後，以原 0.4.1 runtime 成組備份 DB＋媒體並 export，archive 及所有成員 hash 已驗；私密原 env、checkpoint 與 export 保留於受限 `data/release-0.4.2/home-deployment/`。只改 `FUCHENG_IMAGE`，原 data／backup volumes 保留；沒有 init、migration、bootstrap 或管理員修改。
- Schema 仍 `0011_admin_management`，integrity ok、FK errors 0，app／backup healthy。登入前 21 表全欄／全值及原 sessions、帳密完全相同；既有帳號登入→管理 GET→登出後，16 業務表及 admins／admin_audits 共 18 表仍相同，新版成組備份成功。342 會員、2 場次、81 報名、6 保存版及 4 管理員保留，沒有真實業務寫入。
- 原 0.4.1 pinned image `sha256:d9a75ee568e651ce9dbaf7877dcdeda8acad1b57a5c75aebec481324146d7b74`、舊 snapshot／context、原 env 與所有備份均保留。同 schema 程式回退須先停寫並核對資料；如有資料疑慮，保留故障 volume，以匹配備份透過 runtime 還原至新目標。既有 `/fucheng/`、loopback 8064、HP 入口與其他服務未改，沒有清理或重試 HP SSH。

原目標對話已從公開網址完成瀏覽器驗證：會員預覽 342 人、兩頁、十個淺綠 SVG 表頭、14 pt；會內賽預覽 80 人、一頁、四個雙欄分組、16 pt、兩個圈素與原上移位置。表頭／body 共用邊均 0.75 pt，公開 CSS／JS 名稱符合本次映像；既有帳號登入、唯讀檢視與登出成功。只讀取既有名單，未編輯或保存業務資料。

工程 PDF 證據及原生列印限制見[本次驗證紀錄](print-headers-verification-20261021.md)。公開 DOM 預覽與合成實際 PDF、原生系統列印及實體驗收分開記錄。完整 build、registry typed chain、資料保留、備份及 `public-browser-verification.json` 收據在 ignored `data/release-0.4.2/`。


## 0.4.3 健檢回傳正式發布與部署（2026-10-22）

[PR #24](https://github.com/momonong/fucheng-players-system/pull/24)、`v0.4.3` tag及公開[GitHub Release](https://github.com/momonong/fucheng-players-system/releases/tag/v0.4.3)指向`ea16f6ccd3759b19ae0deaba3306ec43df385681`。先從乾淨已提交來源建置、完成映像smoke及registry拉回核對，再於台北時間19:58:47（UTC11:58:47）同批更新既有`fucheng-home` app／backup。先前健檢snapshot的歷史部署及0011→0012遷移記錄不改寫。

- Registry **manifest digest**：`sha256:5b753fc70b2db2270826dcfa07fe0fb1985c8e51774c2d4fb71c90aa42f86137`。Docker Hub `0.4.3`／`latest`相同，media type為Docker manifest v2、linux/amd64，沒有額外index。固定digest拉回後的 **config/native image ID** 為`sha256:76384cf12cb78612839fb9cec3ae4308363f5c249ac85330d05762790bb7c315`，與已測建置及現站一致。
- Source manifest：`b3893c428c3d3b53878bcec81baa0881cf8284a5c649d4ec446c261785aeeb11`。80份來源加manifest共81檔，兩份context均精確符合allowlist與逐檔hash，沒有資料、秘密、備份或舊dist。映像HTML／`index-DR8KBonb.js`／`index-Bq87i6rl.css`與本次正式四案E2E成品逐位元相同；獨立root／prefix合成映像smoke通過，無host port、network none，測試server已停、volumes保留。
- 停寫前prepare檢查器曾因Compose image-only extension引用判讀而停止，當時服務未停、env未改；精確修正檢查器並以fixture驗證後才接續。正式停app／backup後，用原`local/fucheng:snapshot-da298e6231f1f628` runtime成組備份DB＋媒體並export，archive及全部成員hash通過。checkpoint為`manual-export-20261022T115809664914Z-7a9171c6.db`，archive SHA-256為`fbf4bc3ae9d98f1dfdd875af567bc38a7827b5438106de0dff018f1cb47f3e5b`。
- 本次只更改私密env的`FUCHENG_IMAGE`，維持三份Compose overlays、原data／backup volumes、device ID及token掛載。schema原已是`0012_device_reports`，沒有migration、init、bootstrap、新增管理員或帳密變更；app／backup同一新image且healthy，integrity ok、FK errors 0。
- 登入驗證前，原 **22張表全欄全值完全相同**，包含4管理員、帳密、原sessions及1份既有device report。外部HTTPS的health、既有帳號登入／管理GET／登出、Secure／HttpOnly／`/fucheng/` Cookie、匿名管理拒絕，以及既有報告下載digest核對通過；沒有重新上傳報告。排除正常認證影響的`auth_attempts`、`login_sessions`、`public_visits`後，**19張非認證表仍相同**。保留342會員、2場次、81報名、6保存版、82安排操作、4管理員、2公告及1份公告媒體，沒有真實業務寫入。
- 新runtime成組備份`manual-20261022T115908307821Z-d439603e.db`及配對媒體archive通過，revision0012、integrity ok、FK errors 0。後端273項、正式根路徑／prefix各桌面／手機4項工程證據見[發布說明](release-0.4.3.md)；未宣稱全套舊E2E、Windows或真正Turnstile驗收通過。
- 沿用`/fucheng/`、loopback8064、HP forward／Caddy／Tunnel／DNS與其他服務，沒有入口或拓樸變更、服務目錄發布、清理或重試HP SSH。共用契約本輪重新按固定`selfhost-servers@ba471e8c47cf9299ed471b73ab8648d875b8a1be`核對；不宣稱重驗HP現用設定hash。

舊snapshot／image、原env、所有volumes、checkpoint及備份保留，沒有自動回退或清理。同schema且資料確認正常時，可停寫後審查回到前一snapshot；若有資料疑慮，保留故障庫，以匹配備份經runtime還原至新目標。舊registry0.4.2使用0011，**不能直接啟動目前0012資料**。

完整非秘密實證位於ignored `data/release-0.4.3/`的`registry.json`、`github-release.json`、`root-context-audit.json`、`image-static-verification.json`及`home-deployment/`部署／checkpoint／22表／19表／HTTPS／備份收據；env、DB、export及認證檔保持受限，不納入文件或Git。公開瀏覽器已核對342會員、十級表頭、無水平溢出與截圖，報名頁顯示目前沒有開放比賽，管理員登入表單正常；未在瀏覽器登入或提交實站報名。`public-browser-verification.json`及`public-assets-runtime-verification.json`另記公開JS／CSS名稱與byte hash相符、app／backup及既有forward健康。球館Windows、實體手機、真正Turnstile報名、實體列印、斷電／重開機與人工接受仍待驗收，同機備份不等於異地備份。
