# 專案指引

## Docker部署共同規則

- 單一app image包含React成品＋FastAPI，SQLite用Linux named volume；維護／備份復用image。正式Tunnel直連app，nginx只供https-test，見docs/deployment.md。
- 透過scripts/deployment_package.py的allowlist staging與source manifest建置；禁止data／帳密／備份／既有dist入context、image或離線包。未提交版標snapshot與hash。
- volume寫入經runtime.py生命周期鎖與maintenance守門；start不migration。遷移先停寫、備份，回退匹配image/schema並還原新目標、保留故障庫。不繞過guard直接寫volume。
- 部署驗證僅獨立project/port/volume合成資料；真實資料來源與操作另授權。公開Tunnel須另行明確授權，不動既有服務，禁止prune／down -v。

## 範圍與共同約束

- 目前包含球館首頁、公告管理、公開會員分級、會員／比賽管理、「免登入選名報名」及當次比賽級數安排；會員帳號、自助取消、分隊及正式部署不在範圍。
- 公開分級名單允許免登入查看姓名、級數、辨識註記與內部選取 ID；報名候選不提供級數。公開名單不得含餐食、原會員編號、帳號、會費或稽核，回應使用明確 schema。
- SQLite 每個連線維持 `foreign_keys=ON`、`busy_timeout=10000`、WAL 與 `synchronous=FULL`；會員／比賽／報名／公告修改與各自稽核紀錄必須同一交易。
- 姓名可重複；`members.id` 才是識別。未知葷素保持 `unset`。停用不等於刪除。
- 管理寫入需要後端 session 權限與 CSRF；更新必須檢查 `version`，不可靜默覆寫。
- 合成測試資料不得換成對話圖片或未授權的真實會員資料。
- 會員 level、不可回寫的 hard_level_snapshot 與報名列 competition_level 各自獨立。僅 open／closed 場次正取可有原因調級；取消保留歷史，重報以新快照初始化，候補遞補保留原列當次級數。不可用當次級數替換既有快照統計語意。

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

當既有預覽使用 dist-public／dist-delete 時，不可執行上列建置覆寫它們。當次級數驗證改用 dist-levels，並設定 FUCHENG_E2E_DATABASE_URL=sqlite:///data/levels-e2e.db、FUCHENG_E2E_PORT=8036、FUCHENG_E2E_STATIC_DIR=frontend/dist-levels。人工合成預覽為 8035／levels-preview.db，與 E2E 及其他預覽獨立。
