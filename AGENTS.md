# 專案指引

## Docker部署共同規則

- 單一app image包含React成品＋FastAPI，SQLite用Linux named volume；維護／備份復用image。正式Tunnel直連app，nginx只供https-test，見docs/deployment.md。
- 透過scripts/deployment_package.py的allowlist staging與source manifest建置；禁止data／帳密／備份／既有dist入context、image或離線包。未提交版標snapshot與hash。
- volume寫入經runtime.py生命周期鎖與maintenance守門；start不migration。遷移先停寫、備份，回退匹配image/schema並還原新目標、保留故障庫。不繞過guard直接寫volume。
- 部署驗證僅獨立project/port/volume合成資料；真實資料來源與操作另授權。公開Tunnel須另行明確授權，不動既有服務，禁止prune／down -v。

## 範圍與共同約束

- 目前包含球館首頁、公告管理、公開會員分級、會員／比賽管理、「免登入選名報名」、當次比賽級數表格及完整安排保存／唯讀歷史；會員帳號、自助取消、分隊、自訂表頭與當次安排列印及正式部署不在範圍。
- 公開分級名單允許免登入查看姓名、級數、辨識註記與內部選取 ID；報名候選不提供級數。公開名單不得含餐食、原會員編號、帳號、會費或稽核，回應使用明確 schema。
- SQLite 每個連線維持 `foreign_keys=ON`、`busy_timeout=10000`、WAL 與 `synchronous=FULL`；會員／比賽／報名／公告修改與各自稽核紀錄必須同一交易。
- 姓名可重複；`members.id` 才是識別。未知葷素保持 `unset`。停用不等於刪除。
- 管理寫入需要後端 session 權限與 CSRF；更新必須檢查 `version`，不可靜默覆寫。
- 合成測試資料不得換成對話圖片或未授權的真實會員資料。
- 會員 level、不可回寫的 hard_level_snapshot 與報名列 competition_level 各自獨立。僅 open／closed 場次正取可調級，調級原因可省略且稽核留空，不假造原因；其他操作原因規則不變。取消保留歷史，重報以新快照初始化，候補遞補保留原列當次級數；不可用當次級數替換既有快照統計語意。
- 起始安排基準以 auth／CSRF POST 或首次合法調級前同交易建立一次，GET／migration 不補造歷史。完整安排快照不可變，保存須在 BEGIN IMMEDIATE 核對完整名單 token 與最新基準，固定 request_id 綁定 actor／payload，快照及稽核同交易。顯示編輯者與實際 admin 分開；淨差按報名 ID 比較上一保存版，不用 hard_level_snapshot 充當基準。

## 已驗證指令

```text
uv sync --locked
uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp
cd frontend && npm ci
cd frontend && npm audit --audit-level=high
cd frontend && npm run typecheck
cd frontend && npm run build -- --outDir ../frontend/dist-public
cd frontend && npm run test:e2e
```

Python 使用 uv、`pyproject.toml`、`uv.lock` 與專案 `.venv`；前端使用 npm 與 `package-lock.json`。正式服務不在啟動時安裝依賴，也不常駐 Node.js。文件入口見 `README.md`。

免登入新增報名使用自動訪客上下文與 CSRF，共用 `registrations.py` 的寫鎖交易及 actor／payload 綁定 idempotency。選名不證明本人，稽核用 public visit，不假冒 member actor；取消、更正、遞補只限管理員。E2E 用 `data/public-e2e.db`、8031、`frontend/dist-public`，不可覆寫原服務成品或資料。

不可覆寫既有 dist-public／dist-delete／dist-levels／dist-level-drag 或舊預覽 DB。本輪安排保存驗證使用 dist-arrangement、FUCHENG_E2E_DATABASE_URL=sqlite:///data/arrangement-e2e.db、FUCHENG_E2E_PORT=8040、FUCHENG_E2E_STATIC_DIR=frontend/dist-arrangement；人工合成預覽為 8039／arrangement-preview.db，與測試及原8037預覽隔離。重建／重啟使用中的成品前確認該服務用途；舊 Docker／ngrok 升級另依授權及維運契約。
