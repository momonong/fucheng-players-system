# 家中 4090 試用部署

2026-10-03 狀態：0.3.2 原始碼與 image 已發布；本文件與 Compose 是部署準備，`momonong.me/fucheng/` 尚未切換。不可把合成驗證或資料副本升級視為公開服務完成。

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

`fucheng-hp-tunnel@.service` 是 systemd 範本，以實際本機使用者執行，例如 `fucheng-hp-tunnel@ubuntu.service`。安裝前確認該使用者的 `hp-server` alias 與 known_hosts 能非互動登入，目的地符合 selfhost-servers；不複製私鑰。需使用者終端的 sudo 認證才能安裝／enable，不能把測試 SSH 當正式服務。先驗 app，再驗持續 forward，最後依基礎設施契約備份、validate、reload Caddy。

## 本輪證據與剩餘條件

- 0.3.2 image ID `585befc2f28a075467ce15ce32ab5d41f20134b34523cb6ae759e93da097ffe5`，digest 固定於 env 範例。
- 隔離 project `fucheng-home-ingress-check-20261003`、8065、10.203.33.0/24、合成空資料：app/backup healthy；子路徑 health/HTML 200、匿名管理 401、根路徑 API 404、錯誤 Host／缺少轉送識別 400。測試金鑰是無效占位值，僅供 loopback 配置驗證，未呼叫 Siteverify、不代表 Turnstile 通過。
- SSH systemd 範本通過 `systemd-analyze verify`；HP 實際 Caddy 版本 validate 候選通過。臨時 HP loopback 18086 → SSH → 4090 8065 → Docker health 通過，測試 forward 與 app/backup 已停止、合成 volumes 保留。尚未安裝 systemd 或套用 Caddy。
- 使用者已接受收到的舊資料快照作為試用基準，不要求補取 Windows WAL。原始檔另行保留；獨立副本 0005 → 0010 升級後，14 張原表的所有既有欄位逐列一致，integrity ok、FK error 0。未補造安排歷史，也尚未把副本公開。
- 待完成：有效 Turnstile、試用目標資料與管理員存取設定、正式 named volume 還原／備份、持續 SSH、Caddy 切換、完整 HTTPS/登入/報名/媒體驗收與異地備份安排。受限證據在 ignored `data/`，不提交 DB 或認證內容。

備份 volume 與 app 同機，不能算異地備份。更新前手動備份與成組 export；回退在新 volume 還原匹配 image/schema，保留故障資料。不得 prune 或 down -v。

## 日後搬到球館

球館 Windows Docker Desktop／WSL2 仍可使用同一 Linux/amd64 0.3.2 image、runtime 及成組備份。改採該場域的入口配置，不沿用 HP SSH overlay；根路徑時 `FUCHENG_BASE_PATH` 留空，`FUCHENG_PUBLIC_ORIGIN` 改為當地 HTTPS origin，前綴不寫入會員資料。不因改前綴重建 image。實機登入、資料還原、照片、斷電／重啟及 Windows 登入後 Docker 恢復仍需驗收。
