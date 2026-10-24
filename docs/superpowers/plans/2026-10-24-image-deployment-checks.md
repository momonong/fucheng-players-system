# Image Deployment Checks Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement the confirmed tasks in this session. User explicitly requested direct implementation; no additional design approval round. Preserve the original task and report evidence to the root agent.

**Goal:** 管理員在啟動好的 app 內一鍵完成容器範圍檢查、保存與回傳，不另下載健檢工具。

**Architecture:** 延伸既有管理頁、嚴格報告 parser、接收 API 和 SQLite 交易；新增 container schema 2 與可恢復執行記錄，明確保留 Windows 主機未驗證項目。回傳使用固定 HTTPS 端點和私密檔案，失敗保留原報告。

**Tech Stack:** 現有 Python 3.14／FastAPI／SQLAlchemy／stdlib HTTP、React／TypeScript、Docker runtime；不新增套件。

**Spec:** `docs/superpowers/specs/2026-10-24-image-deployment-checks-design.md`

## Global Constraints

- 只在 `feat/image-deployment-checks`，不提交、合併、推送、發布或更動現用服務。
- 舊 schema 1／Windows 腳本／手動報告保持相容；新增 schema 2 僅表示容器範圍。
- 既有 session＋CSRF、BEGIN IMMEDIATE、version、防重 key 和 actor 綁定均維持。
- Secret file only；不得把密碼、token、hash、業務資料、任意環境值或秘密路徑寫入報告、API、前端、Git 或日誌。
- 不掛 Docker socket、主機根目錄，不給特權，不建立 SSH，不執行請求指定的 URL 或命令。
- receiver 固定 `https://momonong.me/fucheng/api/deployment-reports`；Origin 必須是 scheme＋host，禁止 redirect／TLS bypass。
- source allowlist／snapshot manifest 延用既有腳本；候選 image 只在獨立測試環境驗證。
- API 及文件須如實區分 local saved、not_configured、unknown、rejected、received；received 不等於檢查通過。
- `cloudflare_tcp_7844` 為可由目前 app 容器實測的固定官方 TCP 端點，不能列為 host-only；UDP／QUIC 與真正 Tunnel 仍 NOT_TESTED，測試不得觸及外部真實網路。

## Review Focus

- 執行結果未知後換 key，會重複檢查與寫入：前端保留原 key／payload，先 GET 讀回；404 才用原 POST 重試。
- 更新頁面或新 app instance 遺失回傳狀態：durable run table 和原 UUID／bytes 恢復。
- 舊 receiver 或設定變更導致改投其他入口：固定 endpoint／device 綁定，422／409 明確保留原報告。
- Linux 資訊被畫面或下載誤標成 Windows：schema discriminant、標題與所有 host-only check 狀態測試。
- 慢網路／連按／新管理員修改最新報告：有限 timeout、單一進行中守門、再查 version／actor、不得鎖住整個 DB 等外網。

## Task 1: Backend report execution and bounded delivery

**Files:** 新 `src/fucheng/deployment_diagnostics.py`（collector／管理路由）與必要時 `report_delivery.py`（bounded transport）；改 `deployment_report.py`、`device_reports.py`、`models.py`、`config.py`、`app.py`；新 migration `0015_deployment_diagnostics.py`；新 `tests/test_deployment_diagnostics.py` 與必要的舊 migration head assertions。

**Interfaces:** Spec 中三個管理 API；原 state 增加 `run`。執行 request 是 `{version: int, request_id: UUID, probe_network: bool}`。回傳 receipt 延用現有 report_id／device_id／digest／received_at。實作人可決定 collector 內部分工，但不可擴範圍。

- [ ] 先寫會失敗的 API／parser／收據／migration tests：權限、容器邊界、秘密遮蔽、version／actor／payload 防重、500／64 MiB bound、response lost／restart、舊 schema 1 和新 schema 2 receiver。
- [ ] 實作 readonly collector，探測固定端點且有限等待；不讀會員內容；主機專有項目 NOT_TESTED。
- [ ] 實作單交易保存與獨立回傳狀態；HTTP 前保存 unknown，成功驗 receipt 才 received；明確保留原 key 和原 report。
- [ ] 定向測試後跑完整 backend suite；舊表／帳號資料不得被 migration 改寫。

## Task 2: Existing admin page one-click flow

**Files:** `frontend/src/DeploymentReport.tsx`、相關 `styles.css`，`frontend/e2e/deployment-report.spec.ts` 及一個新的聚焦 diagnostics e2e 檔。

- [ ] 先寫失敗 E2E：登入後不需上傳檔就能按「立即檢查並回傳」，看到容器來源、未驗證項目、保存和回傳狀態。
- [ ] 延用現有頁面配色與元件，主要入口改一鍵檢查；舊手動上傳放可展開區塊，不另造 dashboard。
- [ ] 一次生成 request UUID；unknown 保留 payload，只 GET 原 run；404 才允許同 payload 重試。已 receipt 但 GET 失敗只重讀。已保存 run 的回傳為 unknown 時，「重送原報告」入口只送原 run，不換 UUID；讀回確認原 run 後，使用者仍可明確另建一份獨立診斷，不能自動重跑或把新診斷當重送。重新整理後從 current state 恢復 run；不把重跑當重送。
- [ ] `npm run typecheck`、獨立 `frontend/dist-diagnostics-e2e` build；E2E 使用 `data/diagnostics-e2e.db`、8056；prefix 驗證改獨立 8057／DB。桌面與手機無水平溢出。

## Task 3: Image/deployment integration and evidence

**Files:** 新 `deploy/docker/compose.diagnostics.yaml`、改 `club.env.example`、`scripts/deployment_package.py`（kit allowlist）、`docs/host-report-upload.md`、`docs/deployment.md`、必要 README 說明。

- [ ] 提供 server-only send secret overlay、可選 app egress 與明確首次設定；不混淆 upload receiver 和 send credentials，image 不含 secrets。
- [ ] 文件改成 image 啟動後在管理頁執行檢查；標明 Windows 原生腳本為額外深度檢查，非本次前置必要。記下 0015 明確遷移和匹配備份回復。
- [ ] Root 使用 `scripts/deployment_package.py build` 產 fresh snapshot，核對 allowlist／manifest，不直接把資料 repo 當 context。
- [ ] Root 在獨立 Docker project／port／volume 合成資料驗一次 run、同 key retry、下載、備份與 root／prefix。不得動 `fucheng-home` 或球館未建立的資料。
- [ ] 原對話核對 fresh review，交付可用候選映像和驗證證據；版本發布與現用站部署按明確授權分別執行，不用原 v1.1.0 名稱冒充新功能。
