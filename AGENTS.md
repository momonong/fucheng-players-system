# 專案指引

## 範圍與共同約束

- 目前已包含會員管理，以及第二階段的「比賽建立＋管理員維護報名名單」；會員自助報名、軟分級、分隊與發布版本仍不在範圍。
- 公開 API 必須使用明確回應 schema，不得洩漏會員編號、稽核、帳號或會費欄位。
- SQLite 每個連線維持 `foreign_keys=ON`、`busy_timeout=10000`、WAL 與 `synchronous=FULL`；會員／比賽／報名修改與各自稽核紀錄必須同一交易。
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
cd frontend && npm run build
cd frontend && npm run test:e2e
```

Python 使用 uv、`pyproject.toml`、`uv.lock` 與專案 `.venv`；前端使用 npm 與 `package-lock.json`。正式服務不在啟動時安裝依賴，也不常駐 Node.js。文件入口見 `README.md`。
