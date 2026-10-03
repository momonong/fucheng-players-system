# 家中 4090 試用部署

2026-10-03 狀態：0.3.2 原始碼與 image 已發布；4090 的 app/backup 已在 loopback 啟動，指定資料已還原，`https://momonong.me/fucheng/` 已切換並完成公開瀏覽器讀取驗證。管理員登入後人工操作、真實 Turnstile 報名及斷電恢復仍待驗收。

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

球館 Windows Docker Desktop／WSL2 仍可使用同一 Linux/amd64 0.3.2 image、runtime 及成組備份。改採該場域的入口配置，不沿用 HP SSH overlay；根路徑時 `FUCHENG_BASE_PATH` 留空，`FUCHENG_PUBLIC_ORIGIN` 改為當地 HTTPS origin，前綴不寫入會員資料。不因改前綴重建 image。實機登入、資料還原、照片、斷電／重啟及 Windows 登入後 Docker 恢復仍需驗收。

## 公開切換驗證（2026-10-03）

使用者在終端完成兩台主機的互動 sudo。獨立核對 4090 的 `fucheng-hp-tunnel@ubuntu.service` active/enabled、NRestarts=0；app/backup healthy，app 僅發布 127.0.0.1:8064。HP forward 僅 127.0.0.1:18084；Caddy、cloudflared、既有 OrderFlow forward 皆 active。現用 Caddy SHA-256 為 `0e9b6473c465309ea5fad4dde547b9f286d3a363acd69142a3bd3157505da209`，與已審查候選一致；root-only 舊設定備份在 HP `/var/backups/fucheng-ingress/cutover-IQhjPaJx`。

公開瀏覽器可完整載入首頁公告、342 位會員的分級頁、比賽頁與管理員登入表單；共用根首頁及 OrderFlow 登入頁正常。舊場次已截止，公開報名頁正確顯示沒有開放場次；未為驗證向真實試用資料新增合成比賽或報名。

Python urllib 的外部探測被 Cloudflare 拒絕（403 / 1010）；瀏覽器正常進站。IAB 直接導覽 API 路徑另被 client 阻擋，因此未把它記成公開 API 成功，也未調整 Cloudflare 或繞過保護。先前透過可信本機入口的管理員登入／讀取／登出已通過；本輪公開瀏覽器登入後流程、真正的 Turnstile 挑戰及成功報名尚待使用者驗收。沒有斷電／重開機或另一條行動網路的驗證。

現用 image 保持 0.3.2 與原 digest；本輪僅同步部署設定及證據，未重建 image。帳密、來源資料、備份和完整受限紀錄保存在 ignored `data/home-deployment/`，不進版本庫。
