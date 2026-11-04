# 球館 1.3.0 → 1.4.0 更新

本頁對應 v1.4.0 的固定發布。新版輪替規則與更新器見[球館備份輪替](deployment.md#球館備份輪替)。

從 [v1.4.0 Release](https://github.com/momonong/fucheng-players-system/releases/tag/v1.4.0) 下載 `update-club-v1.4.0.ps1`，將整段貼進球館 PowerShell。它自動下載固定 Git commit 的更新器、驗證 SHA256，再使用固定映像 manifest／config ID 更新；不用 Git Bash、不用傳資料夾，也不需重新輸入現有金鑰。請先儲存管理後台的編輯；更新期間網站會短暫無法使用。

下列只說明內部參數介面，含佔位字，不是可貼上的現場指令：

```powershell
& "$env:TEMP\club-vpc-upgrade-1.4.0.ps1" -TargetImage 'momonong/fucheng-players-system@sha256:<正式1.4.0 manifest 64hex>' -ExpectedImageId 'sha256:<正式1.4.0 linux/amd64 config 64hex>'
```

來源固定為 1.3.0 manifest `9b8931bd9042d932cbb0ff4f3b30fba82390d9478bac38a9444780efbe919e1e`、canonical config `63da2c4ddd162c56d2e68e7a7b88a02978081e857b1b850620af109c43564925`。原 1.2.0 pin 只用於核對歷史部署與已完成升級鏈，不啟動舊程式。

## 收據鏈與資料保護

- `%LOCALAPPDATA%\Fucheng\deploy-journal.json` 必須為原 1.2.0 COMPLETE 且 preservation 三項通過。Docker containerd 的 manifest image ID 與傳統 config ID 都只接受已固定的同一映像識別。
- `backup\upgrade-*` 必須含唯一已完成 1.2→1.3 收據；可另有唯一已完成本次 1.3→1.4 收據。每份核對部署 ID、目錄 ID、source／target pins 與 canonical IDs、三個成功 operation IDs／names／exit codes、備份摘要欄位、before／after schema／全表與媒體整體摘要／管理員數一致，以及保留的原 Compose／owner bytes。
- 新收據記錄 `previous_upgrade_id`，不改寫原 deploy journal 或原 1.3 upgrade 收據。原部署 operations、原 1.3 operations、本次 operations 都納入受管資源的 ID／name／exited 比對。
- 未知額外 upgrade、非 COMPLETE、殘留 `.next`／`.upgrade-next`、未知 writer、recipe 或身份漂移都在寫入前拒絕；不以新 UUID 迴避 UNKNOWN。
- 原 Windows 私有 ACL 規則保留：目前使用者／SYSTEM／Administrators 合法 owner，必須 caller allow 且不含其他 allow；root 必須 protected。不修改既有 ACL；僅為新備份目錄建立私有 ACL。

## 正常流程

1. 唯讀核對固定來源 stack／Compose／owner／labels／mounts／volume／networks、named pipe Linux amd64 Docker、writer，下載並驗證 target，再次核對來源。
2. 建立新獨立收據與原 recipe 副本；依具體 ID 先停 connector、backup、app，確認 exited 及無 writer。
3. 用原 1.3 runtime 建立 DB＋metadata＋媒體 tar 成組備份，驗證 hash／schema／設定。create 前記錄 intent，容器不 `--rm`。
4. 使用唯讀 volume、network none 的 job 計算全部 table／schema（包括 admins 和 login_sessions）及媒體整體摘要；只輸出整體摘要與管理員數，不輸出帳號、密碼 hash、session、資料列或媒體檔名。
5. Compose 只替換兩個精確 app ref；先啟動 target app／backup，connector 仍停止。再次計算摘要，與停寫前完全一致才啟動 connector，再核對公開 `/api/health` 及受管三容器。
6. 保存 COMPLETE，提示沿用原帳密。沒有 init、migration、匯入、還原、重建管理員、刪除原資料卷、prune、重開機、Cloudflare 設定或其他服務變更。

任何停寫後失敗均依固定名稱逐個重新核對 member，再以該具體 ID 停止並讀回 exited；app／backup 可各為精確 old／new immutable pin。單 member 的 image、labels、mounts、network、recipe 等完整守門與正常 preflight 共用，每次 stop 前也重核對原 local Docker endpoint／Linux amd64。成員不存在、identity 不符或停止不確定時保留該成員，繼續讓其他已獨立核對的 writer 停寫；整組 `stop_confirmed=false`。原本整組 project／volume／network／historical operation 守門在逐 member 停寫後仍須通過；只有三個固定成員各自通過並停妥、shared resource 一致且資料卷無其他 writer 才能記錄整組停妥。context 不明時不對該 engine 發出 stop。保留原資料、操作容器、ID／receipt、備份與故障現場，不自動 rollback。若 STOP／journal 寫入也不確定，保留 `.next`，回報固定 stage／code；勿直接重跑、首次安裝或手動還原。

既有本次 COMPLETE 重跑只讀核對 recipe／target identity／writer／health，不 pull、不備份、不重建、不重啟。

## 驗證與界線

focused suite 使用專案 `.venv` 與既有 portable PowerShell 7，核對 Docker lifecycle、實際身份守門與 SQLite 摘要；另已啟用隔離 Docker 的無 Health 欄位模板測試，共 56 項通過。沒有操作球館、沒有讀取真實資料與秘密。

```text
FUCHENG_TEST_PWSH=<既有pwsh-path> <專案python> -m pytest -q -p no:cacheprovider test_club_vpc_upgrade_v140.py --basetemp <獨立tmp目錄>
```

映像相容驗證與發布識別見[1.4.0 發布說明](release-1.4.0.md)及 Release。尚未驗證原生 Windows PowerShell 5.1／Docker Desktop 的這次更新、球館真實資料／原帳密登入及人工接受；合成資料通過不等於現場升級完成。
