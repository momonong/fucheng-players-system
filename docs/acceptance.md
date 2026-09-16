# 驗收證據與限制

最後更新：2026-09-16。自動測試與功能驗收資料均為合成資料；經使用者明確授權的本機初始會員資料只保存在 Git 忽略的資料庫與匯入來源中。

## 已驗證

- 基準：Windows x86-64 開發機、一般 CPython 3.14.6、uv 0.12.15、Node.js 24.11.0、npm 11.6.1。
- `uv sync --locked` 可建立專案 `.venv`；FastAPI 0.141.1、SQLAlchemy 2.0.53、Alembic 1.20.0、Pydantic 2.13.5 可安裝與匯入。
- 後端自動測試涵蓋：空資料庫 Alembic 遷移、SQLite pragma／級數／會費期間約束、未登入禁止管理、登入／登出失效、CSRF、公開敏感欄位排除、重名、改名、停用／恢復、修改歷史、交易失敗、過期版本衝突、備份還原。
- 前端 `npm audit --audit-level=high`、TypeScript 檢查與 Vite 正式建置通過。
- Playwright 以桌面 1440×900 及手機 390×844 執行：登入、新增、修改、公開名單、搜尋、級數篩選、列印模式、手機無水平溢位。
- 備份以 SQLite Backup API 建立，還原至另一個乾淨資料庫並核對內容與 `integrity_check=ok`。

## Python 3.15 調查

2026-09-16 時 Python 3.15 正式版尚未發布，官方時程為 2026-10-01；當下是 rc2。實測 `uv 0.12.15` 的下載清單雖顯示 rc2，但指定 `3.15.0rc2` 回報 `No download found`，指定或重裝 `3.15` 反而安裝 3.15.0b2，且首次解算帶入 Pydantic 2.14.0b2。這個預發布組合不作為第一版正式基準，因此採目前可安裝的穩定 CPython 3.14.6 與 Pydantic 2.13.5。

Python 3.15 正式版發布後，應更新 `.python-version` 與 `requires-python`，刪除並依 lockfile 重建獨立 `.venv`，重新執行匯入、Alembic、API、資料庫、完整測試與負載測試；未完成前不可宣稱 3.15 已支援。

## 尚未驗證與現場驗收

- 尚未在 Linux systemd 實機執行；本次 Windows 主機沒有可用的 Linux 執行環境（WSL 發行版列舉亦遭主機拒絕）。目前只有 service／timer 範本、強化設定與操作文件。部署主機需執行 `systemd-analyze verify`、啟停、重啟後健康檢查與權限測試。
- 尚未建立 Cloudflare Tunnel、網域、外部帳號或公開部署。
- 尚未在 2 GB 雙核心舊筆電、20 GB 實際磁碟或球館 Wi-Fi 驗收。開發機負載結果只能證明此程式與測試條件，不能外推到目標硬體。
- 尚未由真實管理員與長輩使用者進行現場可用性驗收。本機已有經使用者授權匯入的真實初始名單，但自動測試、負載測試與列印驗證仍只使用合成資料；授權匯入不等於現場可用性驗收。
- 正式上線前要以去識別或經授權的資料演練遷移、備份、還原、帳號復原、HTTPS cookie 與失敗回復。

## 最近一次結果

- 後端：鎖定環境重建後為 `15 passed`；另有 FastAPI／Starlette 測試客戶端的上游 deprecation warning 2 則，沒有測試失敗。測試涵蓋一次性 CSV 匯入、重名、交易內稽核、防止重複匯入、未設定葷素的具名管理員回填，以及備份／還原危險路徑拒絕。
- 前端：`npm ci`、型別檢查與 Vite 7.3.6 production build 通過；成品 JavaScript gzip 63.31 kB、CSS gzip 2.66 kB；npm audit 為 0 個已知漏洞。
- 瀏覽器：Playwright desktop + mobile `2 passed`；包含衝突提示、輸入保留、多級對照、390×844 手機無水平溢位及長姓名不裁切。列印另以 327 筆合成資料（各級筆數同目前名單）驗證 11 欄、42 列，產出的 PDF 為單頁 A4 橫式，Poppler 重新渲染確認標題、表頭、內容與頁面邊界無裁切。
- 備份還原：除自動測試外，另以 E2E 合成資料庫執行 CLI 一致性備份並還原到新的乾淨目的地；來源與還原檔皆為 `integrity_check=ok`，會員筆數相同。
- 混合負載：單一 Uvicorn worker，100 使用者在 10 秒內逐步到站、每次瀏覽停頓 0.8～2.5 秒、每 5 秒一筆管理寫入；62.3 秒共 3,421 requests，0 errors（0.0000%），p50 4.1 ms、p95 7.9 ms、p99 15.6 ms、max 33.3 ms；服務程序 RSS 89.6 MiB、CPU 5.75 秒。
- 上述負載在 Windows x86-64 開發機與合成小型資料集完成；不是 Linux systemd、2 GB 目標硬體或球館網路的驗收數字。
