# 球館 1.2.0 → 1.3.0 更新器

更新器為程式碼更新專用；維護腳本位於 `deploy/docker/club-vpc-upgrade.ps1`。
`club-vpc-upgrade.ps1` 自包含，使用 Windows PowerShell 5.1，沿用現有 `%LOCALAPPDATA%\Fucheng` 私有配置，不讀取或索取帳密、token、Turnstile secret 或 `protected.env` 內容。

## 發布者整合

發布者需提供實際發布映像的兩個不可變值，不可用 tag 或猜測 digest：

```powershell
& "$env:TEMP\club-vpc-upgrade.ps1" -TargetImage 'momonong/fucheng-players-system@sha256:<實際 manifest digest 的 64 hex>' -ExpectedImageId 'sha256:<實際 linux/amd64 image config ID 的 64 hex>'
```

上面是介面說明，不是可直接執行的 final launcher；placeholder 不會通過 guard。發布者應以固定 Git commit 下載已核對 SHA256 的腳本，將正式 manifest digest／image ID 填入最後交付使用者的 launcher。不要用舊首次安裝碼、`latest` 或 `:1.3.0` 取代 pin。

## 更新的具體行為

1. 核對 Windows console、ACL、連結路徑、既有排他鎖、原部署 COMPLETE journal、原 Compose 全文及 owner marker；核對本機 named pipe Linux amd64 Docker context、三個容器的 image／labels／mounts／network／command、資料卷和未知 writer。
2. 先下載並比對新映像 config ID，再次核對舊 stack／writer；成功前不停止原站。
3. 在既有私有 `backup\upgrade-<UUID>` 保存原 Compose／owner 及獨立 `upgrade-journal.json`。先停 connector，再停 backup、app，以具體 ID 讀回 exited，確認資料卷無 writer。
4. 使用原 1.2.0 image 的 runtime `backup` 建立 DB／JSON metadata／媒體 tar 同組備份，核對檔名、SHA256、schema、integrity、FK 與備份設定。每個 operation 在 create 前保存 intent，保留容器、ID、exit code 與原收據，沒有 `--rm` 或未知重送。
5. 以 network none、read-only root、唯讀資料卷的 Python job 計算全部資料表／schema（包含 admins、login_sessions）的整體 digest、管理員人數、integrity／FK 及媒體整體 digest；不輸出資料列、帳號或個別密碼 hash。
6. 只替換 Compose 中兩個精確舊 app pin，其餘 recipe 不動，更新 owner marker。以原 Compose 啟動 app／backup；connector 保持停止。再次執行唯讀摘要，前後相同才啟動 connector，核對三容器與公開 bounded TLS `/api/health` 回應。最後保存 COMPLETE，提示原帳密仍適用。

原 `deploy-journal.json` 是歷史，永不回寫。舊 preview、兩個資料卷、既有備份與全部操作容器保留；沒有 migration、init、建立管理員、匯入、還原、刪容器／卷、prune、reboot、Windows／防火牆／Cloudflare 配置或其他家用服務變更。

## 失敗、UNKNOWN 與重跑

- 若下載／preflight 失敗，原 stack 不停止。只輸出固定 stage／code，原始 Docker stderr 不顯示。
- 開始停止後若失敗，重新核對本部署固定三容器；app／backup 可各自是已驗證的舊或新 pin，以處理 Compose 部分重建。只停止通過身份守門的 stack，讀回 exited。若身份或停止無法確認，明示保留現場；絕不啟動舊站。
- **網站可能保持停止。** 請回傳 stage／code，由維護者先核對既有 journal、原操作名稱／ID／receipt。不要直接重跑、換 UUID、重新安裝或手動還原。
- 任何非 COMPLETE upgrade journal、殘留 `.next`、多個 upgrade 目錄或身份不符皆拒絕接續，不會再次 backup/create/start。此工具不提供自動 recovery 或 rollback。
- 同一 COMPLETE 升級重跑只驗證目前 Compose／marker、實際 target image、容器身份、writer 與公開 health，不 pull、backup、重建或重啟。
- 本工具只支援目前已核對 1.2.0 的這次升級；後續版本需另外設計，不能刪除升級收據繞過 guard。

## 已驗證及限制

`test_updater.py` 在 Linux portable PowerShell 7 上測試腳本的 mock lifecycle；另直接測試實際身份守門及真實合成 SQLite 全表摘要。測試不連 Docker daemon、不讀任何球館資料、不建立真實會員／報名。

執行方式：

```text
FUCHENG_TEST_PWSH=<pwsh-path> uv run --locked pytest -q -p no:cacheprovider tests/test_club_vpc_upgrade.py
```

測試涵蓋 ACL／remote context／recipe／image／volume／writer／mount／ports／labels／IP 漂移、partial journal、backup create UNKNOWN、hash 不符、stop timeout／仍 running、部分 Compose old/new stack 清理、before/after 變更、公開 health 失敗、COMPLETE read-only 重跑與正常更新順序。

**未驗證：原生 Windows PowerShell 5.1 實際執行、Docker Desktop bind mount 實機形式、球館真實資料及實際 1.3.0 發布 pin。** portable parser／mock／SQLite 合成證據不等於球館部署或人工驗收。若 Docker Desktop mount source 形式不在 guard 允許範圍，會在停止之前拒絕，不自行放寬。

## Docker Desktop 映像識別相容性修正

球館實測 `docker inspect .Image` 及原部署 journal 的 `image_id` 回報1.2.0固定manifest digest，而傳統Docker回報config ID。更新器現僅接受同一固定映像的這兩個精確識別；本機image、目前容器及原journal均核對，仍要求精確image Ref、labels、mounts、network與writer守門。新升級journal繼續保存canonical config ID，原部署紀錄不修改。

舊更新器的 `preflight/JOURNAL_INVALID` 未進入停寫或變更資料。使用修正後固定來源與新SHA launcher即可；不要改journal、重建管理員或重跑首次部署。網站Docker映像仍為已發布的1.3.0，此修正只更新維護腳本。

## 未配置 healthcheck 的 Tunnel 容器

Docker的State可能完全沒有Health欄位；Tunnel未配置healthcheck是正常狀態。更新器用安全的map索引讀取可選Health，對Tunnel仍核對running及固定身份，對app／backup仍強制要求healthy。已以真實Docker的無Health合成容器重現舊模板失敗，並驗證修正後PowerShell程序傳參與JSON讀回。

Docker命令失敗會顯示命令種類、exit code與timeout；僅唯讀metadata命令顯示最多1500字元stderr。寫入／Compose／log內容及完整命令參數不回顯。
