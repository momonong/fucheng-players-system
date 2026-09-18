# 專案指引

## 範圍與共同約束

- 目前包含球館首頁、公告管理、公開會員分級、會員／比賽管理及「免登入選名報名」；會員帳號、自助取消、軟分級、分隊及正式部署不在範圍。
- 公開分級名單允許免登入查看姓名、級數、辨識註記與內部選取 ID；報名候選不提供級數。公開名單不得含餐食、原會員編號、帳號、會費或稽核，回應使用明確 schema。
- SQLite 每個連線維持 `foreign_keys=ON`、`busy_timeout=10000`、WAL 與 `synchronous=FULL`；會員／比賽／報名／公告修改與各自稽核紀錄必須同一交易。
- 姓名可重複；`members.id` 才是識別。未知葷素保持 `unset`。停用不等於刪除。
- 管理寫入需要後端 session 權限與 CSRF；更新必須檢查 `version`，不可靜默覆寫。
- 合成測試資料不得換成對話圖片或未授權的真實會員資料。

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
