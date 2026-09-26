# 驗收證據與限制

最後更新：2026-09-26。自動測試與功能驗收資料均為合成資料；經使用者明確授權的本機初始會員與 9/20 圖片案例只保存在 Git 忽略的資料庫、轉錄與對照報告中。

## 0.3.1 部署檢查報告候選（2026-09-26；尚未公開交付）

來源分支 `feat/mobile-security-release`、功能提交 `38552f8c86c70369c43f906ed35fabb9833fc7c5`；此段證據尚未代表 `main` 合併、遠端 push、tag、Docker Hub 發布或 8052 預覽切換。管理員專用 JSON 上傳以 schema v1／256 KiB 限制、CSRF／版本 CAS、同交易稽核保存最新報告至 SQLite；下載 Markdown 由伺服器按純文字重新產生。管理介面提供系統狀態導航、主機身份／時間風險提示、檢查與建議、複製和下載。報告內容是上傳者宣稱，沒有主機身份證明。Windows PowerShell 5.1 讀取上一輪健檢報告成功，Git Bash 尚待球館主機實跑。

本機後端全套 `193 passed`（2 個既有 Starlette/httpx 警告）；先前全套首輪因 5 個測試仍斷言舊 migration `0009` 而有 `188 passed, 5 failed`，更新預期後相關 25 項與全套皆通過。前端 `typecheck`、0.3.1 `npm audit --audit-level=high`（0 vulnerabilities）、隔離 8046／`data/deployment-report-e2e.db` 的桌面與手機上傳、複製、下載 E2E `2 passed`。首次受限環境 Chromium spawn EPERM，提權後桌面通過；同 DB 的手機案例原先錯誤預期沒有報告，修正測試後 2 項通過。建置輸出 `dist-deployment-report` 不入來源。`uv lock --check --offline` 通過；本機 uv sync 因 sandbox 擋 PyPI 取 hatchling 未完成，實際 Linux 映像建置已以 locked lockfile 成功完成。

`scripts/deployment_package.py build` 以提交來源產生 69 檔 allowlist context 並精確核對 context-audit，`source_manifest_sha256=11999679a1ded1fe541edb47ac00ebbbb25e321c6c992ad4908c0eaf0dd1b0e2`，本機 Linux/amd64 映像 `local/fucheng:snapshot-11999679a1ded1fe`，image ID `sha256:b6eb19a90fce1d28d53487d6de8428894ea8505eae939f8a840248194ba89438`。合成 `fucheng-report-drill-20260926`／`fucheng-report-restore-20260926` 使用獨立 project、volume、8054／8055 與網段，驗 0010 初始化、管理上傳、報告與公告照片、app 重啟後讀回、手動成組 DB／媒體備份的 hash、完整性及新目標 restore 後報告／照片可讀、匿名報告 API 401。停止兩組合成服務後 source/restore `ops inspect` 均為 `revision=0010_deployment_report`、integrity `ok`、FK 錯誤 0；保留測試 volume/備份供追溯，8054／8055 已釋放。忽略路徑 `data/deployment-report-drill-20260926/evidence.json` 保存不含帳密的摘要。合成 drill 首輪腳本因 httpx client 重入與週備份額外生成檔案的錯誤假設中斷；修正腳本並沿用同一合成資料後完成上述驗證。

現用 8052 Docker 0.3.0 app／backup／host-ngrok 仍 healthy，8044 listener 與六個 NeuroAI 容器未碰。Windows Pro 球館實機、外部手機、正式資料、冷開機及新版 8052 預覽仍未驗收；正式升級要按[部署手冊](deployment.md)先停寫、備份、明確 migration 與新目標回退演練。

2026-09-25 最新安全階段結果：[公開安全、Turnstile 與週備份工作樹](#security-stage)；最終後端全套 190 passed，先前失敗紀錄仍保留於下方。

## 8052 手機介面合成預覽（2026-09-25；待人工驗收）

獨立 8052 [手機驗收入口](https://29e0-140-116-158-107.ngrok-free.app/) 已換成凍結的 `data/admin-news-preview-releases/mobile-v5-20260925/source/src` 與 `static`；目前身份見忽略的 `data/admin-news-preview-identity.json`。只停止並更新 8052 app，原 ngrok PID 19552 與 8044 listener 45460 保留；新版 listener 48248、launcher 51336。停寫後以 SQLite Backup API 建立 `rollback/pre-upgrade.db`，19 張表及 5 個媒體檔與原庫逐項 hash 一致，schema 仍為 0009、integrity `ok`、FK 錯誤 0。新版啟動前後同一批表及媒體 hash 完全相同，既有 admin/session/公告與圖片未被重建或清除。

公開 ngrok HTTPS `/api/health` 為 200，首頁 HTML、JS、CSS 三檔與凍結成品 SHA-256 相同，兩張已發布公告圖片 HTTPS 200。本機可信代理路徑驗證既有管理員帳密登入與 `/api/auth/me` 均 200、Secure cookie；外部 HTTPS 管理登入自動檢查因工具自動審核拒絕將本機保存的帳密傳到 ngrok 而未執行，須由使用者在手機親自驗收。預覽的 Turnstile 明確 `disabled`，沒有真實 Cloudflare sitekey/secret；Windows 原生預覽沒有 Docker 的每週備份排程，正式 Cloudflare 模式仍拒絕缺密鑰啟動。

手機改善包含精簡報名頁抬頭、管理比賽清單與設定折疊、報名名單捷徑、公告工具列橫向滑動與觸控圖片操作。獨立合成 Chromium 寬度 360／390／430／768px 的首頁、報名、比賽管理、公告頁均無整頁水平溢位；360px 報名名單頂端約 784px（舊版約 1886px），公告工具列約 83px（舊版約 384px）。圖片上傳後觸控選取／完成、HTTPS 公開圖片載入已核對。`npm run typecheck`、獨立 build、手機流程 E2E 1 passed、公告／免登入報名／比賽管理既有 E2E 6 passed、後端全套 190 passed。追加 80 人格位手機回歸首輪在合成資料建立階段遭管理員寫入 burst 80 額度拒絕 429；將已登入管理員 burst 調至 200、公開額度不變後，該案例 1 passed，安全／報名後端定向 27 passed。此修正尚未包含於上段 v5 預覽凍結來源，需下一次受控換版。寬度 E2E 採固定窄版 viewport 加觸控事件；實體手機與人工操作仍待驗收。先前 `isMobile` 模擬的儲存鍵點擊因 Chromium 測試布局 viewport 高於視覺 viewport 而逾時，保留在忽略的診斷輸出，未當作產品失敗或成功證據。

## 公告工具列分類與文末照片入口最終修正（2026-09-24；8052 本機合成預覽 v4）

v3 將公告工具列五組加上可見的「樣式／文字／段落／插入／區塊」標籤。相同靜態成品在獨立 8053 合成環境的公告定向 Playwright 為 **5 passed、1 skipped**；手機實際通過插圖、圖片上／下移、H2、儲存重載與公開讀回。唯一 skip 是只在 desktop project 擷取 390／768／1440／3840px 頁面矩陣的案例，不是手機核心操作。

最終 v4 移除新公告下方常駐的舊式原生照片選檔列；新增公告先儲存草稿，才可從工具列插入內文圖片，不新增自動儲存。原本有 `photo_id` 的公告才顯示「既有文末照片」折疊區，可查看、替換、移除，並保留原照片直到儲存成功。`npm run typecheck`、`npm run build -- --outDir ../data/admin-news-preview-static-v4` 通過；隔離 8053 合成環境的 `announcement-editor.spec.ts` 與 `website.spec.ts` 桌面／手機定向 **9 passed、1 skipped**，含新公告工具列插圖、舊文末照片替換／移除、格式與發布下架。唯一 skip 仍為上述桌面專用四寬度截圖；本次未重跑無關的 178 項後端全套。

核對 8052 身份與既有備份後只切換 static 至 `data/admin-news-preview-static-v4`，前版 v3／v2 成品與 `backups/admin-news-preview-v2-pre/` 保留。實際 8052 首頁 HTTP 200、health=ok、v4 bundle 已載入；切換前後 17 張業務表及 5 個媒體檔逐項摘要一致，integrity=ok、FK0，未更動既有公告、admin 或媒體，未清理既有 session。實際新公告／舊文末圖 390／1440px 截圖與合成段落圖、超寬截圖在 ignored `data/admin-news-evidence/legacy-entry-v4/`；身份見 `data/admin-news-preview-identity.json`。8052 仍僅本機合成預覽，正式資料、Docker 與公開入口未操作；未 stage／commit／merge／push。

## 公告內文多圖、管理導覽與流式版面（2026-09-24；8052 本機合成預覽）

沿用 `aaa3` 工作樹與 schema `0009_announcement_media`，未新增 migration。公告內文可使用標題 1–3、粗斜體／底線、清單、對齊、安全連結與多張本站圖片；圖片依段落次序保存，區塊上／下移、圖片替換／移除與舊文末照片並存。內文圖上傳要求既存公告及 version／CSRF／request_id，資料與稽核同交易；公開媒體只對已發布且仍被引用的圖片開放。管理三頁共用固定導覽，十級表最後一列下框線限定修於行政表，頁面在 390／768／1440／3840px 採流式寬度而內文保持閱讀行寬。

- Windows/CPython 3.14.6：全套 `uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp` **178 passed、2 第三方 deprecation warnings**。`npm run build -- --outDir ../frontend/dist-admin-news-v2` 包含 TypeScript typecheck 並通過；未更動依賴，沿用先前 npm audit 結果。
- 獨立 `8053`、`data/admin-news-v2-e2e.db`、`frontend/dist-admin-news-v2` 的 Playwright 定向桌面／手機 **7 passed、1 skipped**（四寬度截圖僅桌面專案）。涵蓋多圖插入、排序、替換、移除、連結、保存後公開讀回、舊文末照片、409 輸入保留、行政格線與四寬度無整頁橫向溢位。截圖與列印 PDF 保存在 ignored `data/admin-news-evidence/v2-final/`，已目視檢查 390／768／3840px。
- 8052 更新前核對 listener／launcher 身份，線上與停寫備份至 `backups/admin-news-preview-v2-pre/`，停寫備份 integrity=ok、FK 無錯、5 筆媒體與 5 個檔案逐檔 SHA-256 相同。更新後 `data/admin-news-preview-identity.json` 指向 v2 static；health 與首頁 HTTP 200、管理員登入及公告清單 200、兩張公開引用媒體均 200，DB integrity=ok。實際首頁／公告編輯器 390／1440px 截圖同存證據目錄。8052 仍僅本機合成預覽，正式資料、Docker、公開入口及 8044／8045／8047 未操作；未 stage／commit／merge／push。

## 行政名單與公告圖文工作樹驗證（2026-09-24；未部署）

工作樹 `aaa3` 自 `ef147253ca1604fc8c4c74175b3f9f7fe08894a6` 起；行政名單使用固定十級、`hard_level_snapshot` 分欄，搜尋保留占用格位，候補／已取消以原順位分區及側欄展收；全場摘要與管理列印不受搜尋改寫。公告 schema 新增 `0009_announcement_media`，舊純文字保留、新內容以服務端 allowlist 清理，照片正規化後放持久 data dir，匿名僅能取目前已發布照片。DB＋媒體備份 helper 已涵蓋封存、雜湊、還原與竄改拒絕；Docker 實際容器重啟／還原演練尚未執行。

- Windows/CPython 3.14.6：`uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp` **175 passed、2 第三方 deprecation warnings**。首輪 170 passed／5 failed 均為舊 schema head `0008` 斷言；修正後受影響 29 passed，再完成全套 175 passed。此後追加照片替換案例，`tests/test_website.py` 定向 **7 passed**；追加後未重跑全套。migration 0008→0009 在舊純文字公告上核原文、integrity 與 FK；媒體 helper 用隔離合成資料驗 DB/照片配對及 tamper 拒絕。
- `frontend/npm run typecheck` 與最終 `npm run build -- --outDir ../frontend/dist-admin-news-final` 通過，`npm audit --audit-level=high` 0 vulnerabilities。最終成品在隔離 Chromium 8051／`data/admin-news-e2e.db` 的桌面／手機 **6/6 passed**：行政報名與列印、公告格式／照片／發布下架、原排級數 80 人搜尋／格位基本回歸。截圖與管理 PDF 在 ignored `frontend/test-results/`。
- 曾誤選 `competition-levels.spec.ts` 整檔，Playwright 列出 94 案並在執行到第 12 案時主動 Ctrl+C，中止碼 1；不宣稱全 94 通過。最終成品一次定向六案曾為 5 passed／1 failed，手機拖曳目標格當時在 viewport 下方（目標 y=900、viewport 高844），測試事件未落入目標。測試先將目標格捲入視窗並等候插入預告顯示才放手後，手機定向重跑通過，最後桌機／手機六案單次全通過；未修改既有格位產品邏輯。
- 本機唯讀盤點確認原 `fucheng.db` 327 會員在兩候選庫保留同 ID/共同欄位，候選多 15 會員、9/20 的 80 confirmed 與一場明確測試賽 1 筆；兩候選所有共同業務列一致。`docs/acceptance.md` 既有 8032 紀錄指出候選另有預覽管理員及兩則使用說明公告。正式目標／入口仍待使用者決策，真實資料未寫入、未清理，現用 8044/8045/8047 未更新。新建 `8052` 本機合成預覽來自測試庫獨立副本，DB／媒體／static/帳密在 ignored 路徑；身份見 `data/admin-news-preview-identity.json`。

## B F 表頭選取／右鍵選單／白色色票公開更新（2026-09-23，待人工驗收）

b021／8044 已更新至 `data/grid-public-runtime/releases/grid-menu-20260923-102847`。59 source、3 static、14 docs/tests 與19項 evidence 逐檔 hash 核對通過；source aggregate `676db4866a50700147a641331bc416917b9ee8a3835fcc3ef50fa03a61a326cf`，static aggregate `5dabf888c310598cd30f887e17ff1f0f489a56b78ea61451068d8d7666600b5b`。local/public health JSON200，三公開資產 HTTP200/hash 相符且 no-store。WMI app46196／launcher39588／wrapper14308（parent WmiPrvSE52800），ngrok22148 沿用。AppOnly guard 停止前、啟動後及公開驗證後皆通過。

SQLite Backup API 停寫備份為 `data/grid-public-runtime/releases/grid-menu-20260923-102847/rollback/grid-public-before-menu.db`（SHA256 `4d1f782bfca7f8ba2f1e0b9262cf65f65f83d95b6ac1e695fb2d79d9161c8454`），另留91個舊 source/static/runtime/helper/log 的逐檔 hash。停寫備份、啟動後及公開驗證後的18表 count/hash一致，schema0008、integrity ok、FK0；保留2 workspace／9 versions／153 receipts（81筆舊receipt無undo metadata）。無 SQL migration，DB/admin/session 與其他 unknown 保留。

功能驗證沿用本凍結版：task4記錄的14項適用E2E案例證據（涵蓋桌面／手機內容選單生命週期與觸控開啟不送操作）、畫面檢查、43項後端案例及歷史／列印／XLSX證據，不重跑測試。明確 persistence 契約增加 explicit white／optional `header_merges`，舊 app 不保證解讀，雖 SQL schema 仍為0008，回退需 source+匹配備份成組處理。無可沿用公開 admin session，因此公開UI互動未重測；不登入、不操作使用者原頁。請使用者自行重整取得F，這不代表代清原頁狀態。證據為 `data/grid-public-runtime/grid-menu-update.json` 與 release before/after 資料 JSON。README／部署身份已同步；本輪未 stage／commit／merge／push。

## 前次 E 同色 no-op／底色色票公開更新（2026-09-22，已由 F 取代）

原 b021／8044 更新至 `data/grid-public-runtime/releases/grid-shade-20260922-222334`，58 source／3 static hash 符合 manifest；local/public health JSON200、三個公開資產200/hash一致且 no-store。WMI app33220／launcher50204，ngrok22148 不變，跨工具 guard 通過。停寫 Backup API 備份、啟動後與公開核對後的 18 表 count/hash 相同；schema0008、integrity ok、FK0，2 workspace／7 保存版／115 receipts（81 舊筆無 undo metadata）保留。

使用者精確警告與 task4 真實 D 同色 POST422 no-op → rejected 鎖場重現吻合。E 修正同色不送、精確首次422無變更自動GET核對、保留選取，其他422/409/unknown防護不變；表格底色整組共框與純白首項。沿用同版14不同適用案例的通過證據（不是單次14），最後 visual 2 pass／13.6s；不重跑無關 suite。公開 admin 互動本次未重測，未登入、找 session、操作原頁或 public 業務寫入；使用者可重整原頁載入 E，不能把部署當成原頁 pending 已解除。證據 `data/grid-public-runtime/grid-shade-update.json`、release before/after 資料 JSON；README／部署目前身份已更新，未提交／合併／推送。以下 D 的未知事件敘述保留為當時證據，現以本段及 task4 E 根因為準。

## B D 請求恢復／版面修正公開更新（2026-09-22，待人工驗收）

原 b021／8044 已更新至 `data/grid-public-runtime/releases/grid-recovery-20260922-215041`；58 source、3 static 與凍結 manifest 全部相符，local/public health JSON200、三個公開資產 HTTP200/hash 通過。WMI app24512／launcher63472，ngrok22148 不變。停寫 Backup API 備份與啟動後 18 表 count/hash 全同；schema0008、integrity ok、FK0，2 workspace／7 保存版／113 receipts（81 舊筆無 undo metadata）保留。

功能證據沿用下方 task4 同版 28 distinct E2E 的適用通過證據及同高／歷史捲動／header 檢查，不重建成品或重跑 suite。本次無可用原管理分頁，**公開 admin 互動未重測**，也未登入、清 cookie、掃描其他 session、reload 原頁或重送／discard unknown。修復的是合成重現的 receipt／恢復缺口，不代表已證實原上色事件根因或已解決原操作。公開證據見 `data/grid-public-runtime/grid-recovery-update.json` 與 release 的 before/after 資料 JSON；只保留聚合 count/hash，不輸出姓名、token 或 payload。README／部署目前身份已更新，未提交／合併／推送，待人工驗收。

## B 工具列／Excel／列印精修公開更新（2026-09-22，待人工驗收）

b021 已更新 `data/grid-public-runtime/releases/grid-export-20260922-173559`；58 source／3 static hash 符合 manifest，health JSON200、三個公開資產 hash 通過，WMI app34072／launcher46404、ngrok22148 持續存活。停寫備份與啟動、smoke 後 18 表 count/hash 全同；schema0008、integrity ok、FK0，2 workspace／7 保存版／113 receipts 全保留。

IAB 沿用 session，80 人可見、匯出 Excel 按鈕啟用，正常重新讀取按鈕為 0；歷史 aria-pressed/expanded 隨開關由 false 轉 true，背景白色／深綠切換；搜尋按鈕 40×40、SVG 20×20 置中。只切換歷史，沒有下載、列印、重新登入、業務寫入或未知請求重送。Excel 8 份讀取／3 份視覺與 5 份 PDF，以及實體 Excel／手機／印表機限制，沿用下方 task4 本輪證據。公開證據見 runtime 的 `grid-export-update.json`、`grid-export-browser.json` 及 release 的 before/after 資料 JSON；本輪未提交／合併／推送。

## B 雙欄／選手互動公開更新（2026-09-22，待人工驗收）

b021 已切換 `data/grid-public-runtime/releases/grid-panels-20260922-164146`，57 source／3 static hash 與凍結 manifest 一致；公開 health JSON200、三資產 hash 通過，WMI app12780／launcher6996、ngrok22148 持續存活。停寫備份與啟動、smoke 後 18 表 count/hash 全同；schema0008、integrity ok、FK0，2 workspace／6 保存版／109 receipts 可讀（81 舊筆無 undo metadata），沒有登入或業務異動。

IAB 沿用 session，1920px 開歷史後主表、該版本變動、版本紀錄依序左右排列且無重疊；80 人正常載入。單擊 03 選手格為 grid-selected、無詳情；雙擊打開原詳情，『選取儲存格』按鈕為 0，關閉正常。未拖曳、套色、改字、merge、undo、save 或重送未知操作；其他尺寸、手勢與列印沿用 task4 合成證據，沒有重跑。證據：runtime 的 `grid-panels-update.json`、`grid-panels-browser.json` 與 release 的 `before-data.json`、`after-start-data.json`、`after-smoke-data.json`。

## B 表頭／等待處理公開更新（2026-09-22，待人工驗收）

b021 已更新為 `data/grid-public-runtime/releases/grid-header-20260922-161245`；57 source／3 static 符合凍結 manifest，公開 health JSON 200、HTML／JS／CSS hash 通過，app53896／launcher67372 經 WMI 持續運行、ngrok22148 不變。停寫備份與新版啟動、唯讀 smoke 後 18 表 hash/count 全同；schema0008、integrity ok、FK0，2 workspace／6 保存版／93 receipts 全可讀，其中 81 筆舊 receipt 無 undo metadata，未補造。

IAB 沿用原 session，80 人可見；單擊「1 級」表頭後 BUTTON aria-pressed=true、th 內無輸入框，工具列底色／編輯文字啟用，復原與合併保持停用。只做選場與表頭選取，沒有套色、改字、拖曳、undo、merge、save、重新登入或未知請求重送。公開 smoke 不宣稱已重現／解決使用者原請求；逾時與寫入行為沿用 task4 同版本工程證據。來源：runtime 的 `grid-header-update.json`、`grid-header-browser.json`，release 的 `before-data.json`、`after-start-data.json`、`after-smoke-data.json`。

## B 局部底色／復原公開更新（2026-09-22，待人工驗收）

原 b021／8044 已更新至 `data/grid-public-runtime/releases/grid-undo-20260922-152840`，57 檔來源及 3 個公開資產符合 `delivery-identity.json`；新 app **24292**／launcher **60616** 經 Windows WMI 隱藏啟動，ngrok **22148** 不變。停寫 Backup API 備份與新版啟動、公開唯讀 smoke 後的 18 表 count／hash 全同，schema0008、integrity ok、FK0；2 workspace／6 保存版／81 舊 receipt 可由新模型唯讀解析，未補造 undo metadata。沒有 migration、重新登入、撤銷 session 或業務寫入，全部未大存差異保留。

IAB 沿用登入，80 人及新 JS／CSS 可見；上方工具列復原停用，選空格後純色色票可用、清除鈕為斜線，未套色。卡片姓名字體 16.32px、詳情右上 × 可關閉；歷史保存版無復原與編輯工具列。未試做有效 undo／move／color／text／merge／save；點外退出、復原寫入與 PDF 沿用本文件 task4 同版本工程證據，不重跑公開寫入。證據：runtime 的 `grid-undo-update.json`、`grid-undo-browser.json` 及 release 的 `before-data.json`、`after-start-data.json`、`after-smoke-data.json`。以下各輪描述均為當時狀態。

## B 灰階／雙區拖曳／歷次參考（2026-09-21，已公開換版待人工驗收）

task5 已於同一 eb24 完成 Windows 11／Python 3.14.6 受控更新：release `data/grid-public-runtime/releases/grid-interaction-20260921-120352`，56 檔凍結 source 摘要 `c00f5937c00291c58819e2630387d965a0bf3951f0ae9cb1a73c631ae30f83c2`，HTML／JS／CSS 各 200、SHA256 符合 manifest、Cache-Control:no-store，health 回 JSON 200。舊 2 workspace／5 個有布局保存版／47 receipts 可由新模型唯讀解析。停寫 Backup API 備份後，以同一 DB 啟新版；啟動即時及公開 smoke 完成後，兩次 18 表 hash／count 皆與備份一致，含會員、報名快照、布局、完整保存版、回執、稽核、admin/session。integrity_check=ok、foreign_key_check=0、schema0008；沒有 migration／reseed／重設密碼或撤銷 session。

獨立 IAB 分頁沿用原登入：新 assets 引用正確、鉛筆按鈕為 0；右鍵開啟整排操作，可見無底色／三階淺灰選單，僅關閉未選色。03 詳情含本場餐食、當次／長期級數與「最近 5 場已結束比賽」空態，移級下拉寬度 80px；舊完整快照無拖曳／軸選單，詳情的歷次參考另標「以下為目前查詢結果」，保存欄位仍獨立顯示。返回目前安排的全部格位內容一致。未執行 drag/drop/delete/color/text/save，也未為歷次查詢建立示範資料。證據為 runtime 的 `grid-interaction-update.json`、`grid-interaction-browser.json`，release 的 `before-data.json`、`after-start-data.json`、`after-smoke-data.json`。swap／insert／shade 的寫入有效性與 PDF 沿用下列相同交付版本合成證據，不在公開主場重做。

以下保留 task4 本機工程與歷次交付證據；各段「未公開／待換版」描述的是該次工程交付時點，現用身份以本節及部署手冊為準。

環境：Windows、Node24.11.0、Playwright1.63.0 Chromium桌面與390px觸控模擬。Python使用既有uv鎖定環境。只用新 `dist-grid-interaction`、`data/grid-interaction-e2e.db`／8043；未測其他OS／實機手機／實體印表機。無dependency/migration變更，不重跑Docker/GPU或無關管理功能。

- `npm --prefix frontend run build -- --outDir ../dist-grid-interaction`（tsc＋Vite）通過。後端 `uv run --locked pytest tests/test_grid_interaction.py tests/test_arrangement_grid.py tests/test_arrangements.py -q -p no:cacheprovider --basetemp .test-tmp-grid-interaction`：46 passed／25.67秒。涵蓋same/cross-column swap、上下insert與obstacle、empty拒占用、雙人audit第二筆失敗全回滾、replay/CAS/self no-op、level/version/hard snapshot、shade合法值／CSRF／terminal／old bytes／history、歷次exact member/同名/confirmed/取消重報/date cutoff/台北午夜/tie/limit5/匿名隔離/最小schema。審查發現audit關聯應符合既有before/after格式，修正後單項 `test_swap_two_levels_audits_versions_atomic_replay_and_noop`：1 passed／0.78秒，增加交換後GET稽核200與兩筆關聯response驗證。
- 初輪相關E2E `--grep '表格互動|拖曳修正|格位八十人|格位未知小存|格位文字409|格位大存未知|格位送出前|表格新版|表格刪除' --output test-results/grid-interaction-first`：33 passed／1 failed，1.5分鐘。既有28項全通過；唯一新mobile drag測試目的格未捲入viewport。新6項補跑 `grid-interaction-final` 為5 passed／1 failed（20.8秒），mobile改捲入後仍貼下緣，截圖等待觸發auto-scroll使預告改變；調整測試將目的格置中並在放手前再核預告，未放寬結果斷言。
- 拖曳另補強只採用已render preview，不取pending frame；最終 `--grep '表格互動：中央|拖曳修正|格位八十人' --output test-results/grid-interaction-drag`：8 passed／31.6秒。桌面/可信touch中央同欄及跨欄swap、上下before/after、empty、每次preview/action/實際格位、人數唯一、swap稽核GET，既有80人/ghost同尺寸/來源25%/click抑制/取消/503恢復/普通pan均通過。所有34個相關案例均有通過證據，不稱同一次34 pass。
- 新UI案例驗證精簡＋hover/focus、右鍵/觸控整排選取與色盤、無新增文字/鉛筆、三灰max交叉/merge、保存還原無淨差、immutable歷史及print；歷次late A不污染B、關閉重開、換場、空/error、live參考與已存diet/level分離；詳情移級select80px與次要按鈕。文案採「歷次比賽級數／最近5場已結束比賽」，僅歷史有短註。
- 實際三種背景設定PDF：`--grep '表格互動：精簡邊界' --project desktop --output test-results/grid-interaction-pdf`：1 passed／8.3秒。每份PDF會觸發afterprint清理，因此測試每次重新建立printJob且斷言4人；**first/final目錄早期gray-background-off/on.pdf是在清理後誤印管理頁，不作證據**。正式PDF僅使用grid-interaction-pdf。三份均1頁、000..003各一次；Poppler100dpi PNG含237/217/196三階灰，merge採217。default/off逐像素一致；on保留全域頁首CSS背景，因此全頁不同，但灰階格與merge實際取樣色值一致、姓名完整。已目視黑字／格線／灰階，未操作實體印表機。PNG和機器核對結果在 `data/grid-interaction-pdf/verification.json`；off PNG為 `gray-background-off-1.png`。
- screenshot證據：`frontend/test-results/grid-interaction-drag/competition-levels-表格互動：中央交換上下插入空白移動與預告一致-mobile/` 的 `intent-swap-0.5.png`、`intent-insert-0.1.png`、`intent-insert-0.9.png`、`compact-person-detail.png`；桌面同名project。`grid-interaction-final` 的 `history-reference-separation.png`及`grid-interaction-pdf`的`gray-history.png`保留參考區／灰階歷史證據。
- 任務仍在原B worktree/feat/competition-arrangement-grid，base89cae097；未stage/commit/merge/push。公開axis版及所有使用者資料/未大存差異未由task4變更，前輪UNKNOWN來源不追查不歸因。交付identity `data/grid-interaction-delivery-identity.json`；完成後source/tests/docs/artifacts全停寫，由orchestrate驗收後task5受控同網址換版。工程完成與人工接受／公開更新分開。

## B 刪除行欄、素食開關與歷史順序（2026-09-21，本機完成待公開換版）

- `npm --prefix frontend run build -- --outDir ../dist-grid-axis`（tsc＋Vite）通過；未覆寫dist-grid／dist-grid-drag／dist-grid-edit。無migration或依賴變更。
- 後端 `uv run --locked pytest tests/test_arrangement_grid.py tests/test_arrangements.py -q -p no:cacheprovider --basetemp .test-tmp-grid-axis`：41 passed、1 failed／25.16秒。唯一失敗為新增測試誤用大存HTTP201，修正為現有200後，以 `tests/test_arrangement_grid.py::test_delete_axis_confirm_cas_replay_history_and_registration_invariants`、`--basetemp .test-tmp-grid-axis-cas`補跑1 passed／0.89秒。42項均有通過證據，未稱同一次42 passed。覆蓋刪軸merge頭中尾縮小、單格解除、唯一文字保留／搬移、空白anchor、衝突原子拒絕、stable target、strict bool、文字/title確認、stale/replay、CSRF、audit注入失敗全回滾、ended拒絕、固定十級／含選手／最後body保護；保存版不變、其他選手座標／version不變。
- 初輪新增3案例×desktop/mobile：6 passed／17.5秒，`frontend/test-results/grid-axis-first`。修正低位置多文字popup高度後，`npm --prefix frontend run test:e2e -- --grep '表格刪除|拖曳修正|格位八十人|格位未知小存|格位文字409|格位大存未知|格位送出前|表格新版：邊界' --output test-results/grid-axis-final`：24 passed／53.0秒。涵蓋刪除scope/文字確認取消、保護、保存前歷史不變與列印、captured token409、503已提交回應遺失原樣重試不重複revision、選格清理；素食on/off顏色及aria、人數/格位不變無寫入；歷史0..14升序、首次底部、舊版閱讀/重讀不跳、新大存15到最新。加上既有80人、drag/取消、邊界與小大存/斷線/切場回歸。
- 低位置多文字案例使用1000×600桌面與390×600手機，10格各300餘字，選單與dialog內容實際可捲到最後、保留／刪除／關閉按鈕在viewport；已目視 `axis-low-menu.png`、`axis-long-confirm.png`。三項功能截圖均在grid-axis-final各project輸出。
- 補強原CAS案例desktop inline draft：409及503未知仍保留原輸入，成功receipt＋讀回後編輯器／失效選格清除；兩次payload與captured token一致。`--grep '表格刪除：確認綁舊token' --output test-results/grid-axis-draft`：2 passed／9.6秒。僅測試加斷言，production source/static未再變。
- 全部E2E用PYTHONUTF8=1、8043、`FUCHENG_E2E_DATABASE_URL=sqlite:///data/grid-axis-e2e.db`、`FUCHENG_E2E_STATIC_DIR=dist-grid-axis`、單worker。未操控公開eb24、現用DB/admin/session/80人安排或未保存差異。手機為Chromium觸控模擬，不替代實機；本輪無新PDF/實體印表機證據，列印實作未改、完整PDF證據沿用前輪。drag仍插入下移，交換未授權。
- 交付身份 `data/grid-axis-delivery-identity.json`；branch feat/competition-arrangement-grid，base89cae097，未stage/commit/merge/push。task4交付後停寫source/tests/docs/artifacts，task5再依新identity受控換版；工程驗證完成不代表人工接受或公開部署完成。

## B 表格直接編輯與列印（2026-09-21，本機工程完成待公開換版）

使用者授權的五項增量已完成：實際邊界＋新增／＋標題與落點線、文字／合併格／欄顯示名稱直接編輯、矩形框選、柔和素食標記、當前／歷史安排列印。桌面雙擊Enter提交／Escape取消，IME composition不誤送；手機明確編輯／二點範圍選取、原生pan。首次框選不需先選格、不需Shift，浮動工具不推表。姓名／把手仍拖人與查看，dragfix不退化。全部操作沿用B串行、token、transaction/audit及receipt恢復邊界。

- 建置 `npm --prefix frontend run build -- --outDir ../dist-grid-edit`（含tsc）通過；獨立新成品，不覆寫dist-grid／dist-grid-drag或runtime static。無新增migration或依賴。
- 後端 `uv run --locked pytest tests/test_arrangement_grid.py tests/test_arrangements.py -q -p no:cacheprovider --basetemp .test-tmp-grid-edit-final`：**33 passed／23.12秒**。驗證title-only小存/大存/history、舊0008 JSON raw bytes不回填、missing/null/default等價及復原淨差歸零、會員/報名級數與version不動、非anchor合併文字經插列/改字/unmerge仍在原格、空白merge使用anchor、stale/replay、CSRF、audit注入失敗全回滾、ended阻擋。首次新增terminal測試誤用completed enum已改為合法closed→ended，未改產品驗收標準。
- 最終 `npm --prefix frontend run test:e2e -- --grep '格位|拖曳修正|表格新版' --output test-results/grid-edit-complete`：**26 passed／1.0分鐘**，單worker desktop1440/mobile390，另測桌面1800宽度。環境 `PYTHONUTF8=1`、`FUCHENG_E2E_DATABASE_URL=sqlite:///data/grid-edit-e2e.db`、`FUCHENG_E2E_PORT=8043`、`FUCHENG_E2E_STATIC_DIR=dist-grid-edit`。保留全部20既有格位/拖曳案例加6新增，未放寬恢復/未知/late receipt斷言，沒有重跑無關管理全量或部署演練。
- 新增trusted desktop mouse首次未選取直接框選，起點／終點精確且表格y不變；跨有人格merge被拒絕且人不移。手機tap編輯/二點範圍選取、素食標記、桌面雙擊與取消、標題復原、合併原位字、邊界插入stable IDs、title 503原payload重試/切場保留均通過。
- 首輪舊測試仍找已移除「＋末列」導致恢復案例失敗；已改為同操作的新邊界入口。24/26輪另發現查看姓名同時啟動範圍工具可能遮住手機把手，已分離查看與選格並通過上述最終26。均保留原斷言，未跳過失敗。
- PDF以合成80人、11欄當前/歷史，以及14欄20body列寬長表實際輸出，Poppler渲染全部頁、逐頁目視無姓名缺漏／截斷／工具欄；pypdf對嵌入字型康熙部首先NFKC正規化，確核三份PDF每位選手恰一次。A4橫向841.92×594.96pt，當前1頁27個素、歷史1頁27個素、現況餐食變更後寬長表5頁26個素。寬表有橫向合併續接、body合併跨段保留、最後原格的第039號僅出現一次。DOM也核對每registration ID恰一次，不受姓名搜尋／素食toggle影響。
- 單幅不加技術列號；寬長表4個邏輯分幅因實際文字行高為5個紙頁，額外頁重複欄表頭，分幅/合併續接清楚；未宣稱18列必定一紙頁或任意500列50欄可塞一页。超長文字／更多表頭／不同字型、紙張與瀏覽器可能進一步分頁，仍需列印預覽核對。
- 列印關閉/取消後afterprint清理portal、切場/切版亦清理；測試mock列印與真PDF均核對清理後app恢復。早期第二/三份PDF因測試explicit screen emulation輸出screen CSS，已更正每份PDF擷取前明確print media並斷言app隱藏/print可見；本節僅引用最終grid-edit-complete PDF。

手機補驗：main指出complete截圖仍有desktop hint且左邊界接近裁切。已在既有mobile案例末段改為純tap並把scrollLeft回0；明確斷言「範圍選取」可見、desktop hint隱藏，實際tap左側插欄＋與上側插列＋，驗rows/columns各+1，再二點選取得到2格且scrollLeft=0。`npm --prefix frontend run test:e2e -- --project mobile --grep '表格新版：邊界' --output test-results/grid-edit-touch-origin`：**1 passed／9.5秒**。新viewport截圖 `frontend/test-results/grid-edit-touch-origin/competition-levels-表格新版：邊界插入、直接標題與合併原位文字、框選-mobile/grid-edit-mobile-touch-origin.png` 目視左＋/範圍入口清楚。原因是先前case混用.click及水平捲動的截圖狀態；production code/static未修改，未重build／重跑26項。

證據路徑（以下相對B worktree）：

- `frontend/test-results/grid-edit-complete/competition-levels-表格新版：邊界插入、直接標題與合併原位文字、框選-desktop/grid-edit-interactions.png` 及同名mobile目錄。
- `frontend/test-results/grid-edit-complete/competition-levels-表格新版：完整列印與歷史凍結、寬表長表分幅-desktop/arrangement-current.pdf`、`arrangement-history.pdf`、`arrangement-wide-long.pdf`。
- 全頁渲染 `data/grid-edit-pdf-final/current-1.png`、`history-1.png`、`wide-long-1.png`～`wide-long-5.png`；抽取核對 `verification.json`。
- 來源/static身份 `data/grid-edit-delivery-identity.json`。branch仍feat/competition-arrangement-grid，base89cae097，既有未提交工作保留；未stage/commit/merge/push。8042 listener56896、8044 listener44424仍在、8043已退出，未改publicDB/admin/session/安排/未大存差異。沒有實體印表機／實機手機／公開換版證據。task4交付後source停寫，task5再受控更新同eb24。

## B 拖曳互動修正（2026-09-21，本機工程完成待公開換版）

使用者在eb24驗收後指出拖完會開資訊卡與拖曳視覺不足。本輪只修改三個應用來源：`useLevelCardDrag.ts`、`LevelCardBoard.tsx`、`styles.css`，其餘B source（含全部後端／migration）hash與前輪交付一致；不修改現用eb24/A服務、DB、密碼或session。既有所有dirty保留，未commit/merge/push。

原因：pointerup呼叫onMove使小存進入blocked，瀏覽器後續click又被姓名按鈕的blocked分支當作查看；hook清除active後沒有保留該pointer的拖曳click歸屬。現在在window capture只攔截同次真拖曳完成/取消後的派生click，跨來源把手／姓名及落點皆生效；新pointerdown立即釋放歸屬，keyboard激活不阻擋，不用延遲全禁click吞下一個正常操作。普通查看統一由click觸發，取消時也清理pointer capture/計時器/visual。

單一ghost改由body portal呈現，寬高取來源姓名卡，僅姓名＋原辨識註記；desktop跟游標、touch浮在手指上方，限制於viewport。active來源opacity=.25但原格保留，drop/Escape/touchCancel/失敗後恢復1；普通touch捲動不啟drag。grab僅可拖曳格，busy/readonly保留正常查看游標，active時grabbing。沒有改精確格位/插入/小存/大存/歷史/搜尋/合併契約。

- `npm --prefix frontend run build -- --outDir ../dist-grid-drag`（含tsc）通過；新獨立成品 `dist-grid-drag`，未覆寫8042使用中的dist-grid或eb24 frozen static。
- 首輪 `npm --prefix frontend run test:e2e -- --grep 拖曳修正 --output test-results/grid-drag-first`：**4 passed／13.9秒**。main目視desktop drag-preview-cell-name及mobile drag-preview-cell-grip確認尺寸／內容／淡化方向。
- 補可拖曳游標scope及普通把手tap/click回歸後，最終 `npm --prefix frontend run test:e2e -- --grep '格位|拖曳修正' --output test-results/grid-drag-final`：**20 passed／41.8秒**（原B16＋新增4）。只跑受影響格位範圍，沒有重跑原12管理案例或backend/migration演練。
- E2E使用8043、`data/grid-e2e.db`、`FUCHENG_E2E_STATIC_DIR=dist-grid-drag`、`PYTHONUTF8=1`，初始化的只有專用合成測試庫。trusted mouse由來源姓名/把手拖到目的姓名、trusted CDP touch長按把手拖到目的姓名，刻意掛起成功後GET，覆蓋最容易誤觸的blocked窗口。断言drop後無dialog、ghost可見及內容/尺寸/跟手座標、來源opacity=.25/清理回1、立即下一次click/tap與keyboard仍開；另測Escape/touchCancel/503失敗、busy詳情查看、普通touch橫捲不寫也不殘留淡化。最終截圖保存在grid-drag-final各project目錄。
- 交付身份 `data/grid-drag-delivery-identity.json`：50 allowlist來源清單及新static三檔SHA；`changed_since_B`只有上述3檔，原dist-grid三檔與前次identity完全一致，`git diff --check`通過。JS `index--v5lmZ5o.js`、CSS `index-C7LmpEmg.css`。task5須依新identity核對並凍結換版；舊grid-delivery-identity仍保留供比對。
- 收尾8042 listener56896與8044 listener44424維持，8043已退出，未另建預覽或操作現用session。手機是Chromium可信事件模擬，不替代實體手機驗收。新bundle尚未更新eb24；由orchestrate序列安排task5。task4交付後source停寫。

## B 公開入口增量驗收（2026-09-21）

最新 axis 三項功能版於同一 eb24 發布，54 個 production 檔摘要 `5abb9dd18a96aae083bcab6a5eaf62d703daa6f522537b5b317ae56fb17efc5b`。發布前新版唯讀解析原 2 workspace、5 個有布局保存版、47 receipt 成功；停止 B app 後 Backup API 備份，原 DB 啟動新版後 18 表 hash／count 完全一致。公開有限 smoke 結束後 18 表仍完全一致，integrity_check=ok、foreign_key_check=0、schema0008，未 migration／reseed／改密碼／登出／大存。

實際 IAB 獨立分頁沿用 session：第 5 排含 10 位選手時刪除停用，第 11 直欄固定級數欄刪除停用；第 4 排文字預覽列出甲／乙／丙組，進入確認後焦點在「保留這個範圍」，選保留退出，沒有提交刪除。素食按鈕 on 為 aria-pressed=true、深綠 rgb(40,92,62)／白字，off 為 false／白底。歷史依起始基準→合成完整布局→公開 B 格位驗收→版本 3 排列，版本 3 帶最新標籤；首次清單 scrollTop=42、scrollHeight=330、clientHeight=288，已到底。讀取舊版後拖曳／邊界選單皆為 0，返回目前安排全部格位內容一致。證據：runtime 的 `grid-axis-browser.json`、`grid-axis-update.json`，release `grid-axis-20260921-113513` 的 before-data／after-start-data／after-smoke-data JSON。先前 UNKNOWN 活動紀錄保留，不因本次一致而改寫其歸因。

沿用 task4 的 backend 41 項通過＋修正錯測後單項 1 項通過（不是一次 42 項）、24 E2E／53 秒＋draft/token 2 項／9.6 秒，以及含 tsc 的 build。沒有重跑無關全量、重產 PDF 或實機觸控驗收；列印與拖曳 insertion/downshift 行為保持既有範圍。工程公開驗證完成，使用者人工驗收另行確認。

最新五項功能版已於同一 eb24 更新（11:08 台北）：production 53 檔摘要 `eaf8d9ce6f002a89575710641bd36886c4da59812a89ec6ede17fe670b76eb48`，成品 dist-grid-edit。發布前既有 2 個 workspace、4 個有布局保存版、32 筆操作 receipt 均可由新模型唯讀解析；停止 B app 後 Backup API 備份，啟動新版後 18 個資料表的 hash／count 全部一致（包含原 JSON bytes、稽核、admins、login_sessions、會員／報名快照）。integrity_check=ok、foreign_key_check=0、schema0008，沒有 migration、重建資料、大存或 session 撤銷。公開 `/api/health` 為 JSON 200，HTML／JS／CSS 全部 200、hash 符合 manifest、no-store。

實際獨立 IAB 分頁沿用既有登入：取消拖曳後無詳情誤開、無 ghost、格位不變；正常點擊 03 詳情成功；合併文字原位編輯後 Escape 退出且文字／格位不變。列印按鈕建立完整 80 人、20 個「素」的 print DOM，registration IDs 與目前全名單相同，print CSS 已載入；IAB 本輪未進入實際 print media，媒體版面與分幅證據沿用 task4 已驗證 PDF，不能稱為公開實機列印完成。本 task 沒有有效 drop／插入／文字提交／完整保存。

重啟當下的 18 表一致證據與後續使用情形分開記錄：11:08:37–45 出現 10 筆後續 insert_row／insert_column 操作，11:09:53 的 smoke 後比對 workspace／operations／competition_audits 因此不同，其餘 15 表含 session、會員、報名及保存版仍相同。11:11:24 又有一筆 insert_row；來源目前 UNKNOWN，不能歸因 main 或使用者。task5 手勢前首次 DOM 的行列 ID 及 80 人座標精確吻合 revision36，代表前兩筆已先發生；revision45 在 task5 驗證分頁關閉後發生，中間時段不能僅凭共用 admin actor 判定 client。沒有已確認的非預期 UI trigger，也未為此新增測試寫入；時間線已交 orchestrate 判斷。這些後續變更完整保留，不還原成舊備份。證據位於 runtime 的 `grid-edit-update.json`、`grid-edit-browser.json`、`grid-edit-operation-timeline.json`、`grid-edit-initial-dom.json`，及 `releases/grid-edit-20260921-110654/before-data.json`、`after-start-data.json`、`after-smoke-data.json`。沿用 task4 已交付 33 backend、26 E2E、追加 touch 1 項與 PDF 證據，未重跑完整測試；人工驗收仍由使用者決定。

後續拖曳修正：task4 的 `dist-grid-drag` 已切至原 eb24，source50 摘要 `490b5aa7ead24f1a7b744a26e99aa2e0fed03c65bff102768c0c81a95dfa65ef`，只變更三個 frontend 來源。公開 HTML／JS／CSS 200、SHA256 與 manifest 一致、Cache-Control 均 no-store；原凍結來源未改。獨立 IAB 分頁使用既有 session，拖起合成 03 後移出表格取消，格位完整一致、無詳情誤開、ghost 已清；隨後正常點擊姓名可開啟詳情。未在主場有效落格、大存、重設、登入或登出；原本已有未完整保存差異並保留。切換前後會員、報名、安排 workspace／operations／versions、稽核與 admins 表 hash 一致。drop／saving 競態及 mouse／touch 由 task4 隔離環境 20 項 trusted E2E（41.8 秒）與 typecheck／build 通過證據支持，本次未重跑或外推為物理手機驗收。增量證據：runtime 的 `frontend-drag-update.json`、`frontend-drag-browser.json`。

B 公開入口為 `https://eb24-140-116-158-107.ngrok-free.app/admin/competitions`，以下為本次增量證據，補充後文 task4 的本機交付紀錄。B 仍為 `89cae09754eaefa4dba6c3dce308482526f33ff2` 加未提交變更；50 檔來源 SHA256 `c25556fbde911448ce2672e0082ed9056b6aad48447a36fbce3f7b77bf546f2e`，原來源與凍結副本、3 檔 dist-grid 與公開 static 最終全部相符。

- 正常 TLS 的公開 health／登入／管理讀取均 200。匿名管理讀取 401；錯誤 Origin／缺 CSRF 403；錯 Host、缺代理頭、HTTP forwarding、非信任 loopback forwarding 及公開偽造 forwarding 均 400；cookie 為 Secure、HttpOnly、SameSite=Lax。
- 實際公開 IAB 桌面 1440×900：將合成 02 從第一隊第 2 級拖到同列第 1 級的指定空格，原格留空，畫面顯示已自動儲存；整頁 reload／重選場次後，完整格位 DOM 與重載前一致、80 人仍全數存在。
- 經正常 UI 保存「公開 B 格位驗收」，打開該歷史版本後格位／合併／文字相同、拖曳 handles 為 0；返回目前安排仍完全一致。歷史讀取與返回前後所有 SQLite 表內容 hash 均未改變。
- main 另在真正 IAB tab2 登入確認甲乙丙表頭／左隊名／密集表格、04 的本場餐食與當次／長期級數、欄底移動說明、素食 20 人、搜尋 80 後 1 姓名／79 占位；已清除篩選與選取，無管理寫入。task5 沿用 main 回報，未重複或撤銷其 session。
- 新庫由 8042 合成庫以 SQLite Backup API 複製，初始逐表一致；保留原管理員及歷史 actor，再以既有 CLI/hash_password 建立已授權 admin。最後確認會員與 hard_level_snapshot 未改、原保存版完整保留、只新增 1 個完整保存版、integrity_check=ok、foreign_key_check=0，schema 為 0008。

本次證據存於 B 的 `data/grid-public-runtime/identity.json`、`ready.json`、`security.json`、`browser.json`、`desktop.png`、`final-verification.json`。既有 109 backend／final affected 9／28 E2E（B 16＋既有 12）、型別及 build 結果沿用 task4 交付，不形式重跑；觸控證據仍是模擬測試，沒有真實手機觸控或球館現場驗收。工程驗證完成不代表使用者已接受；未 commit／merge／push／建立 B image／正式部署。

2026-09-21階段A Git交付範圍：緊湊表格、完整安排保存／唯讀歷史、0007、必要測試與部署接續文件，共33項來源變更；從 `0970af2` 整合至main並正常推送，沒有納入後續B需求。整合核對48個應用來源與3個runtime靜態檔仍符合公開驗證身份，沿用下述101項後端、final affected 39項及22項E2E與公開80人證據，不形式重跑。DB、帳密、成品與ignored launcher不進Git；未執行的Docker drill仍僅為準備腳本。以下「未提交」及資源狀態均保留為各次驗證當時紀錄，最新Git身份以交付commit／main／origin/main核對為準。此Git交付不重啟預覽、不改資料／帳密／session，也不是正式部署或Docker hold解除。

## B 精確格位安排表（2026-09-21，工程驗證完成待人工驗收）

B從A已推送提交 `89cae09754eaefa4dba6c3dce308482526f33ff2` 建立唯一worktree `D:\projects\fucheng-players-system-worktrees\arrangement-grid`，分支 `feat/competition-arrangement-grid`；自己的.venv與node_modules，未改依賴lock。A從主目錄src載入8041，因此B source/DB/static/port均隔離。未commit/merge/push、未公開部署，worktree保留待驗收。

已實作與驗證：精確格位小存／重載，同欄位置也保存；有人格先挪來源留洞、目標插入向下，僅推必要選手，保留原空洞／文字／merge，必要時增列；點選／鍵盤落目標欄底。受影響選手version更新，舊直接level stale409；會員長期級數與hard snapshot不改。行列穩定ID，插空列不把每人視為重新分組。header/body分層保存，甲乙丙合併在數字級數標頭上方，左側文字隊名可對齊選手橫列。文字/空格可合併與解除，多文本/選手/既有merge/跨數字標头明確拒絕；原底格內容保留。

搜尋只呈現匹配姓名，其他人顯「已占用」不壓縮格位；搜尋後拖進隱藏占位仍插入讓位。素食以本場diet計數/外框高亮，不篩人、不改異動色；詳細卡含本場餐食、當次/長期級數，舊history未記錄欄位為未知。位置/級數改回基準清色，完整保存含文字/行列/merge，歷史唯讀、返回不寫入。未知結果及成功待fresh GET整場鎖，固定payload原樣重送，不用舊receipt覆蓋較新布局；409重新核對，文字草稿跨場保留。純布局/文字修改有實際admin與時間audit。

### 實際驗證紀錄

- `uv sync --locked`：獨立Python3.14.6/.venv成功；`npm ci`：123套件、0 vulnerabilities，沒有依賴修改。
- 原 arrangements＋levels聚焦回歸：33 passed／21.32秒；新初版grid5 passed／2.90秒。
- 全套 `uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-grid-all`：**109 passed／53.86秒**。之後只收緊diet回應Literal與新增公開報名同步測試，`tests/test_arrangement_grid.py --basetemp .test-tmp-grid-final`：**9 passed／5.04秒**。只有2項既有FastAPI/Starlette棄用warning；不將局部結果稱為重跑全套110。
- 包括strict操作/明確GridLayout與receipt、跨API request_id409、位置與級數交易、公開正取新增/取消/遞補、所有被推選手version、同token兩admin一成一409、old receipt重送、workspace/operation/audit失敗rollback、insert header/文字merge/解除、多文本拒絕、文字欄不能落選手、移回無淨差。
- 0007→0008合成含3個舊歷史版：舊所有表原欄位與rows_json原文逐欄一致，新layout全null、workspace/operations空，沒有回填歷史；pre-upgrade backup還原新target仍0007且舊snapshot相同。升級後integrity=ok/FK=0、Alembic check無差異。舊history API schema1/layoutnull、diet/member_level未知；B POST初始化不改舊latest且保留未大存級數差，第一次B大存schema2包含全部布局。
- `npm --prefix frontend run build -- --outDir ../dist-grid` 含tsc通過。最終JS `index-CzXpTD6B.js`，CSS `index-LxQ8-DAs.css`；`git diff --check`通過。沒有把dist建進A成品或其static。
- E2E全程 `FUCHENG_E2E_DATABASE_URL=sqlite:///data/grid-e2e.db`、port8043、static `dist-grid`、`PYTHONUTF8=1`，單worker、桌面1440×900／手機390×844（isMobile/hasTouch）。A的卡片/級數專用10 UI案例改写為B的16格位案例，其餘12管理/公開/刪除/匯入回歸保留。
- 首次B10項為5過/5失敗，包含重載後測試沒重選場次、文字輸入定位、mobile測試目標位置；修正fixture/定位並用明確文字aria-label，套用main最新搜尋隐藏占位語義後，`--grep 格位 --output test-results/grid-second`：10 passed／23.2秒。
- 擴至26項 `test-results/grid-all`：22 passed/4 failed（1.2m），同一合成帳號累積登入達既有限流，後段4項停在登入。改為每desktop/mobile獨立合成帳號，不變更限流規則，並新增最遠欄觸控案例。
- 最終 `npm --prefix frontend run test:e2e -- --output test-results/grid-final`：**28 passed／59.0秒（B16＋原12）**，非首次全綠。含trusted mouse/CDP touch長按、Escape/touchCancel、普通touch橫捲不寫、邊緣自動橫捲到第10欄、80人搜尋後drop到真占用格、重載精確坐標、keyboard欄底、素食/詳情、header合併及左隊名、完整history、位置/級數復原清色、純插列不染所有人、外部終態重讀唯讀、前置斷線/commit後503/GET失敗整場鎖、文字409切場草稿、切場晚回應、大存未知後真另一admin另存/再修改原keyretry保持fresh latest。8043測試服務完成後退出。

### 8042合成預覽與限制

[本機安排預覽](http://127.0.0.1:8042/admin/competitions) 使用 `data/grid-preview.db`／`dist-grid`；83合成會員、3場、85報名，主場80人＋合成甲乙丙/隊名。腳本variant grid新建，沒有用照片姓名或讀A DB。`data/grid-preview-verification.json`記新庫與initial backup/restore：integrity=ok/FK=0/revision0008且筆數相同。這不是正式資料或Docker/volume演練。

`node data/grid-preview-qa.cjs`對兩尺寸只登入、選場、搜尋、素食切換與history：80姓名格、11欄（十級＋文字）、1標題列，表高約505.5px；搜尋匹配1姓名、79占位；本場素食20，無頁面水平溢出/pageErrors，adminWrites=[]。結果 `data/grid-preview-browser-verification.json`、六張 `data/grid-preview-{desktop,mobile}-{table,search,history}.png`；desktop table與mobile search已目視核對。main另目視grid-second截圖確認版面方向；這不是使用者已驗收，也不代替球館實體手機。

8042 listener **56896**／launcher **59956**，PID檔 `data/grid-preview.pid`、`grid-preview-launcher.pid`，logs同前綴stdout/stderr。帳密僅ignored `data/grid-preview-admin.json`，停止依README先核對當下PID/port/身分；留供驗收，未清理。主目錄A與現用f9d0/8041 source、DB/static/密碼/服務及Docker/GPU均未操作。B來源身份清單與static hash交付 `data/grid-delivery-identity.json`（後續凍結/公開由task5核對），不把未提交worktree冒稱A提交內容。

已更新README/AGENTS/architecture/deployment；限制：最多500列/50欄、500字/格，合併文字先解除再編輯；無隊伍/對戰引擎、公式、Office匯入、協同游標或安排列印。公開B與使用者驗收由orchestrate接續安排，task4本輪未擴交付授權。

## 緊湊級數表格與完整安排版本（2026-09-20，取代下方 A+B 使用方式）

本輪工程驗證完成，等待使用者人工驗收；新功能已提供獨立原生HTTPS合成入口，舊Docker環境尚未更新。排級數以1～10橫向欄、低列高姓名格呈現，正取以外資訊及比賽設定移至「報名與設定」。移動不需要原因，逐次稽核留實際admin／時間／前後值；起始基準只建立一次，大存不可變完整快照、可選版本名稱／顯示編輯者／備註、server秒時間。現在工作對最新保存版、歷史對直接前版，新增／移出依報名ID辨識；不把報名快照當上版。公開資料與其他管理操作原因限制不變。

既有ngrok合成預覽的Docker升級於2026-09-20 14:34台北因共用Docker不可用而hold：ps API500、version兩次unable to start；當時舊公開health404、8448/8450逾時，8039仍200。沒有build／volume操作／migration／舊env變更或重啟共用服務。離線allowlist與指定合成0006備份已核對；`deployment_arrangement_drill.py`只有py_compile／--help通過，**不是遷移或回退已驗證**。證據 `data/deployment-ngrok-r11-evidence-20260920/preflight-blocked.json`；r11 image／Docker演練仍未執行。其後另獲授權建立下列原生入口，不代表解除Docker hold。

原生公開合成驗收（2026-09-20 22:44～22:52台北）：

- [公開新版安排管理](https://f9d0-140-116-158-107.ngrok-free.app/admin/competitions) 正常TLS載入、登入與health JSON200。首次ngrok提示可按Visit Site，未略過TLS驗證。獨立 `data/arrangement-native-preview.db`、0007、83合成會員／3場／85報名，主場80正取；未讀取或複製真實資料／舊volume。初始Backup API備份還原與Alembic metadata check通過。
- 已驗證48個應用來源及3個靜態檔SHA，從 `frontend/dist-arrangement` 複製到獨立runtime/static，沒有重建舊成品。browser公開驗收沿用已驗證核心程式，不形式重跑既有全套測試。
- CUA真實瀏覽器桌面1440×900：80人十欄、拖曳不問原因、自動儲存、重載仍為1→4；回基準清色且無淨差不能大存。第一次採預設「版本 1」、登入帳號作顯示編輯者、空備註；保存後清色。再拖4→6按上一保存版顯色。
- 手機viewport390×844：搜尋圖示展開、按辨識註記縮至1人，表格寬1100px、捲至最右第10級，頁面無水平溢位。手機尺寸完成第二次保存，自訂「公開驗收版本 2」／「合成現場編輯者」／備註；保存後清色。實際操作帳號仍獨立列出levels-preview-admin。這是桌面瀏覽器尺寸模擬；未宣稱實體手機或本次觸控長按已驗證，既有touch E2E證據仍見下方。
- 歷史第二版相較前版4→6，第一版相較起始基準1→4，皆完整80人、唯讀；回目前安排保持6級及無淨差。時間顯示至秒（基準22:43:31、第一版22:48:26、第二版22:49:45）。三版各80列；基準在首次合法合成調級前實際建立，沒有偽造過去基準。
- DB只讀核對：歷史瀏覽前後全部16表hash相同；會員全列、hard_level_snapshot及其他非調級報名欄位與初始備份一致。此次瀏覽器新增5筆level audit（含合成選手03的3→1→3往返及同名選手3→1→4→6），原因皆null，保留逐次歷史；integrity=ok、FK錯誤0。
- 安全：未登入管理401；錯誤Origin／缺CSRF403；錯Host／缺forwarded／HTTP proto／公開偽造forwarded／來源127.0.0.2的forwarded均400；Secure／HttpOnly／SameSite=lax。僅127.0.0.1:8041 listener，信任同機loopback程序，沒有Docker網路隔離保證；inspector／remote-management關閉。沒有公開debug或access body日誌。
- 保護核對：48來源、3複製成品、當次36個既有檔案及先前439個保護檔案皆未改（大封裝沿原基準只比size／mtime）。8037 PID57548與8039 PID55404保留；Docker／GPU零操作。browser console無error/warn。

完整證據在 `data/arrangement-native-runtime/`：`identity.json`、`security.json`、`browser-evidence.json`、`data-verification.json`、`protection-final.json`、`desktop-current.png`、`mobile-history.png`。登入檔、PID／停止方式見README。原生入口已可人工驗收，但不代表使用者已接受、正式部署完成或r11 Docker升級／回退完成。

功能驗收後另依使用者指定新增合成 `admin`，同庫之外未寫入。過程曾短暫套用短密碼；最新指示已改用既有hash_password的正常12字元規則，取消fixture例外並撤銷所有admin舊sessions。最終新密碼HTTPS登入200、管理讀取200、登出204，舊密碼401；定向session撤銷前200／撤銷後401，Secure／HttpOnly／SameSite仍有效。原管理員及版本actor保留，帳密只存ignored檔，沒有寫入產品預設或更改正式規則；最終證據 `admin-rotation-verification.json`。上述16表不變證據特指歷史瀏覽區間，不包含其後已授權的admin／session修改。

共用owner於22:54:49已恢復Docker並停止舊府城容器至exited，由main／orchestrate轉達；本task未操作或重新探測Docker，hold持續。原生入口未受影響，舊Docker/r11仍不在本次已完成項目內。

23:09入口恢復：8170原生程序後來消失，根因未知；免費agent拒絕指定重用，因此目前入口改為f9d0且app使用精確新Origin。80人完整功能驗收於原8170完成，來源／DB／成品不變；新入口補做最新正常密碼登入及session撤銷驗證。舊8037／8039在恢復查詢時亦無listener，本task未操作它們。新app／ngrok已跨啟動工具shell結束保持運作；不宣稱永久背景執行。

後端與 migration 證據：

- 首輪 `uv run --locked pytest -q tests/test_arrangements.py tests/test_competition_levels.py -p no:cacheprovider --basetemp .test-tmp-arrangements-first`：32 passed（21.25秒）。
- 完整回歸 `uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-arrangement-all`：**101 passed（50.48秒）**。此為補上state.editable前的本輪完整版本；不是引用上一輪78項。
- 最後補上同一讀取快照的editable、外部結束後重讀呈現唯讀，以及0006升級前備份還原新目標後，針對受影響範圍 `uv run --locked pytest -q tests/test_arrangements.py tests/test_public_registration.py -p no:cacheprovider --basetemp .test-tmp-arrangement-final`：**39 passed（23.98秒）**。兩輪皆僅2項既有上游棄用警告，沒有形式重跑未變測試。
- 涵蓋optional原因／原原因規則、無GET隱性baseline寫入、直接level先ensure、並行init只一次、初次level/audit失敗連baseline回滾、版本與保存audit任一步失敗整體回滾、同名／取消重報／候補遞補／更名、snapshot不可變與真actor、跨場404／權限／CSRF／終態限制。完整token過期涵蓋level／取消／遞補／重報／姓名註記／比賽版本／另存；同key並行只一版、不同key並行保存一成一409、save/level並行符合完整序列化切點、舊save重送回原版不倒退latest。GET在讀取途中另一connection寫入level／version時仍回同一讀取快照。
- 0002／0005／**0006→0007**合成升級保留原所有表原欄位，包含原會員、快照、已改當次級數、version、順位及既有audit。新versions為空，不補造歷史；Alembic check無差異。升級前0006備份Restore新target保留原內容／revision；升級後backup／restore皆integrity=ok、FK=0。故意invalid FK使migration失敗時，DDL及revision回滾。這是SQLite／程式層證據，尚未進行新image/volume部署回退演練。

前端與瀏覽器證據：

- `npm run build -- --outDir ../frontend/dist-arrangement` 通過，包含tsc型別檢查。沒有依賴變更。`git diff --check`通過。
- 全程使用 `FUCHENG_E2E_DATABASE_URL=sqlite:///data/arrangement-e2e.db`、`FUCHENG_E2E_PORT=8040`、`FUCHENG_E2E_STATIC_DIR=frontend/dist-arrangement`、`PYTHONUTF8=1`，單worker；desktop1440×900、mobile390×844、isMobile／hasTouch。
- 新功能首輪 `npm run test:e2e -- --grep '緊湊八十人|大存未知|免原因移動|儲存後讀回' --output test-results/arrangement-first`：8 passed（24.9秒）。
- 加入同名／名單變更、真正另一admin帳號及最後editable修正後，首次全套 `npm run test:e2e -- --output test-results/arrangement-final`：17 passed／5 failed。新10項全過，失敗來自共用合成fixture：新同名資料撞原固定搜尋，以及大量新會員令原測試假設的預設100名候選不含指定會員。
- 新同名fixture改獨立名稱，原管理測試改為先搜尋指定會員；原功能及安全斷言全部保留。因影響共用DB，重跑整套 `npm run test:e2e -- --output test-results/arrangement-isolated-final`：**22 passed（57.2秒，新10＋既有12）**。不是首次全套全綠；8040測試server已退出。
- 最終22涵蓋：80人十欄密集版面、原大卡／快捷區／常駐統計不存在、搜尋圖示；真實trusted mouse與CDP touch長按拖曳、普通name橫捲不寫入、拖到邊緣自動橫捲可抵第10欄、Escape／touchCancel；5→4→6有兩audit淨5→6、回5消色；大存清色、再次異動、兩歷史各對前版、唯讀回看不寫DB、回目前不還原；名稱／顯示editor／真actor與可選note、同名／重報／遞補新增移出、更名後舊快照不改。
- 故障與時序涵蓋：level commit後503、commit前斷線原樣重試；其他卡仍可獨立操作；真409；PUT成功後GET掛起／失敗同卡仍鎖，重讀成功才解鎖；大存commit後503，**另一帳號再改級／另存／再改級**後以原key重試，仍回原receipt且current latest不倒退；大存在途切場晚回應不跳場；409大存保留tag／顯示editor／note，重讀核對後新token再存。

獨立人工預覽：[8039 排級數](http://127.0.0.1:8039/admin/competitions)，`data/arrangement-preview.db`／`frontend/dist-arrangement`。83位合成會員、3場、85報名，主場80人安排。`scripts/create_level_preview.py --variant arrangement`新建，不複製真資料；初始1→3示例先建立baseline再調整。來源及initial backup／restore均integrity=ok、FK=0、0007，見 `data/arrangement-preview-verification.json`。

`data/arrangement-preview-browser-verification.json`記錄最終8039桌面／手機80姓名格／10欄、搜尋1人、可到最遠欄、整表高度約458.5px、無頁面水平溢出、無pageErrors；desktop容器1372px、mobile335px／內容1100px。此次QA只有登入／選場／搜尋／歷史檢視，adminWrites=[]。截圖 `data/arrangement-preview-{desktop,mobile}-{table,search-far,history}.png`及E2E `compact-80.png`／`membership-history.png`已目視核對。orchestrate另以IAB只讀核對80人桌面及手機搜尋／橫捲。手機為Chromium觸控模擬與viewport證據，不替代球館實機與使用者操作驗收。

原6個DB的78表內容hash前後一致；原dist成品及r7～r10共439檔一致（<20MB用SHA256＋stat，大型archive僅size／mtime，不稱全檔hash）。見 `data/arrangement-protected-before.json`／`arrangement-protected-after.json`／`arrangement-protection-verification.json`；source allowlist已核對涵蓋新後端／0007／前端檔，未實際建置image。這是task4當時的歷史檢查：當時8037 PID57548及8448／8450 listener仍在，8032～8035未復活。當前原生／舊Docker狀態以上方收尾紀錄為準，task4當時未動Docker／ngrok／selfhost。

新8039最終listener **55404**、launcher **63776**；PID檔 `data/arrangement-preview.pid`／`arrangement-preview-launcher.pid`，日誌同前綴stdout／stderr，帳密僅 `data/arrangement-preview-admin.json`。本輪曾為載入editable修正只重啟新8039，已告知orchestrate，未停止其他服務。停止前比對netstat8039 PID及Python身分，再依README停該listener。8039留供驗收。

交付：主要目錄 `D:\projects\fucheng-players-system`，分支 `feat/competition-arrangement-versions`，起始及HEAD `0970af21abf4a8761a898f06d8b4d34da8a7d341`。此為task4當時交付：無新增worktree，成果未提交／merge／push，當時尚無新版公開入口。其後task5已交付頁首所列原生公開合成入口；舊Docker由owner停止且維持hold。後續部署task須以新source manifest建新image，明確停寫／備份／migration；回退是舊image＋0006 pre-update備份Restore到新target，保留0007更新後DB，禁止破壞性downgrade。自訂甲乙丙表頭／當次安排列印／編隊／隊長／循環賽未實作。

## 姓名卡片拖曳與逐次自動儲存（2026-09-20）

本輪 A+B 工程驗證完成，等待人工操作驗收。滑鼠拖曳、手機長按把手拖曳、點選／鍵盤移動共用逐次自動儲存；管理員先手填本次原因，每次移動固定當下原因、版本及 request_id。同一卡片完成後才能再移動，其他卡片獨立。已儲存撤回是有原因的新反向異動；結果不確定保留原操作重試，409 不替換版本或自動覆寫。會員長期級數、報名快照、當次級數與既有名單／列印語意保持獨立。

驗證使用 `FUCHENG_E2E_STATIC_DIR=frontend/dist-level-drag`、`FUCHENG_E2E_DATABASE_URL=sqlite:///data/level-drag-e2e.db`、`FUCHENG_E2E_PORT=8038`、`PYTHONUTF8=1`，單 worker。desktop 1440×900；mobile 390×844，isMobile／hasTouch 開啟。

- `npm run typecheck`、`npm run build -- --outDir ../frontend/dist-level-drag` 通過，未更新依賴。
- `npm run test:e2e -- --grep '姓名卡片|自動保存未知|真實409' --output test-results/level-drag-first`：6 passed（17.7 秒）。真實 Chromium 滑鼠／CDP touch 事件均 isTrusted，含長按前移動取消、touchCancel／Escape、卡片非把手原生捲動；自動儲存、連續移動、反向撤回與逐次原因／稽核；commit 後 503 且後續另改級再原 key 重試回最新紀錄；未 commit 斷線重試；另一卡片獨立；真實 409、切場保留原因／未完成操作、遲回應不跳場、較新版本不被舊回應取代、終態唯讀。
- `npm run test:e2e -- --grep-invert '姓名卡片|自動保存未知|真實409' --output test-results/level-drag-regression`：8 passed／4 failed。失敗是既有測試使用全頁 status 或模糊比賽按鈕姓名，與新卡片提示／把手撞名；已縮至通知 `.toast[role="status"]` 及 `.competition-item` 精確名稱，未刪除斷言或改業務行為。
- `npm run test:e2e -- --grep '刪除需確認|整批八十人' --output test-results/level-drag-regression-fixed`：80 人匯入桌面／手機 2 passed，刪除案例在還原後另一處同名定位 2 failed。補齊該檔比賽列表定位後，`npm run test:e2e -- --grep '刪除需確認' --output test-results/level-drag-deletion-final`：2 passed（6.7 秒）。合計 **18 個不同 E2E 通過（新 6＋原 12）**，不是首次全套全綠。
- 本輪未修改後端或 migration，未重跑先前 78 項 Python 測試；下節 78 passed 是既有 HTTP 部署階段證據。8038 測試服務已退出。

人工預覽 [8037 比賽管理](http://127.0.0.1:8037/admin/competitions) 使用新建 `data/level-drag-preview.db`／`frontend/dist-level-drag`。83 位合成會員、3 場比賽、85 筆報名，主場 80 正取／2 候補／1 取消；沒有複製真實資料。`scripts/create_level_preview.py --variant level-drag` 保留原預設 variant 與拒絕覆寫行為。初始備份 `backups/level-drag-preview-initial.db` 與還原 `data/level-drag-preview-restore-check.db` 均 integrity=ok、foreign_key_errors=0、revision=0006，見 `data/level-drag-preview-verification.json`。

80 人預覽另以真實 Chromium 驗證兩種尺寸：80 張姓名卡、十區、3 級篩選 9 張、篩選仍保留十個區域及十個快捷目的、區內可捲動、無水平溢位與 pageErrors。這次視覺 QA 沒有送出調級修改；結果 `data/level-drag-preview-browser-verification.json`，overview／board 截圖 `data/level-drag-preview-*-*.png` 已目視檢查。長姓名及未知結果提示由新 E2E 截圖核對。觸控是 Chromium 模擬，未取代球館實體手機操作驗收。

保護前後比對 `data/level-drag-protected-before.json`／`level-drag-protected-after.json`／`level-drag-protection-verification.json`：原 dist-public／dist-delete／dist-levels、r7／r8／r9 共 321 檔無差異（小於 20MB 以 SHA256＋大小／時間，大型 archive 僅大小／時間）；原 5 個 DB 的 63 張表內容 hash 一致。8448／8450 listener 持續存在；8032～8035 在本輪開始／完成檢查皆無 listener，沒有重啟或停止它們。既有 ngrok／Docker、真實資料及舊交付包未更新。

8037 實際 listener PID **57548**、啟動父程序 **54164**，分存 `data/level-drag-preview.pid`／`level-drag-preview-launcher.pid`；帳密只存 `data/level-drag-preview-admin.json`。停止時先比對 netstat 的 127.0.0.1:8037 PID 與 Get-Process Python 身分，才依 README 停止該 listener，不能拿其他預覽 PID 操作。8037 留供驗收。

交付位於主要目錄 `D:\projects\fucheng-players-system`，起始 main `289be6ca9692f2ed701a86f16a444b8e7151475c`，工作分支 `feat/competition-level-drag`；無新 worktree，變更未提交，未 merge／push。task4 本機驗證後，task5 另依授權更新公開預覽，見下節；上段保護結果是 task4 換版前的歷史證據。大版本快照、版本名稱／備註、與上一保存版本的淨差異顏色、自訂標題與當次安排列印另待後續階段，並未以報名快照代替上一保存版本。

### r10 公開預覽更新與操作驗證

沿用 `https://30a1-140-116-158-107.ngrok-free.app/`／`fucheng-ngrok-preview-20260920`，只替換 app／backup。r10 `local/fucheng:snapshot-b7a6f33e2b8e4777` 由 allowlist 的 47 檔 build context 建置，三個新前端模組均在 manifest；Docker 內 typecheck／build 通過。完整 image、source、archive SHA256 見部署手冊。後端、schema、runtime 與 r9 文字一致；部分檔案只有 Git 換行正規化造成 bytes 不同，未作應用修正。

- 換版前正常手動備份，正常停止 app／backup 後再建立 checkpoint `manual-20260920T030501454562Z-2de5c494.db`，SHA256 `473c6316a7d826541ffa797d58d78ff0dd01f47a5a72566c1e1862af0dbc9db3`；integrity=ok、foreign_key_errors=0、revision=0006。原 image／env／checkpoint 保留，無 migration／reseed。換版前後 15 張資料表筆數與內容 hash 完全相同，3 會員／1 場／2 報名保留。
- 真實公開 **CUA IAB**：正常 TLS 登入、先填原因、滑鼠把手拖曳合成甲 3→6、自動儲存、重開仍為 6、歷史顯示操作者／時間／原因成功；沒有儲存按鈕介入、TLS bypass 或 ngrok skip header。390×844 手機尺寸實操點選 6→3，再使用已儲存撤回 3→6，反向紀錄存在，無水平溢位；最後登出。長按主路徑沿用上節 trusted CDP touch E2E，未在此次 IAB 重演長按或宣稱實體手機驗收。
- 驗收只新增三筆有原因的 `level` 稽核；合成甲當次級數最終 6、version +3、報名快照仍 3。所有會員欄位／級數、比賽、兩筆報名身分／餐食／快照／順位／狀態與既有稽核保留。登入相關表有預期 session／attempt 變動。
- 正常 TLS API：health 200、未登入管理 401、錯 Origin 403、缺 CSRF 403、偽造 forwarding 400、拒絕後合法 session 仍 200、登出 204；cookie 仍 Secure／HttpOnly／SameSite=Lax。
- 原本機 DB／dist／帳密指紋一致；r7～r9 原包完整 SHA256SUMS 驗證通過。換版後即時快照中其他容器 ID／StartedAt 全保持；收尾時發現三個 KaChing portable api／mcp-read-api／mcp 容器其後另有變化（03:05:27～03:05:42 UTC），本 task 未操作它們，未調查或回復外部工作。ngrok、8448／8450、selfhost 容器保持，8037 PID57548 保留。8032～8035 在此次起始就無 listener，沒有重啟。無新 worktree／Git 提交／推送／資源清理。

本次證據集中於 ignored `data/deployment-ngrok-r10-evidence-20260920/`：`updated.json`、`backup-stopped.json`、`data-preservation.json`、`source-package-verification.json`、`public-api-security.json`、`iab-evidence.json`／截圖與 AX 紀錄、`final.json`。既有 18 distinct E2E 與 78 backend 證據沿用，不形式重跑。公開工程操作驗收通過，使用者接受成果與球館實機驗收仍是獨立狀態。

## ngrok 公開 HTTPS 合成預覽（2026-09-20，另行授權）

URL `https://30a1-140-116-158-107.ngrok-free.app/`。使用全新 `fucheng-ngrok-preview-20260920` project/data/backups、精確HTTPS origin與ngrok trusted peer，復用r9 image（沒有程式/image變更，也未更新舊交付包）。local-http模式未接Tunnel；既有8032～8035、8448、8450保持運作。只初始化3位合成會員與1個2099年合成場次。

- 正常TLS外部HTTP client驗首頁200、health200、Secure/HttpOnly/SameSite=Lax、登入及登出；Origin403、CSRF403、未登入管理401、偽造forwarding400。原負向測試一度預期代理會清洗偽造header後200，實際安全拒絕400，已更正測試期望，未放寬應用防護或重複seed。來源 `public-api-evidence.json`。
- app內網錯Host400、不受信peer偽造proxy400；公開HTTP307轉同域HTTPS，`host-peer-evidence.json`。未修改已過78項測試的程式，所以沿用既有全套結果，未為形式重跑。
- 真實CUA IAB首頁、登入、儲存合成會員辨識註記、登出通過；`iab-evidence.json`、`iab-admin.png`、`iab-member-saved.png`、`iab-logout.txt`。orchestrate首訪經ngrok Visit Site提示後成功，main亦看到合成賽事；沒有TLS警告繞過或skip header。
- 本次證據、private env/token與合成帳密均位於ignored `data/deployment-ngrok-evidence-20260920/`；總索引`ngrok-final.json`。Token/密碼未輸出、未入套件、未更改原ngrok設定。準確停止與存續条件見部署手冊。工程可訪問性通過，仍不宣稱使用者已接受成果、正式資料部署或球館實機驗收。

## 本機 HTTP 合成預覽（2026-09-20，另行授權）

r9 `data/deployment-release-20260920-r9/` 加入明確 opt-in、獨立 project/volume/cookie 的本機 HTTP 預覽。app `local/fucheng:snapshot-1076c3922cbd1465`，image ID `sha256:387861452a77d4e34c66f9ba6c7e6d30136cd3779076ee4c01b86992afe39858`，source SHA256 `1076c3922cbd1465441071ed2da39be500f41f673a322bf9858fc18e41d74c00`，image archive SHA256 `da919750dee95e164b4e678c05b8d171617fde1eac8aa8d4df6cc1e2f637ba38`。r7/r8原交付保留；8448沿用r7/r8映像未重建，HTTPS工程證據不冒充IAB憑證通過。

- `uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-http-all`：78 passed，2項既有上游warnings。包括HTTP非法設定13組fail-closed、HTTP Host/Origin/CSRF/管理session與cookie名稱、原HTTPS Secure cookie及代理語義回歸。前端未變，build重用已驗成品cache。
- 新HTTP容器由空白volume初始化，3個合成會員／1個合成場次；禁止復用未標記庫、HTTP restore/import/migrate、HTTPS啟用HTTP標記庫。首次internal-only bridge雖配置port卻不發布host listener，已改獨立普通bridge、雙loopback發布；沒有Tunnel服務，拒forwarding headers。此網路不提供出站隔離，不得宣稱具有此能力。
- 真正 **CUA Codex IAB** 訪問 `http://localhost:8450/`：首頁、管理登入、儲存會員辨識註記、比賽管理與登出均成功，沒有ignoreHTTPSErrors或略過TLS警告。證據 `data/deployment-http-evidence-20260920/iab-evidence.json` 與 `iab-*.png`／首頁及登出AX紀錄。另由orchestrate自己的IAB核對首頁可用。
- API共用cookie jar登入HTTP/HTTPS各自合成帳號，雙session共存；HTTP登出後HTTPS仍200，雙向替換token皆401，HTTPS cookie維持Secure、HTTP專用cookie無Secure。證據 `cookie-isolation.json`，此項是API測試context，並非瀏覽器跨站jar實測。
- 帳密僅本機ignored `data/deployment-http-evidence-20260920/synthetic-admin.json`；停止方式、來源與資源清單見該目錄 `http-final.json` 及部署手冊。保留本機預覽供人檢視，仍待人類接受；沒有公網、正式資料或編隊/循環賽功能授權。

## Windows Docker可搬移套件（本機工程驗證，待階段核對／人工驗收）

正式拓撲為單一app image（React成品＋FastAPI）與SQLite named volume，備份／維護复用app image；Cloudflare named tunnel直連app，nginx只供本機HTTPS測試。沒有啟動公開Tunnel、球館遠端、真實資料遷移或正式上線。

最終套件：`data/deployment-release-20260920-r8/`。app tag `local/fucheng:snapshot-16baa6405474f861`，image ID `sha256:9c9debe226d721af860a96a11de90eb0128f54f9d9965f69c28712773e665d3d`，source manifest SHA256 `16baa6405474f861217fc92668d91bb5ae0b7fa3556154d9e807fcfec51647bb`。離線 `fucheng-images.tar` SHA256 `5d775963ee9aecc9c001cf9328b99cf3317733b8bcc27dd7c63809125d2f6580`。這是含未提交級數與部署變更的working-tree snapshot；HEAD `1ba5c68809866150f9d4e8a5c5e38c393dec2aca`只表示起始提交，不能代表全部image來源。r8只更新雙loopback Compose與手冊，沿用r7相同image、source與archive。r7已按原交付hash還原保留；r1～r6為過程材料，不能交付替代r8。

### 已完成證據

- 人工預覽後續修正：原Compose只綁IPv4，實测IPv6連線拒絕；現僅為https-test加上`[::1]`映射，兩種loopback路徑均200，IP網址仍400、錯誤Origin仍403。只重建nginx測試容器，app image／來源manifest／image archive未變，套件Compose、手冊與SHA256SUMS已刷新。**Codex IAB在本task修正前後均回ERR_CERT_AUTHORITY_INVALID，未進入頁面或登入；不能把main先前ERR_CONNECTION_REFUSED全部歸因於IPv6，也不能把自動Chromium測試當成人工IAB成功。** 自簽憑證例外須由人員處理，未安裝信任、未關閉驗證或放寬Host/Origin。證據`preview-loopback-20260920.json`；此項人工驗收仍未通過。
- `uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-deploy-all`：**63 passed**，2則既有上游warning；包含4項部署Origin/Host/Secure cookie及Cloudflare/ngrok受信peer/IP語義測試。後續只修改容器runtime／helpers，未重跑未變的應用測試。`npm --prefix frontend audit --audit-level=high`：0 vulnerabilities。Docker多階段build內npm ci/typecheck/build及uv locked依賴安裝成功，不覆寫本機dist。
- 真實build context export精確比對44個允許檔案；source ZIP與凍結build-context逐檔一致，image內manifest與label一致；裸image沒有DB、Node runtime或會員資料，UID10001。app無host port、唯讀rootfs；實際連線pragma為FK=1、busy_timeout=10000、journal=wal、synchronous=2(FULL)。外部非受信容器偽造Forwarded/XFF/XFP/CF-Connecting-IP均400。
- 本機HTTPS Chromium桌面1440×1000／手機390×844：登入、Secure/HttpOnly/SameSite cookie、公開首頁／分級／選名報名、管理當次級數3→7且快照仍3、Origin/Host/CSRF拒絕、登出與無水平溢位。最終r7獨立還原庫結果 `data/deployment-evidence-20260919/https-browser-results-8448.json`；截圖 `https-8448-*.png`。屬手機viewport測試，未取代球館實體手機與外網驗收。
- fresh init／無預設密碼CLI建立管理員／未初始化拒啟動／重複Init拒絕／第二writer与服務中migration拒絕／force-recreate持久化均通過。0005舊程式fixture→0006→舊image＋0005 pre-update備份回退通過；正取／候補／取消快照逐列回填，更新後寫入保留於舊DB。舊image是**HEAD 0005程式與前端＋本輪deployment guard**的合成回退fixture，並非曾正式部署的版本。證據 `drill-upgrade-1789816812824004800.json`、`drill-persistence-1789816762625716400.json`。
- 新runtime另補受影響恢復測試：migration失敗留下maintenance且拒啟動；損毀／缺失active DB由有效備份還原至新檔、保留故障檔與操作證據；interrupted init獨立volume救援。完整命令及結果見最新 `drill-recovery-*.json`，最終索引見 `deployment-final.json`。一次重跑曾因測試fixture重用舊volume而被guard正確拒絕，修正測試volume唯一名稱後通過，不列為產品成功證據。
- 備份失敗stderr/backup-health可見、手動checkpoint不受自動retention刪除。**長時短週期測試發現舊版備份留下3760組partial-WAL/SHM，先前僅檢查DB數量不足以證明保留政策。** r7將BackupAPI目的副本轉為DELETE journal，來源live DB仍WAL；Legacy WAL匯入先hash再複製可寫暫存驗證，不用immutable或掛可寫來源；Restore在鎖內驗metadata/hash並回收已匯入備份空白sidecars，完成後來源bytes不變。8次備份後只有2個scheduled DB／metadata、0個partial/importing sidecars；舊累積檔保留盤點，不廣泛刪除。證據 `backup-standalone-retention.json` 與 `deployment-final.json`。
- 完整可攜包另複製到 `data/deployment-portable-test-20260920-r7/`，**僅用Windows內建PowerShell5.1＋Docker**執行load（逐檔SHA及全部image ID）、Legacy WAL備份Import、新volume Restore（不先Init）、StartTest、Status、ExportBackups；重複匯入、既有匯出目錄、錯誤hash、服務中Migrate均拒絕。腳本補顯式Utility module載入、在body解析套件路徑，以消除PS5.1與PS7差異。精確命令／exit/stdout/stderr：`portable-final-operations.json`。
- 新版ExportBackups封存持backup.lock，Windows驗tar及解開後每檔hash；匯出的單檔備份再經ImportBackup還原到第二個全新project/volume，所有資料表筆數及內容hash相同：`portable-roundtrip.json`。這是合成、同主機的離機交接流程演練，不聲稱已擁有真實異地備份。
- Cloudflare image實查2026.9.1，ngrok3.39.8且config check通過；兩者均只在network none執行版本／配置命令，未啟動Tunnel。官方來源與未驗項見部署手冊。

### 保護與交付狀態

主要目錄 `D:\projects\fucheng-players-system`、分支 `feat/competition-level-management`、HEAD未變，無新worktree、未commit/merge/push/registry/正式部署。起始26個級數差異完整保留；原前端與級數業務碼未回復。部署新增Docker/Compose/runtime/PowerShell helpers、封裝與演練腳本、proxy邊界與測試，並更新既有文件；src/app.py僅增加可選部署middleware，config新增對應環境欄位。起始manifest／diff存 `baseline-files.json`／`baseline.patch`；本輪檔案範圍由 `preservation-final.json`及最終索引列明。

原各DB全表hash／筆數、dist-public/dist-delete/dist-levels及帳密檔hash前後一致：`protected-before.json`、`protected-after.json`。原8032～8035及共用selfhost-models／KaChing服務沒有被停止或修改。所有Docker演練只碰fucheng專屬合成project／volume；保留容器、volumes、網路及過程包清單與停止方式見 `deployment-final.json`，沒有prune／down -v或未授權清理。

仍待：orchestrate階段核對與人類接受、球館虛擬化/WSL/Docker/電源/重啟實查、無人登入恢復責任、domain/account及真正named tunnel、外網手機、唯一正式資料來源與搬移授權、真正離機備份保管。以上不阻止本機套件完成，但不能描述為正式上線完成。

## 當次比賽級數與人員管理（2026-09-19）

第一階段工程驗收完成：會員長期級數、報名快照及當次比賽級數獨立；管理員只調正取且原因必填，支援姓名／註記搜尋、當次級數篩選、升冪分區、固定全場與篩選人數、取消歷史與候補分開。沒有編隊、隊長、A/B 分組、抽籤、對戰或公開參賽名單功能。

- 後端原有全套：`uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-levels`，45 passed（24.48 秒）。新增案例及相關 public／migration 最終驗證：`uv run --locked pytest -q tests/test_public_registration.py tests/test_competition_levels.py -p no:cacheprovider --basetemp .test-tmp-level-final`，28 passed（15.98 秒）。兩者部分重疊，共 **59 個不同後端案例有通過證據**；`--collect-only` 確認目前共 59 項，不把它說成一次全套 59 passed。2 項既有上游 deprecation warning 保留，無依賴變更。
- 新案例驗證管理／公開／批次新列初始化、同會員別場不變、會員與快照不變、重讀歷史含 actor／時間／前後級數／原因；非法級數／多餘欄位／空原因／未登入／缺 CSRF／舊版本拒絕；同級數回 422 且沒有空白調級稽核。相同 key 重送不增版本，跨 actor／payload key 重用拒絕。
- 故障注入在 registration_audits INSERT 觸發 ABORT，報名當次級數、version、操作者／時間及稽核全部回滾。並行兩筆調級、調級與取消都是一筆成功、一筆 409。已取消列不可修改；重報新列用新會員快照初始化；候補遞補保留原列級數。closed／實際過截止仍允調級，deleted／ended／cancelled／draft 阻擋；刪除還原不重設級數。
- 最後將刪除／還原案例強化為「先人工調級，再經真正 delete／restore API」確認當次級數及整筆報名保留；只重驗 `tests/test_competition_levels.py -k lifecycle --basetemp .test-tmp-level-lifecycle`，6 passed（3.54 秒），沒有因此重跑其他未變案例。
- Migration **0006_competition_level**：合成 0002 及 0005 升級、全原表原欄位逐欄保留、候補序、取消紀錄、公開 actor、已刪除狀態皆通過；故意令會員目前級數不同於快照，確認回填來自快照。備份還原、integrity_check／foreign_key_check、Alembic check 及兩個起始版本的故障 DDL／revision rollback 通過。原會員及正式庫未套用。
- `npm run typecheck` 通過；最終 `npm run build -- --outDir ../frontend/dist-levels` 通過（JS gzip 74.18 kB）。Vite 暫存與 Playwright cache／結果目錄的 sandbox 權限已依授權建置／測試範圍取得，未改套件或覆寫既有成品。
- E2E 全程使用 **8036／data/levels-e2e.db／frontend/dist-levels**、單 worker、desktop 1440×900 與 mobile 390×844。首次全套 12 passed／2 個既有刪除測試因 role=status 多個元素而失敗；定位縮至 `.toast[role="status"]` 後 `--grep '刪除需確認' --output test-results/levels-deletion` 為 2 passed（6.7 秒）。新增表單聚焦與歷史失敗情境後，受影響的 `--grep '當次級數安排' --output test-results/levels-final` 再次 2 passed（7.8 秒）。共 **14 個不同 E2E 案例通過**，不稱首次全套全綠。
- 新安排瀏覽器案例包含保存重開、分區與搜尋統計、實際另一筆 API 競寫造成 409（不是只 mock 409）、保留輸入及原 version、切換場次再返回保留草稿、503 模擬故障後以原 key 重試、歷史前後值、讀錯場歷史防護，以及手機無水平溢位。503 為前端失敗情境，資料庫交易故障由後端 trigger 測試驗證。桌面／手機截圖已目視檢查：`frontend/test-results/levels-final/competition-levels-*/levels-failed-input.png` 及 `levels-saved.png`。

### 可操作合成預覽與原環境保護

[8035 比賽管理](http://127.0.0.1:8035/admin/competitions) 使用全新合成 `data/levels-preview.db`，83 位合成會員、3 場比賽、共 85 筆報名。其中主場 80 正取／2 候補／1 取消；另一場用相同會員驗證級數獨立。沒有複製真實資料庫。初始 Backup API 備份 `backups/levels-preview-initial.db`、還原 `data/levels-preview-restore-check.db`，檢查報告 `data/levels-preview-verification.json` 的來源／還原皆 integrity=ok、FK errors=0、0006。

在這個 80 人預覽另外啟動真實 Chromium 檢查 desktop 1440×900／mobile 390×844：全場正取 80、3 級篩選 9、無水平溢位、調級表單可聚焦及輸入；未送出新的報名／調級修改。結果 `data/levels-preview-browser-verification.json`，兩平台 overview／group／form PNG 在 `data/levels-preview-*-*.png`，均已目視檢查。這是模擬手機 viewport，未取代球館實機驗收。

實際 8035 listener PID **20008**，啟動父程序 **53140**；分別保存在 levels-preview.pid／levels-preview-launcher.pid。帳密只存 `data/levels-preview-admin.json`，未輸出。啟停及重建防覆寫行為見 README。8036 測試服務已退出，8035 依預覽交付保留。

受保護的 8032／8033／8034 listener PID 仍為 59376／35904／59116。運作中兩份預覽 DB 主檔直接 hash 被 Windows 檔鎖阻止，改用 read-only SQLite 各表完整列指紋前後比對：club-preview.db（0004）與 club-delete-preview.db（0005）全表一致，證據 `data/levels-protected-db-before.json`／`after.json`。原 fucheng.db／competition-case.db 與 dist-public／dist-delete 成品共 8 檔 SHA-256 一致，證據 `data/levels-protected-before.json`／`after.json`。沒有停止既有服務或升級其庫。

交付位於主要目錄 `D:\projects\fucheng-players-system`，分支 `feat/competition-level-management`，起點／HEAD 仍為 `1ba5c68809866150f9d4e8a5c5e38c393dec2aca`，所有本階段變更未提交；未建立 worktree、未 commit／merge／push／deploy。正式資料遷移、Linux／HTTPS／球館實機，以及第二階段人工編隊與隊長管理均未執行。

## 9/20 已確認 80 人名單匯入（2026-09-18）

依使用者確認，9/20 為 2026 年、80 人全數正取、沒有候補且不開放額外報名。17 筆近似姓名、另外同名／弱候選由使用者確認；15 筆新會員姓名經 7 筆更正後，使用者明確同意依原圖欄號作為這 15 人的初始硬實力級數。既有會員仍沿用目前級數，不回寫來源欄號。黃安彬兩筆會員的資料及初始匯入歷史一致、皆未報名，本場沿用穩定排序第一筆，僅登記一次，兩筆原會員記錄均保留。

- 後端：`uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-roster-import`，**41 passed**（21.57 秒），2 則既有上游 warning。新案例包含全交易回滾、新會員與餐食快照、超額／版本／資料變更／同名／重複列拒絕、權限與 CSRF、批次重送、兩個並行請求匯入 80 人仍只有 80 報名及稽核。
- E2E：`cd frontend; npm run test:e2e`，**10 passed**（23.5 秒），皆在獨立 8031 合成庫。新增桌面／手機 80 人匯入後的實際瀏覽器名單、級數篩選、80 筆稽核與列印模式，原 8 個案例亦通過。應用程式前端未更改，沿用已建置成品。
- 已授權資料操作：只在 club-preview.db 執行管理員 API，65 位既有會員加 15 位新會員，共 80 正取、0 候補、0 空位；場次 closed。餐食 64 葷、2 素、14 未設定；其中原圖明確 1 位素食，另 1 位沿用既有會員預設，14 位新會員無餐食資料故不猜測。
- 預覽會員總數 342，327 筆原會員逐欄未改動；testing 場次及其報名／稽核逐欄與匯入前備份一致。原 fucheng.db、competition-case.db 雜湊在操作前後不變。完整姓名、ID、決策及結果只保留於 Git 忽略的 data/ 下。
- 匯入前 Backup API 備份：backups/club-before-confirmed-80-import-20260918.db；結果與備份路徑：data/club-tournament-0920-import-result.json；資料庫 integrity_check／foreign_key_check 通過。本輪不需 migration，仍為 0004_club_website。

自動核准機制拒絕重啟現有 8032，理由為早先「不要停止現有服務」限制；因此 8032 原程序保持運作，另在 8033 啟動新版 API 操作同一份預覽副本。8033 PID 記於 data/roster-import.pid，啟停及功能邊界見 README。原 8032 可直接讀到新名單，不需停止服務。此輪驗證當時尚未提交、未合併、未部署；後續 Git 整合授權見下節。

## 球館網站整合驗收（2026-09-18）

本輪已將首頁、公開分級、比賽入口與公告管理接成同一網站。依使用者最新授權，所有人可免登入查看啟用會員姓名／級數／辨識註記；公開 schema 移除餐食。下方 9/17「完整分級限管理員」描述為當時歷史邊界，現由本節取代。

- 後端完整測試初次為 36 passed／1 個新測試 helper 參數錯誤；修正 helper 後 `uv run --locked pytest -q tests/test_website.py -p no:cacheprovider --basetemp .test-tmp-website3` 為 3 passed。共 37 個不同案例已通過；既有 2 則上游 deprecation warning 保留。初次 migration revision 斷言亦已更新到 0004。
- `npm run typecheck`、`FUCHENG_BUILD_DIR=../frontend/dist-public npm run build` 通過。沒有新增依賴。
- `npm run test:e2e` 原 6 個桌面／手機管理與報名案例通過；新增 2 個首頁案例的級數 select 定位修正後，`npm run test:e2e -- --grep "首頁公告"` 2 passed（7.8 秒）。共 8 個不同 E2E 已通過，均使用 8031／public-e2e.db 合成資料。
- 新案例涵蓋公告草稿不公開、發布、置頂、下架、未授權／缺 CSRF 拒絕、空白內容及多餘欄位拒絕、idempotency 重送不重複、version conflict 保留輸入、公告與稽核失敗整筆回滾。公告文字中的 `<script>` 在瀏覽器僅當文字顯示。
- 首頁 → 免登入分級 → 搜尋同名／級數篩選 → 比賽報名 → 首頁導覽已由桌面與手機驗證；手機首頁無水平溢位，截圖已視覺檢視。比賽公開時程不含草稿，狀態 open 但時間已截止時顯示 closed，也不出現在可報名清單。

### 原會員副本與啟動成果

使用者已授權以原會員資料副本檢視新版。執行 `uv run --locked python scripts/create_club_preview.py`，從 `data/competition-case.db` 以 Backup API 建立 `data/club-preview.db`，升級 0002 → 0003 → **0004_club_website**。原 327 會員、2 管理員、1 比賽、649 會員稽核、1 比賽稽核與其他原表所有舊欄位逐一比對完全一致。原副本當時尚無比賽報名紀錄，不將其描述為已匯入 9/20 參賽名單。

遷移後 integrity_check／foreign_key_check、Alembic check、再次備份還原比對均通過。結果在 `data/club-preview-verification.json`；檢查完後僅新增預覽管理員及兩則事實性使用說明公告，不新增虛構比賽或真實會員報名。`data/fucheng.db` 與 `data/competition-case.db` 主檔雜湊在操作前後一致；未對原庫遷移或回寫。

8032 已由舊合成預覽切換到這個副本，首頁 HTTP 200，公開 API 現有 327 會員、2 公告與 1 已公開比賽；公開會員欄位恰為 id／name／distinguishing_note／level。管理帳密檔為 `data/club-preview-admin.json`，背景程序 PID 檔為 `data/club-preview.pid`。舊合成資料保留。啟停、備份路徑與限制見 README。

原工作目錄／分支不變，仍為 `feat/member-self-registration`，HEAD 為 2679bf4，尚未 commit、合回 main、推送或正式部署。沒有額外 worktree。尚未完成真實手機現場試用、外網 HTTPS 與 Linux/systemd 部署；自動開放報名時間與公告預約發布不在本輪，預告可由公告提供。

## 第三階段歷史驗收：免登入選名報名

2026-09-17 依使用者確認改為公告欄式選名報名，會員帳號與自助取消方案已撤下。工作目錄 `D:\projects\fucheng-players-system`，分支 `feat/member-self-registration`，該次驗證的起始／當時 HEAD 為 `2679bf4ff61a06528bc11c604a2f4fd219491bdf`。當時變更未提交，沒有額外 worktree、合併、推送或正式部署。

- 後端：`uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-public2`，**34 passed**（17.02 秒），僅 2 則既有上游 deprecation warning。
- 前端：`npm run typecheck`、設定 `FUCHENG_BUILD_DIR=../frontend/dist-public` 後 `npm run build` 通過；依賴／lockfile 未變。
- 瀏覽器：`npm run test:e2e`，**6 passed**（20 秒），桌面 1440×900／手機 390×844，各涵蓋會員管理、比賽管理與免登入報名。
- Migration：`0003_public_registration`。合成第二階段資料 upgrade、逐欄保留、Backup API 備份及還原、integrity_check／foreign_key_check 通過；只對新合成預覽執行 `alembic check`，No new upgrade operations detected。

餐食選項調整：公開報名僅顯示葷食／素食，預設葷食，API 拒絕 unset；歷史資料仍保留未設定。調整後執行 `uv run --locked pytest -q tests/test_public_registration.py -p no:cacheprovider --basetemp .test-tmp-public-meals`（14 passed）、`npm run build` 與 `npm run test:e2e -- --grep "免登入搜尋"`（桌面／手機共 2 passed）。瀏覽器確認只有兩個選項、預設葷食，改選素食後失敗重送仍保留選擇。

### 核心證據

1. 候選搜尋需要姓名，返回最多 20 筆 id／name／distinguishing_note；同名東區／西區可精確選擇，不公開級數、預設餐食或名單。空查詢／LIKE wildcard 不可取得全表，停用會員不列出。
2. 沒有會員帳號 API／資料表，也沒有匿名取消、更正、遞補或歷史 API。匿名上下文不能取得管理權限。CSRF 缺少／跨來源拒絕，額外 status／sequence／level／reason 欄位拒絕。
3. 5 位不同會員同時報容量 3：3 正取、2 候補。管理員取消正取後 2 正取／2 候補／1 空位；3 位新會員同時報名皆候補，原取消者重新報名排最後。管理員確認第一候補後為 3 正取、5 候補、0 空位，餐食統計正確。
4. 同會員同時提交：相同 key 回同筆、不新增第二筆稽核；不同 key 一次成功、一次 409。跨 visit 或內容重用 key 拒絕，換訪客用新 key 重報也拒絕。
5. 草稿／截止／結束／取消及仍為 open 但已到截止時間均禁止新增；會員停用不取消既有報名，餐食／硬實力快照不被後續預設資料修改回寫。
6. 人工注入稽核 trigger 失敗後，報名、next_sequence、稽核完整回滾。CHECK 拒絕 public actor 同時帶 admin_id。過期 visit 在取得寫鎖後再次驗證回 401；速率限制、Secure／HttpOnly／SameSite cookie 測試通過。
7. 升級合成庫含 5 會員、1 管理員、1 比賽、2 正取／2 候補／1 取消及各類舊稽核，所有舊欄位與候補序保留，備份還原一致。故意注入舊外鍵錯誤，migration 失敗後 DDL 與 revision 回到第二階段。

### 真正瀏覽器及預覽

桌面與手機各執行：管理員建立比賽與先加入正取／候補；全新匿名瀏覽器直接開首頁，搜尋同名會員、選西區、選素食、確認報名成為候補；管理員取消後再匿名重報，管理名單確認順位由 3 變 4。失敗請求保留姓名與餐食，成功頁沒有取消操作，管理員可辨識免登入來源並執行取消及查看稽核。前兩階段管理流程與列印也通過。

截圖在 `frontend/test-results`，包括 `public-confirm.png`、`public-receipt.png`、`public-admin-audit.png`。已檢視手機確認與結果畫面，調整標題與連結對比，手機結果頁無水平溢位。測試使用 `data/public-e2e.db`、8031、`frontend/dist-public`。

預覽 [http://127.0.0.1:8032/](http://127.0.0.1:8032/) 已切換免登入版，使用全新 `data/public-preview.db`。選合成賽、搜尋「王」或「陳」可操作；只有管理員帳密在本機 `data/public-preview-admin.json`。原 8012、原會員庫及 9/20 案例庫保留，沒有正式資料操作。舊帳號版合成庫保留但不再使用；其未提交原始碼封存在 `backups/account-flow-source-before-public-registration.zip`，不含帳密或資料庫。啟停見 README。

### 限制及未執行項目

選名登記不驗證本人，可能代報；CSRF／速率限制／唯一約束只提供技術防護，不代表本人確認。取消、更正與遞補由管理員處理。搜尋會公開必要姓名與辨識註記，並非完整會員資料對外公開。正式 DB 升級、Linux/systemd、實際 HTTPS、球館現場與長輩可用性尚未驗收，步驟見 deployment.md。

## 第一、二階段歷史證據

- 基準：Windows x86-64 開發機、一般 CPython 3.14.6、uv 0.12.15、Node.js 24.11.0、npm 11.6.1。
- `uv sync --locked` 可建立專案 `.venv`；FastAPI 0.141.1、SQLAlchemy 2.0.53、Alembic 1.20.0、Pydantic 2.13.5 可安裝與匯入。
- 後端自動測試涵蓋：空資料庫 Alembic 遷移、SQLite pragma／級數／會費期間約束、未登入禁止管理、登入／登出失效、CSRF、公開敏感欄位排除、重名、改名、停用／恢復、修改歷史、交易失敗、過期版本衝突、備份還原。
- 前端 `npm audit --audit-level=high`、TypeScript 檢查與 Vite 正式建置通過。
- Playwright 以桌面 1440×900 及手機 390×844 執行：登入、新增、修改、公開名單、搜尋、級數篩選、列印模式、手機無水平溢位。
- 備份以 SQLite Backup API 建立，還原至另一個乾淨資料庫並核對內容與 `integrity_check=ok`。

## 第二階段已驗證

- 後端完整測試 `20 passed`。新增情境包含：名額 3／報名 5、正取取消不自動遞補、新報名不搶候補空位、第一有效候補確認、候補取消與重新排尾、增加／非法降低名額、截止後理由、終態唯讀、會員停用保留報名、當次餐食與硬實力快照、權限、CSRF、版本衝突、idempotency 重送、兩人競爭最後名額、兩管理員同時遞補及稽核失敗整筆回滾。
- Alembic 測試先建立 `0001_member_management` 的合成會員／帳號／稽核資料，再升級 `0002_competition_registration`；舊資料保留且新表初始為空。
- 前端 `npm audit --audit-level=high` 為 0 個已知漏洞；TypeScript 檢查與 Vite production build 通過。成品 JavaScript gzip 66.53 kB、CSS gzip 3.52 kB。
- Playwright 在 desktop 1440×900 與 mobile 390×844 執行會員及比賽流程，共 `4 passed`：建立比賽、加入正取／候補、取消不自動遞補、人工遞補、餐食摘要、全場與篩選摘要分離、衝突時保留輸入、管理名單列印與手機無水平溢位。
- 真實資料的只讀案例流程：從運作中資料庫使用 SQLite Backup API 建立 `backups/competition-phase2-source-20260916.db`，還原為 `data/competition-case.db` 後才升級。升級前後及再次備份還原皆 `integrity_check=ok`，會員 327、管理員 2、會員稽核 649 筆完全相同；原 `data/fucheng.db` 未遷移、未寫入。
- 9/20 圖片逐格確認為 8 欄 × 10 個有姓名的格子，共 80 人，不是用空表格容量推算。精確姓名對照結果：44 筆單一啟用匹配、29 筆無精確匹配、1 筆同名多候選、6 筆辨識待確認；沒有模糊比對或自動新增會員。圖片只有 1 筆明確素食標記，其餘已匹配者的提案餐食來源標為會員預設。

案例尚未建立正式比賽或報名列，因為年份、正式名額上限、報名截止時間仍待使用者確認，而且圖片順序不是報名先後；在這些資料不足時建立候補會捏造順位。來源轉錄與含會員 ID 的對照報告只在 Git 忽略的 `data/`，來源圖片仍在使用者指定的下載目錄。

## Python 3.15 調查

2026-09-16 時 Python 3.15 正式版尚未發布，官方時程為 2026-10-01；當下是 rc2。實測 `uv 0.12.15` 的下載清單雖顯示 rc2，但指定 `3.15.0rc2` 回報 `No download found`，指定或重裝 `3.15` 反而安裝 3.15.0b2，且首次解算帶入 Pydantic 2.14.0b2。這個預發布組合不作為第一版正式基準，因此採目前可安裝的穩定 CPython 3.14.6 與 Pydantic 2.13.5。

Python 3.15 正式版發布後，應更新 `.python-version` 與 `requires-python`，刪除並依 lockfile 重建獨立 `.venv`，重新執行匯入、Alembic、API、資料庫、完整測試與負載測試；未完成前不可宣稱 3.15 已支援。

## 尚未驗證與現場驗收

- 尚未在 Linux systemd 實機執行；本次 Windows 主機沒有可用的 Linux 執行環境（WSL 發行版列舉亦遭主機拒絕）。目前只有 service／timer 範本、強化設定與操作文件。部署主機需執行 `systemd-analyze verify`、啟停、重啟後健康檢查與權限測試。
- 尚未建立 Cloudflare Tunnel、網域、外部帳號或公開部署。
- 尚未在 2 GB 雙核心舊筆電、20 GB 實際磁碟或球館 Wi-Fi 驗收。開發機負載結果只能證明此程式與測試條件，不能外推到目標硬體。
- 尚未由真實管理員與長輩使用者進行現場可用性驗收。本機已有經使用者授權匯入的真實初始名單，但自動測試、負載測試與列印驗證仍只使用合成資料；授權匯入不等於現場可用性驗收。
- 正式上線前要以去識別或經授權的資料演練遷移、備份、還原、帳號復原、HTTPS cookie 與失敗回復。

## 第一版既有結果

- 後端：鎖定環境重建後為 `15 passed`；另有 FastAPI／Starlette 測試客戶端的上游 deprecation warning 2 則，沒有測試失敗。測試涵蓋一次性 CSV 匯入、重名、交易內稽核、防止重複匯入、未設定葷素的具名管理員回填，以及備份／還原危險路徑拒絕。
- 前端：`npm ci`、型別檢查與 Vite 7.3.6 production build 通過；成品 JavaScript gzip 63.31 kB、CSS gzip 2.66 kB；npm audit 為 0 個已知漏洞。
- 瀏覽器：Playwright desktop + mobile `2 passed`；包含衝突提示、輸入保留、多級對照、390×844 手機無水平溢位及長姓名不裁切。列印另以 327 筆合成資料（各級筆數同目前名單）驗證 11 欄、42 列，產出的 PDF 為單頁 A4 橫式，Poppler 重新渲染確認標題、表頭、內容與頁面邊界無裁切。
- 備份還原：除自動測試外，另以 E2E 合成資料庫執行 CLI 一致性備份並還原到新的乾淨目的地；來源與還原檔皆為 `integrity_check=ok`，會員筆數相同。
- 混合負載：單一 Uvicorn worker，100 使用者在 10 秒內逐步到站、每次瀏覽停頓 0.8～2.5 秒、每 5 秒一筆管理寫入；62.3 秒共 3,421 requests，0 errors（0.0000%），p50 4.1 ms、p95 7.9 ms、p99 15.6 ms、max 33.3 ms；服務程序 RSS 89.6 MiB、CPU 5.75 秒。
- 上述負載在 Windows x86-64 開發機與合成小型資料集完成；不是 Linux systemd、2 GB 目標硬體或球館網路的驗收數字。

## 比賽刪除／還原驗證（2026-09-18）

- `uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-delete-all`：45 passed，2 項既有上游棄用警告。新增 4 項驗證覆蓋管理權限、CSRF、必須確認、版本衝突／重送、刪除與報名並行、刪除／還原稽核失敗整體回滾、公開入口隱藏、所有名單寫入阻擋，以及還原後餐食／級數／排序與報名稽核保持原狀。
- `cd frontend; npm run typecheck`、`npm run build -- --outDir ../frontend/dist-delete` 通過。
- `$env:FUCHENG_E2E_STATIC_DIR='frontend/dist-delete'; npm run test:e2e`：12 passed，desktop 1440×900、mobile 390×844。新情境實際透過瀏覽器建立比賽、查看確認名稱與人數、安全焦點、Escape／保留、確認刪除、已刪除唯讀名單、再次確認還原；既有會員、報名／候補、80 人匯入、公告與公開網站流程一併通過。截圖位於 frontend/test-results/competition-deletion-*/delete-confirmation.png 與 restored-roster.png，已目視檢查桌面／手機確認視窗。
- 初次 E2E 的新選單定位及共用帳號超過 10 次登入限制已修正：新情境使用另一個合成管理員，保留正式速率限制，再完整執行 12 項通過。
- 合成第二階段 schema 升級至 head 並備份還原的既有測試通過，保存會員、管理員、所有報名狀態及候補順序、舊稽核。獨立新版預覽亦逐欄核對原有 342 會員、2 場比賽、81 報名及其他表，升級後備份還原、integrity_check、foreign_key_check、Alembic check 均通過；來源庫雜湊未變。完整報告：data/club-delete-preview-verification.json。
- 原 8032／8033 與其成品、資料庫未改；沒有對真實場次做刪除測試。最新預覽為 8034／data/club-delete-preview.db，兩份預覽資料獨立。正式資料庫遷移與 Linux／HTTPS 部署、球館實機手機驗收仍未執行。

## Git 整合範圍（2026-09-18）

使用者於功能驗收後授權將目前全部更新提交、合併至 main 並推送 origin。此次範圍為首頁／公告、公開會員分級、免登入報名、已確認名單批次匯入、可還原的比賽刪除，以及相關遷移、測試與文件；不包含真實資料、資料庫、帳密、備份或建置成品。功能分支起點為 2679bf4，main 可快轉至相同已驗證程式；後續工作從整合後 main 接手。

整合沿用本頁最近記錄的 45 項後端與 12 項 E2E 通過結果，驗證後僅調整文件接手敘述及預覽腳本的 schema revision 回報。Git 發布不代表資料庫遷移或正式部署；8032／8033／8034 預覽程序及各自資料保持不變。


## 局部底色、復原與上方工具列驗證（2026-09-22）

Windows／CPython 3.14.6／Node 24.11.0／Playwright Chromium desktop 1440×900 與 mobile 390×844 觸控模擬；無實機／其他 OS／實體印表機驗收。前端沿用既有依賴，`npm --prefix frontend run build -- --outDir ../frontend/dist-grid-undo`（含 TypeScript）及 `git diff --check` 通過。實際新版成品在 `frontend/dist-grid-undo`，舊 root `dist-grid-interaction` 等目錄不覆寫。

後端：`uv run --locked pytest tests/test_grid_cell_shade.py tests/test_grid_undo.py tests/test_grid_interaction.py tests/test_arrangement_grid.py tests/test_arrangements.py -q -p no:cacheprovider --basetemp .test-tmp-grid-undo-regression` 為 **73 passed / 39.89s**。之後只新增 `test_insert_undo_restores_all_displaced_people_and_keeps_versions_monotonic`，以 `.test-tmp-grid-undo-insert` 單案 **1 passed / 0.78s**；生產碼未改，共 74 案證據，並非單次 74 passed。初輪兩個新測試 fixture 問題（預備調級已建基準、重用會員編號）已修正。

驗證包含 cell_shades strict 值／重複或孤立座標／最大範圍／合併閉包與反向選取／move、insert、delete 保格色／舊 bytes、no-op、保存歷史、CAS、auth、terminal、audit rollback；undo 連續、分支、server 前態拒不合法／名單不符、外部名單／會員／餐食／保存斷鏈、多選手跨級稽核回滾與重播、version/revision 單調、舊 receipt 與私有 metadata 不外洩。

E2E 均 single worker、8043、`FUCHENG_E2E_DATABASE_URL=sqlite:///data/grid-undo-e2e.db`、`FUCHENG_E2E_STATIC_DIR=frontend/dist-grid-undo`。於 frontend 執行 `npm run test:e2e -- competition-levels.spec.ts` 搭配下列 grep/output：

- `編輯工具：上方|編輯工具：文字外點` → 首跑文字 desktop/mobile 2 passed，工具列 2 fail 是舊 helper 點 disabled 取消選取及誤把手機捲動當布局位移；修 helper 後 `編輯工具：上方` → **2 passed / 8.8s**，證據 `test-results/grid-undo-toolbar`。
- `局部底色：|編輯工具：復原|表格互動：|拖曳修正|表格新版：` → **21 passed、1 failed**，證據 `test-results/grid-undo-integration`；失敗是舊標題斷言尋找已被保留的 disabled input 取代的 button。
- 修該斷言與 inline pending 不攔核對按鈕後，`表格新版：標題失敗|編輯工具：文字外點|編輯工具：復原` → **6 passed / 20.0s**，證據 `test-results/grid-undo-final-text`。其他已通過且不受修正影響的證據沿用，總計 26 個不同 desktop/mobile 案例有通過證據，不宣稱單次全 26 通過。

實際 PDF：`frontend/test-results/grid-undo-integration/competition-levels-局部底色：格位橘底合併歷史與實際PDF-desktop/local-default.pdf` 與 `local-background-off.pdf`。每次重新建立凍結 printJob 後呼叫 PDF，afterprint 清理正常；兩者各 1 頁，合成選手 000／001／002 各一次。Poppler 100dpi 渲染為 `data/grid-undo-pdf/*-1.png`，目視確認局部灰覆蓋排灰、文字／素標完整；237、217、196 三階灰像素分別 4902、3668、41808，default 與 background-off 全圖一致，詳 `data/grid-undo-pdf/verification.json`。本次文字待核對的小修不影響列印碼，重用同輪 PDF 證據。

上方工具列手機換行及右上 X／綠色素標圖片在 `frontend/test-results/grid-undo-toolbar/competition-levels-編輯工具：上方固定入口與卡片外點關閉-mobile/`；orchestrate/main 已檢視。工程完成不等於使用者已驗收或公開部署；所有資料合成，本轮未動公開資料、session、ngrok、A、8042 或 8044 服務。


## 表頭選取與等待恢復驗證（2026-09-22）

本輪僅 B worktree、合成資料，Windows／CPython 3.14.6／uv 0.12.15／Node 24.11.0／Playwright 1.63.0 Chromium desktop 1440×900、mobile 390×844 觸控模擬。固定表頭可單選、工具列改字／上色與雙擊編輯；header_shade 不改 body、level 或 stable ID，清色回到既有 column.shade。未知寫入逾時保留原 request_id/payload；已取得 receipt 後讀回逾時只重新 GET。所有安排請求的 20 秒上限涵蓋 fetch 與完整 response body。

根因證據：在保留的舊 frontend/dist-grid-undo 上，以合成 POST 真正提交後攔住回應並推進時鐘 21 秒，舊 UI 仍停 saving、沒有核對入口，單案預期失敗記於 frontend/test-results/grid-header-reproduce。這證實無等待上限的程式缺陷；公開使用者當次網路／代理／伺服器故障原因仍未知，不能把合成復現或 task5 的目前健康檢查當成該次原因證明。

後端命令 `uv run --locked pytest tests/test_grid_header.py tests/test_grid_cell_shade.py tests/test_grid_undo.py tests/test_arrangement_grid.py -q -p no:cacheprovider --basetemp .test-tmp-grid-header`：**63 passed / 28.17s**。包含 strict 值、清除／舊 bytes、body 與軸隔離、title／undo／保存歷史、權限、CSRF、CAS、重播、no-op、交易回滾與終止場次；無新 migration／依賴，schema 仍 0008。舊程式未必能保留新欄位，不承諾舊 app 無損回退。

瀏覽器均 single worker、8043、FUCHENG_E2E_DATABASE_URL=sqlite:///data/grid-header-e2e.db、FUCHENG_E2E_STATIC_DIR=frontend/dist-grid-header。在 frontend 執行 `npm run test:e2e -- competition-levels.spec.ts` 配合下列 grep/output：

- `表頭修正：上色回應遺失` → **2 passed / 9.1s**，test-results/grid-header-timeout。真實合成提交後回應遺失、unknown 鎖定、原 key/payload 重播不重複 revision、恢復後再次修改。
- `表頭修正：回應內容|表頭修正：單選|表格新版：|編輯工具：文字外點|編輯工具：復原|局部底色：選區|表格互動：中央` → **18 passed / 53.1s**，test-results/grid-header-integration。包括 body 讀取卡住、receipt 後 GET-only 恢復、初次 GET timeout、離線重試、表頭與 body 選取互斥、鍵盤／觸控、文字／色階、undo、歷史／列印及既有拖曳／文字回歸。
- readonly review 發現選中表頭後 body 右鍵未清掉 header selection，修正後 `表頭修正：單選|局部底色：選區` → **4 passed / 14.0s**，test-results/grid-header-final；實際工具列上色請求為 shade_cells，表頭保持不變。
- 手機單案視覺補驗發現窄畫面範圍按鈕依賴 pointer:coarse 且全域 hover 遮住表頭底色；test-results/grid-header-visual 的 1 failed 已以局部 CSS 修正。最終 `表頭修正：單選|編輯工具：上方` → **4 passed / 13.8s**，test-results/grid-header-visual-final。最新手機互動畫面為該目錄下 mobile/header-selected-toolbar-screen.png（完整路徑含 test 名稱）；header-mobile.png 是 print media，不作互動畫面證据。

上述 scoped runs 共 **22 個不同 desktop/mobile 案例有通過證據**，並非單次 22 passed。最後僅將未知結果提示改成「表格調整與保存」「重試不會重複執行同一次修改」，沒有匹配舊句的測試 locator。最終 `npm --prefix frontend run typecheck` 與 `npm --prefix frontend run build -- --outDir ../frontend/dist-grid-header` 通過；文案後未重跑 E2E，重用相同行為與 CSS 的 scoped 證據。

實際 PDF 取自 grid-header-visual-final 的 desktop/header-default.pdf 與 header-background-off.pdf。兩者各單頁、選手 000／001／002 各一次、表頭文字完整；Poppler 100dpi 渲染 1170×827，196 灰像素各 2451、兩圖完全一致，目視只有第一級表頭灰色，body 保持白色、素標與姓名完整。報告 data/grid-header-pdf/verification.json；最後恢復提示文案不影響列印碼。未驗證真實手機、其他 OS 或實體印表機，也不代表使用者已驗收。

最終來源／成品／文件測試指紋見 data/grid-header-delivery-identity.json；舊六組 static 逐檔與各自 identity 核對不變，先前局部色部分成品保留。本輪未操作公開服務、DB、admin、session、ngrok，未動 A／8042，未 commit／merge／push。凍結後由 task5 依 orchestrate 授權處理發布，工程驗證不等於已發布。


## 版本雙欄與選手單雙擊驗證（2026-09-22）

B feat/competition-arrangement-grid、HEAD/base 89cae09754eaefa4dba6c3dce308482526f33ff2 上未提交增量。Windows／CPython 3.14.6／uv 0.12.15／Node 24.11.0／Playwright 1.63.0 Chromium desktop 與 mobile 觸控模擬，single worker。獨立 FUCHENG_E2E_DATABASE_URL=sqlite:///data/grid-panels-e2e.db、FUCHENG_E2E_PORT=8043、FUCHENG_E2E_STATIC_DIR=frontend/dist-grid-panels。全部合成資料，使用者截圖只參考視覺，未導入姓名或資料。

命令 `npm --prefix frontend run test:e2e -- competition-levels.spec.ts --grep '雙欄選格：|拖曳修正|表格互動：中央|表格刪除：素食|編輯工具：上方|表格互動：歷次參考' --output=test-results/grid-panels-integration` 首輪 **15 passed、1 failed / 1.2m**。唯一失敗確實揭露手機取消選取後殘留 tap 候選，下一次單擊提早開詳情；修正姓名以外 pointerdown 清候選後，命令 grep `雙欄選格：單雙擊|拖曳修正|編輯工具：上方`、output test-results/grid-panels-click-final 得 **8 passed / 22.0s**。最後生產修正不改布局／版本／歷次參考，重用首輪相關通過證據，總計 **16 個不同案例有通過證據**，不是單次16passed。

覆蓋單擊只選格且零寫入、mouse 雙擊、真 touch tap×2、跨人與超時不視為雙 tap、Space 不捲頁／Enter 資訊、range 雙擊只延伸不折疊不開資訊、選手區禁用 merge、歷史選取／資訊唯讀。既有拖曳正常／失敗／Escape／touchCancel／原生觸控捲動與下一次單雙擊恢復、交換／上下插入／空格落點、X／Esc／backdrop、歷次資訊晚回應／空／失敗／歷史餐食隔離皆有針對證據。

布局幾何與實際 screen：1920×900 主表格>1100px、右側變動與版本頂對齊；1440×900 表格>1200px、下方兩欄；390×900 先變動後版本。三種寬度 document 溢位<=1px，diff 與版本獨立捲動，舊至新排序／最新標記／初次捲底／閱讀舊版不搶捲動與新保存定位最新均通過。screen 位於 test-results/grid-panels-integration/competition-levels-雙欄選格：寬桌面筆電手機布局與獨立捲動-{desktop|mobile}/history-panels-{1920|1440|390}-screen.png，三張已目視；最新版 readonly detail 與range screen 在 grid-panels-click-final 的「雙欄選格：單雙擊鍵盤範圍與唯讀資訊」子目錄。以上為 screen，非 print media。

`npm --prefix frontend run typecheck`、`npm --prefix frontend run build -- --outDir ../frontend/dist-grid-panels`、`git diff --check` 通過。最終 build JS index-DGQG1ehm.js、CSS index-DakIpyZL.css；來源與成品完整雜湊以 data/grid-panels-delivery-identity.json 為準。僅三個前端 product 檔不同於 grid-header source manifest；backend/schema/API/deps、兩個 gesture hooks 與 print 元件未改，故不重跑後端或重新產 PDF。無實機手機／其他 OS 驗證，不宣稱使用者已驗收或已部署。8043 測試完成後退出，全部舊成品保留；無 Git stage/commit/merge/push，公開資料／服務／session／ngrok 未由 task4 操作。

## Excel 匯出、工具列與列印格線精修（2026-09-22）

B `feat/arrangement-export-print`、base/HEAD acacb876c90aad109af12edd831561fd9fa93914，Windows／Node 24.11.0／Playwright 1.63.0 Chromium desktop + mobile 觸控模擬，single worker。全部合成資料；獨立 grid-export-e2e.db／8043／frontend/dist-grid-export。

`npm --prefix frontend run typecheck`、`npm --prefix frontend run build -- --outDir ../frontend/dist-grid-export`、`npm --prefix frontend audit --audit-level=high`（0 vulnerabilities）、`git diff --check` 通過。最終命令 `npm --prefix frontend run test:e2e -- competition-levels.spec.ts --grep '匯出精修：|表格新版：完整列印|表頭修正：上色回應|表頭修正：回應內容|表格刪除：素食' --output=test-results/grid-export-final`：**14 passed / 35.8s**。涵蓋 toolbar 開關與SVG中心／順序、current/history/legacy下載、匯出零寫入與不裁搜尋、真實Blob URL下載階段失敗後finally清忙碌與同頁重試、unknown禁匯出、原key重試、GET與response-body逾時恢復、歷史捲動、完整列印及寬長分幅。必要安全恢復測試保留，只改原先依賴一般手動刷新圖示的fixture。

前期按需載入測試曾 4 passed/2 failed，揭露瀏覽器快取失敗 module；main已改定靜態匯入，移除臨時loader/Vite plugin及舊lazy測試。中間整合14案例未完成即取消，不算通過證據；上述14通過為最終靜態版本。

8份實際瀏覽器 current/history/retry/legacy下載，由 `scripts/verify_arrangement_exports.py` 用獨立 openpyxl 3.1.5 讀回，核對每個原生儲存格文字／空位／座標／thin border／灰階／wrap／行欄尺寸、merge範圍、每人一次、純字串、無公式／外部連結／macro／media，全通過。`=SUM(1,2)`、`+第一級`、`@隊名`、`-自訂文字`與換行／繁中／emoji均保存為文字。報告 `data/grid-export-xlsx-verification.json`。openpyxl報缺default named style並套用default的非致命警告；逐格明確樣式檢查通過，未宣稱Microsoft Excel實機測試。artifact-tool只用於QA匯入渲染，未加入產品依賴；current/history/legacy PNG（data/grid-export-xlsx-visual）已目視，合併、空位、姓名、素標及歷史差異清楚且無裁字。

格線鑑識見 `data/grid-export-print-forensic/REPORT.md`、measurements.json、border-detail-comparison.png：同一合成表600dpi，原SVG覆蓋5851個深色格線像素；.25mm內縮後對照no-SVG缺失0、額外0；.125mm仍有1218個差異，故採.25mm。內縮約1CSSpx白邊已接受，不將正常次像素6–7px差異視為完全相等線寬。

產品PDF取自最終E2E，Poppler渲染已目視。grid-lines-default/background-off各1頁且3名各一次；current/history各1頁且80名各一次；wide-long維持4個分幅、實際5頁（首分幅自然跨2頁），80人皆恰一次，跨頁合併標示與素標完整。背景開關兩張差異限預設表頭底色區，非全圖pixel相同；設定灰階196/217/237皆保存。報告 `data/grid-export-pdf/verification.json` 與各PNG。沒有橘色搜尋／選取高亮。

無後端／schema／API變更，未重跑無關後端全套。未測實體Excel、真實手機、其他OS或實體印表機；不安裝或等待，工程證據不代表人工已接受。最終指紋 `data/grid-export-delivery-identity.json`，全部舊成品保留，8043退出。未操作公開資料／服務／session／ngrok，未stage／commit／merge／push；交由orchestrate核對後安排task5發布。

## D 上色恢復、同高側欄、歷史捲動與頁首（2026-09-22）

沿用 B feat/arrangement-export-print@acacb876c90aad109af12edd831561fd9fa93914 與上一未提交精修；新隔離 frontend/dist-grid-recovery／data/grid-recovery-e2e.db／8043。Windows、Node24.11.0、Playwright1.63.0 Chromium桌面與手機觸控模擬，單worker，全部合成資料。

原事件限制：task5唯讀核對現用grid-export-20260922-173559的58份來源及公開3資產hash一致、health200；app無access log且ngrok inspect關閉，無當次POST/GET紀錄。可用瀏覽器沒有使用者原tab，21:26截圖警告被裁掉。因此不能判定原事件屬unknown/refresh/rejected或是否已保存，也不能歸因ngrok／睡眠／session；task4未讀寫public DB、重登／reload／清cookie／解除原unknown。

修前因果證據（非原事件原因）：grid-recovery-reproduce的desktop實際POST先讓revision+1，再替換成功回應為200 {}，前端拋「Cannot read properties of undefined (reading 'action')」並永久refresh、只有不能解決問題的GET恢復；預期1failed。grid-recovery-auth-reproduce預期2failed：真實同帳號新登入輪替cookie使舊頁CSRF持續403，原恢復只GET不更新token；已提交但回應遺失的unknown重試401被降rejected。以上均在新合成服務重現。

最終修正：嚴格辨識小存必要receipt與原request/payload，無效成功回應維持unknown；人工恢復先GET認證並核對原帳號，保留原key/payload及草稿；合法receipt後GET失敗只讀回。unknown後401/403不丟原請求；unknown後真正409/422可重新核對，避免初次未送達、其他頁變更後一直重送舊token。20s、CSRF、CAS、actor綁定與idempotency不放寬，沒有新自動重試。

驗證結果按實際輪次保存：
- grid-recovery-first：22項中20passed、2failed／55.0s。僅最後非同步歷史首載在setup碰到合成帳號登入頻率上限，未進功能斷言；不放寬產品限流，後續改用既有另一合成帳號。
- grid-recovery-final：12項中10passed、2failed／1.5m。無效receipt擴充object/null/204/HTML/wrong-key/wrong-operation、stale CSRF、合法receipt後異常GET、同高尺寸／header與歷史async均桌面手機通過。兩fail是401測試只等button visible便切換mock，POST因而成功、下一次等待已移除按鈕；改等實際401 response與button enabled，不改產品處理來配合測試。
- 審查另發現unknown一律保留會使確定409無法解鎖，收斂到只特別保留401/403。最終 grid-recovery-boundary-final：**12passed／20.9s**，命令 `npm --prefix frontend run test:e2e -- competition-levels.spec.ts --grep '狀態精修：未知|格位大存未知|格位文字409|表頭修正：上色回應|表頭修正：回應內容' --output=test-results/grid-recovery-boundary-final`。包含未知後持續401、認證preflight後POST401、不同帳號不重送、未送達後真實409重核對、大存舊receipt不回退、409文字草稿保留及20s transport/body期限。最終**28個不同案例有適用通過證據**，不是單次28全套。

側欄幾何驗證表格與兩側頂部／高度差<2px，涵蓋插列、刪列、長文字換行、目前／歷史切換、換場及2400/1920 resize；標題保持固定、兩區獨立scroll。1440表格上兩欄下、390堆疊且document無橫溢。頁首brand/admin左緣與arrangement-main差<2px；切報名設定恢復1240px。每次關閉重開（仍選舊版）與非同步初載皆捲到底且不改selected，開著閱讀時一般rerender不搶捲動。畫面見 grid-recovery-final 的 aligned-1920/1440/390-screen.png 與 unknown-recovery-screen.png，已目視並交orchestrate核對。

最後typecheck、production build、git diff --check通過。Excel exporter／列印元件及print CSS／package-lock與前輪一致，沿用匯出與PDF證據；backend/schema未改，不重跑無關全套。未測實體手機、其他OS或實體列印。最終identity為 data/grid-recovery-delivery-identity.json，舊9組成品保留且逐檔驗hash，8043測完退出。task4未stage/commit/merge/push/部署、未動A/8041/8042與public session/DB/ngrok。工程驗證通過不代替原使用者事件根因或人工接受。


## 同色 no-op 鎖場與色票修正（2026-09-22）

使用者補充確切原文「安排沒有變更」及「重新讀取並核對」。修前先核對來源58/58檔等同D identity，獨立 dist-grid-shade／grid-shade-e2e.db／8043 合成80人、既有底色及歷史；真實 shade_header 已為2再按2，POST422 detail「安排沒有變更」→rejected／verified=false→所有編輯鎖定，桌面手機均重現。證據 grid-shade-normal-confirmed/*既有同色重點*/same-shade-observations.json。正常不同色 POST200／receipt／GET200 完成，無 React pageerror；成功清選取另導致色票disabled，與使用者的422鎖場是不同現象。沒有修改或重送原公開請求。

修正：已選同色不POST；成功保留選區，outline不遮底色，支持同格不重選連續換色。「表格底色」共框、白最左及3灰、沒有可見文字數字／斜線；白保持清除局部色／繼承軸色。controller僅首次精確no-op422自動GET核對，未偽造receipt／revision／Undo／已儲存；GET失敗仍鎖定。一般422／409與unknown保持原保護，不加入自動重送。

本輪14個不同案例有適用通過證據（不是單次14全套）：grid-shade-fix 8passed／2fixture failed／30.9s；grid-shade-boundary 4passed／2fixture failed／16.4s；修正合成fixture先合法插空列後 grid-shade-merge-final 2passed／16.6s。兩次merge fixture失敗分別為不存在row索引、選到含人列而被合法422拒絕，產品沒有為fixture放寬。最終去除手機色票暫時tap藍色遮罩後，grid-shade-visual-final 2passed／13.6s。早期正常診斷中止另有登入前預期401混入console監測、header清除合法null被測試誤判為0，均已修測試窗口與空值斷言。

案例包含80人＋4保存版＋既有底色、header/body不重新選格连续6色、同色／已無局部色按白／merge no-op不POST、真後端3種no-op皆422且state完全不變、真422無變更自動GET再繼續修改、讀回失敗只GET恢復、一般422与unknown不自動解鎖、已寫入回應遺失原payload重試及真409衝突。正常觀測 JSON 含request/receipt/revision/選取/控制可用性。最終1440與390截圖見 grid-shade-visual-final/*/shade-palette-screen.png，已目視共框、純白及選框。Windows／Node24.11.0／Playwright1.63.0 Chromium桌面与觸控模擬；沒有真手機／其他OS證據。

typecheck隨production build通過，git diff --check通過。相對D產品只5檔：LevelCardBoard、CellShadeMenu、gridShade、styles、useArrangementWorkspace。Excel exporter、列印與D側欄／頁首邏輯、後端、schema、依賴不變；沿用其前輪證據，不重跑無關全套。舊10組成品逐檔hash不變；8043已退出。指紋 data/grid-shade-delivery-identity.json，task4未stage／commit／merge／push／部署，未動公開session／DB／app／ngrok。公開更新由orchestrate核對後交task5；工程通過不代表人工已驗收。

## F 格位操作選單、表頭合併與明確白色（2026-09-23）

B `feat/arrangement-export-print`、起始 HEAD `acacb876c90aad109af12edd831561fd9fa93914`，Windows／Node 24.11.0／Playwright 1.63.0 Chromium desktop 與 390×844 mobile 觸控模擬、single worker。只使用合成 `data/grid-menu-e2e.db`／8043／`frontend/dist-grid-menu`；沒有公開資料、A／8041／8042／8044、ngrok 或既有 runtime 操作。新增 JSON／operation 契約沿用 schema 0008，無 migration。

根因與修正：早期 `grid-menu-touch-lifecycle` 2 項失敗，一項是桌面 outside click 沒關閉，一項是手機 ⋯ 開啟後 dialog 消失；`grid-menu-header-fixed` 桌面通過、手機仍在初次開 menu 失敗。`grid-menu-touch-diagnostic` 的 `touch-events.json` 證實 pointerdown／touchstart 在 trigger，touchstart 後 portal mount；同一手勢後續相容 click 改命中新出現的 `.secondary` 菜單操作鈕並關閉 dialog。移除提前開啟的 `onTouchStart`、保留原生按鈕 click；outside pointerdown 改同步 capture-phase 並安全處理非 Element target。這是瀏覽器事件順序的實證，不是鍵盤 emulation 限制。

最終 Playwright 證據（以下為分開 scoped runs，非全套一次跑完）：

- `grid-menu-menu-lifecycle-fixed`：**2 passed／8.7s**。桌面完整驗表頭選取／合併／編字／Undo／outside close／Shift+F10；mobile 驗表頭 ⋯、底色 tap、outside close 與 Escape。
- `grid-menu-mobile-no-post`：**1 passed／6.2s**。開啟手機表頭選單前後 operations POST 為 0，`layout_revision`／`state_token` 不變且 menu 保持可見；再 tap 底色才寫入，接著外點與 Escape 均關閉。
- `grid-menu-export-recovery`：**6 passed／15.6s**。desktop／mobile 的明確白色跨區操作、目前／歷史列印與匯出、未知結果固定 payload 重試與真 409 保護、跨分幅表頭／淡橘差異 PDF／XLSX。

上述結果對應的實際命令及 Playwright `.last-run.json` 完成時間（UTC）：

```text
2026-09-23T01:54:57.9766278Z  npm --prefix frontend run test:e2e -- grid-menu.spec.ts --grep 'F表頭與資料共用選單' --output=test-results/grid-menu-menu-lifecycle-fixed
2026-09-23T01:55:44.1564053Z  npm --prefix frontend run test:e2e -- grid-menu.spec.ts --grep 'F白色|F選單未知|F跨分幅' --output=test-results/grid-menu-export-recovery
2026-09-23T01:56:40.2499487Z  npm --prefix frontend run test:e2e -- grid-menu.spec.ts --grep 'F表頭與資料共用選單' --project=mobile --output=test-results/grid-menu-mobile-no-post
```

後端沿用本輪 touch/UI 修正前已完成的 `tests/test_grid_menu.py`、`tests/test_grid_header.py`、`tests/test_grid_cell_shade.py`、`tests/test_grid_undo.py` **43 passed**；這之後沒有後端程式變更，不重跑。`npm --prefix frontend run build -- --outDir ../frontend/dist-grid-menu`（內含 app typecheck）通過。明確白色以持久化 shade 0 覆寫軸色；缺少局部項目保留舊繼承行為，且不回填舊 JSON。

`scripts/verify_arrangement_exports.py` 獨立讀回 `grid-menu-export-recovery` 的 6 份 desktop/mobile current、history、wide-header XLSX；每份 3 名選手，所有儲存格文字／座標／填色／合併／邊框／格式檢查均 **PASS**。uv 專案環境沒有 openpyxl，因此用 Codex bundled Python／openpyxl 3.1.5 執行，不新增產品依賴；openpyxl 的 no-default-style warning 非致命，逐格樣式檢查通過。兩份 desktop PDF 以 Poppler 渲染並目視：白色歷史版 1 頁、跨分幅版 2 頁，無裁切／重疊；第 2 頁只有第 13 欄，是測試此跨幅合併延續的稀疏頁。渲染 PNG 已清除，原 PDF／XLSX 留在忽略的 E2E 結果目錄。

不含實體手機、其他 OS、Microsoft Excel 實機或實體印表機驗收。task4 僅交付 B worktree 未提交變更與新 identity；沒有 stage／commit／merge／push／部署。舊成品需逐檔核對後才列為未變，公開更新仍依 task5 的既有授權與 freeze／GO 流程；工程通過不等於人工驗收。

## B 逐步重做、差異定位與側欄驗收（2026-09-23）

B `feat/arrangement-export-print`，起始 HEAD `acacb876c90aad109af12edd831561fd9fa93914`，Windows／Python 3.14.6／Node 24.11.0／Playwright 1.63.0 Chromium desktop 與 390×844 mobile 觸控模擬、single worker。沿用 `schema_version=1` 的 0008 layout 與 receipt JSON，沒有 migration file 變更。Playwright runner 只在全新 synthetic DB 執行既有 Alembic 0001–0008；未遷移任何既有／真實資料庫。未操作公開 app、真實會員資料、session、ngrok、8041／8042 或既有預覽；8043 每輪由 Playwright 啟停，最後 listener 為 0。

後端將伺服器保存的 undo 前布局引用保存在私有 receipt `_redo_stack`。Redo 只取同一 actor／場次／保存基準及現有 head、token、revision 下的 stack 頂端，以新 receipt、單調 revision／報名 version 與稽核交易重做；不接受或重送 client snapshot／舊 operation。普通新操作清除 redo 分支；大保存與外部更新斷鏈。前端 pending／unknown 保留固定 key／payload；receipt 後讀回失敗只 GET。快捷鍵 Undo Ctrl／Command+Z，Redo Ctrl／Command+Shift+Z 或 Ctrl+Y；文字輸入／IME／dialog 原生復原、歷史唯讀與 locked state 不攔截或寫入。無新增資料表或 schema migration。

差異卡按 registration ID 顯示新增、移出、同級換位、跨級移動及交換，只定位目前布局中實際存在的來源／目標 stable 格位；點卡不改 revision、選區或 arrangement POST，歷史版與鍵盤／觸控操作可用。舊版本無座標／來源軸被刪除時不推算位置，顯示旁列原因。左右側欄標題保持固定、各自獨立捲動且標示比較版／目前安排；切換或重開仍回到最新版本。純結構差異保持保存能力，不出現泛用結構提示或錯誤的「沒有變更」。固定級數表頭 hover 顯示 `cell` cursor。目視發現全站 `button:hover` 會令淺色卡片轉深綠、黑字對比不足；改為淺底 hover/focus、保留新增／移出顏色，並加入 computed background assertion。

驗證均對應最後 source snapshot：

- `UV_CACHE_DIR=%TEMP%\codex-grid-redo-uv-cache uv run --locked pytest -q -p no:cacheprovider --basetemp %TEMP%\fucheng-grid-redo-backend-20260923 tests/test_grid_menu.py tests/test_grid_header.py tests/test_grid_cell_shade.py tests/test_grid_undo.py`：**44 passed／19.26s**，僅 Starlette/httpx 相依棄用警告。
- `npm --prefix frontend run typecheck` 通過；`npm --prefix frontend run build -- --outDir ../frontend/dist-grid-redo-final` 通過。最終獨立 CSS `frontend/dist-grid-redo-final/assets/index-W7BGt1dM.css` SHA-256 `78399245B8D89F915CE85290FF1A2FEF5E4E0BB48A604C0DD04DA3061ACE2CA2`，內容包含淺底 hover 規則。舊 `dist-grid-redo` 原樣保留。
- `npm --prefix frontend run test:e2e -- e2e/grid-redo-locator.spec.ts --output %TEMP%\fucheng-grid-redo-e2e-output-20260923-final-visual`：**10 passed／31.2s**；desktop／mobile 各 5 項。覆蓋 Undo/Redo 多步與分支、保存鎖定、輸入及 IME 例外、unknown 固定重試、receipt 後只讀回、外部更新失效、diff cards／歷史／舊座標、獨立側欄捲動與凍結標題、重新開啟定位最新及結構差異。
- `npm --prefix frontend run test:e2e -- e2e/grid-redo-locator.spec.ts --grep '變動卡片以 stable 格位定位新增移出移位交換與歷史版本' --output %TEMP%\fucheng-grid-redo-e2e-output-20260923-contrast`：**2 passed／11.2s**，desktop／mobile 均對最終 build 斷言 computed background `rgb(255, 240, 194)`。
- `git diff --check` 通過，只有既有 CRLF 正規化提示。Earlier E2E attempts found fixture issues (collapsed panel, locked menu, no-op baseline save, and a selected historical version that was not re-fetched); the fixtures/assertions were corrected without loosening API validation. A scoped rerun verified the missing-layout route interception before the final full run.

最終 E2E DB 為 `data/grid-redo-20260923-final-visual-e2e.db`，對應獨立 static `frontend/dist-grid-redo-final`、port 8043；顯示用截圖複本在 ignored `data/grid-redo-visual-20260923/`（12 張 desktop／mobile current／history／missing-layout／recovery／undo-history／sidebar screens），Playwright 原始輸出保留於上述 `%TEMP%` 目錄。`data/grid-redo-delivery-identity.json` 記錄完整 dirty source、static 與 screenshot hash。其他合成測試 DB／輸出均保留，未 stage／commit／merge／push／deploy；沒有進行人工接受、實體手機或其他 OS 驗收。

## v0.2.0 大型保存快照與歷史側欄（2026-09-23）

B worktree `feat/arrangement-export-print`，基底 commit `acacb876c90aad109af12edd831561fd9fa93914`。後端回歸 `tests/test_arrangements.py::test_large_save_preserves_exact_layout_across_receipt_get_noop_and_history` 1 passed；覆蓋保存 receipt、GET、歷史快照、無變更 422、後續保存及第一版歷史不變。合成資料刻意含使用者新增尾列、文字／合併、列色與局部色；workspace 原始 layout JSON 在第一次大型保存前後相同。

最終 Playwright E2E `frontend/e2e/grid-save-tail.spec.ts` 在 Windows Chromium 桌機與 390×844 觸控模擬各 1 passed（共 2 passed／13.0s），使用新建合成資料庫 `data/grid-save-tail-final-20260923-e2e.db`、既有 0001–0008 migrations 與獨立 `frontend/dist-grid-save-tail-final-20260923`。檢查合法滿級移動所新增列確實含選手，Undo／Redo 回復；再核對尾端空白有色列及文字／合併列在大型保存 receipt、GET、歷史讀回、第二次保存、無變更拒絕及重新整理後 row ID、角色、格數與選手位置不變。無變更保存回 422，第一版歷史保持原快照。最終輸出及截圖複本位於 `C:/Users/morris/AppData/Local/Temp/fucheng-grid-save-tail-e2e-final-20260923` 與 `data/grid-save-tail-visual-20260923/`；8043 測試後監聽數為 0。

歷史側欄標題「版本紀錄」與「目前安排」按鈕同列靠兩側；保留原凍結標頭、版本列表獨立捲動與分隔線。E2E 驗證目前／歷史點選、`aria-pressed` 及按鈕高度至少 44px；桌機及手機截圖已保存。`npm --prefix frontend run typecheck` 與獨立 build 通過；未新增 migration。沒有動真實／公開資料庫、既有服務或正式部署。

先前一次探索性瀏覽器測試把保存後會合理消失的淨差文字標記納入整列 `innerText` 比對，也重複執行了桌機／手機回圈；它不是產品缺陷證據。最終斷言改比 stable row ID／role／格數／選手 ID；這項測試斷言修正不是產品修復，也不代表尾端空列已修好。尾端空列偶見於大型保存或重新啟動後的情況，本輪未重現、未修復，使用者同意延後；沒有新增裁切或 fallback，也沒有以修改保存流程掩蓋問題。沒有進行公開資料、正式服務、實體手機或其他作業系統驗收。Git、image 與 B 預覽的發布狀態見 `docs/deployment.md`。

## v0.2.0 發布驗證（2026-09-23）

來源 `main`／`origin/main` commit `c9c4e0be1907cf6e6f2f2a54ffafba3ab4868e45`，annotated Git tag `v0.2.0` 指向該 commit。Docker Hub 公開 repository 為 `momonong/fucheng-players-system`；`0.2.0` 與 `latest` 都是 Linux/amd64，OCI index digest 均為 `sha256:bf522f2646caf936fd8c4b852789ed34367f85979a867511b3f3f5a7d2f70176`。image synthetic volume 驗證另見[部署紀錄](deployment.md#v020-docker-image-與-b-預覽2026-09-23)。

Windows Chromium E2E 使用合成資料與獨立輸出：

| 批次 | 結果 | 保留證據 |
| --- | --- | --- |
| A-r2 | 30 passed，`.last-run.json` 為 passed | `data/release-playwright-0.2.0-competition-a-r2-results`；DB `data/comp-levels-release-0.2.0-a3-e2e.db`；port 8032 |
| B3（含明確白色 desktop/mobile） | 10 passed，`.last-run.json` 為 passed | `data/release-playwright-0.2.0-competition-b3-results`；DB `data/comp-levels-release-0.2.0-b3-e2e.db`；port 8033 |
| C2 | 14 passed，`.last-run.json` 為 passed | `data/release-playwright-0.2.0-competition-c2-results` |
| C3 首輪 | exit 1；12 passed、4 failed（16 個 desktop/mobile 測試）；52.5 秒 | `data/release-playwright-0.2.0-competition-c3-results`；DB `data/comp-levels-release-0.2.0-c3-e2e.db`；port 8033 |
| C5 targeted（兩個色票案例） | exit 1；2 passed、2 failed；35.9 秒。八十人案例 desktop/mobile 通過；同色案例兩個 viewport 因測試 locator 失敗 | `data/release-playwright-0.2.0-competition-c5-results`；DB `data/comp-levels-release-0.2.0-c5-e2e.db`；port 8033 |
| C6 targeted（同色案例，修正 locator 後） | exit 0；desktop/mobile 2 passed；14.3 秒 | `data/release-playwright-0.2.0-competition-c6-results`；DB `data/comp-levels-release-0.2.0-c6-e2e.db`；port 8033 |

三批都在 B worktree 的 `frontend/` 以 PowerShell 執行；共同設定為 `PYTHONUTF8=1`、`FUCHENG_E2E_PORT=8033`、`FUCHENG_E2E_STATIC_DIR=frontend/dist-release-0.2.0`，各自使用上表的獨立合成 DB。實際 Playwright 命令如下：

```powershell
npm run test:e2e -- e2e/competition-levels.spec.ts --grep '狀態精修：表格同高動態尺寸歷史重開與頁首對齊|狀態精修：非同步首載開歷史後定位最新|狀態精修：未知未送達後真實409可重新核對|色票故障：八十人正常連續點色生命週期|色票故障：同色白色與合併範圍不重送|色票故障：真實未變更回應自動讀回且不假造保存|色票邊界：未變更讀回失敗仍鎖定而不重送|色票邊界：一般422與未知請求不可自動解除' --output ../data/release-playwright-0.2.0-competition-c3-results
npm run test:e2e -- e2e/competition-levels.spec.ts --grep '色票故障：八十人正常連續點色生命週期|色票故障：同色白色與合併範圍不重送' --output ../data/release-playwright-0.2.0-competition-c5-results
npm run test:e2e -- e2e/competition-levels.spec.ts --grep '色票故障：同色白色與合併範圍不重送' --output ../data/release-playwright-0.2.0-competition-c6-results
```

C3 篩選 8 個測試標題、桌機與手機共 16 例。四個失敗實例是「色票故障：八十人正常連續點色生命週期」及「色票故障：同色白色與合併範圍不重送」各自的 desktop/mobile。C3 原錯誤分別顯示色票按鈕尚不存在，以及首次明確白色寫入被測試誤判為 no-op（預期 422、實收 200）。修正後 C5 重跑兩個標題：八十人案例 2/2 通過；同色案例兩例失敗，因測試把「表格底色」group 定位在安排區而非開啟的儲存格操作選單。僅修正測試操作／定位，保留 no-op 與保存斷言；產品程式與 `frontend/dist-release-0.2.0` 未變。C6 只重跑同色案例，在桌機／手機 2/2 通過。因此四個原失敗 viewport 均有後續 pass 證據；C3、C5 原始執行結果仍保留 failed，沒有單次全 16 例重跑，故不把 C 系列描述為單次全綠。A-r2、B3、C2 的留存狀態皆為 passed。自動測試與觸控均為 Windows Chromium／Playwright 模擬，不替代實體手機、其他 OS 或使用者人工驗收。

公開 B 原生預覽 `data/grid-public-runtime/releases/grid-v020-20260923-200323` 的唯讀檢查：本機及 HTTPS health 為 `{"status":"ok"}`；首頁、JS、CSS HTTP 200／`no-store`，三個回應檔 SHA-256 與凍結 image static 相同。更新前後 SQLite Backup API 檢查 18/18 table row count/hash 不變，schema `0008_arrangement_grid`、integrity `ok`、FK errors 0；沒有 migration、reseed、業務寫入或管理員登入/session 變更。此為合成 B 預覽，不是正式資料庫或正式部署；公開 admin UI 操作沒有測試，人工驗收仍待進行。大型保存或重啟偶見尾端空白列的已知限制仍未重現、未修復。
<a id="security-stage"></a>

## 公開安全、Turnstile 與週備份工作樹（2026-09-24～25）

此段只記錄本工作樹的合成工程驗證，**未部署到 8052、8044 或任何正式入口**。起始與目前 HEAD 均為 `ef147253ca1604fc8c4c74175b3f9f7fe08894a6`（detached）；原有公告／編輯器／schema 0009 等未提交工作保留，本階段未 stage、commit、merge、push、部署、修改真實資料或操作舊服務。Windows／PowerShell、Python 3.14、Node 24、Chromium Playwright；Linux 容器與真正 Cloudflare 網域／金鑰尚未驗證。

- 後端目標：`tests/test_security_stage.py tests/test_deployment_boundary.py tests/test_weekly_backup.py tests/test_announcement_media_backup.py`，**29 passed**。覆蓋請求入站上限、信任代理 IP、Turnstile 回應失敗／錯 hostname／action／時限、一次性 token 後同 receipt 讀回、週一 04:00 曆法、八週 retention、失敗保留舊備份，以及新目標還原後舊 session 失效／稽核 actor 保留。皆為合成／fake Siteverify，不是 Cloudflare 真實連線。
- 既有公開報名、網站、名單匯入後端回歸：`tests/test_public_registration.py tests/test_website.py tests/test_roster_import.py`，**31 passed**。全後端 `pytest` 首輪 **186 passed／1 failed**；失敗為新並發上限 32 拒絕既有 50 個同時公開讀取的測試。修為有限上限 64 後，受影響的 `tests/test_concurrency.py tests/test_security_stage.py tests/test_deployment_boundary.py` **27 passed**。首輪失敗作為歷史紀錄保留；2026-09-25 新增下述合成情境、修正 slow trickle 總時限後，以 `uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-security-full-final` 在最終後端程式碼 **190 passed、2 個第三方棄用警告、exit 0（100.62 秒）**。
- 共享 Wi-Fi 合成：六個獨立瀏覽器 visit 同用一個經 Cloudflare 可信 proxy 驗證的 `192.0.2.77`，各自建 session、搜尋一位合成會員、送出一次報名，**6/6 為 201**，6 個 visit cookie 不同，6 筆報名及稽核均成立。預設入站配額為每 client `public-read` 120 容量／每秒回補 2、`public-write` 40／每秒回補 0.7；此案例使用預設值，沒有 429。攻擊突發另用**縮小的測試配額** read 每 IP 2／0.5 每秒、全局 4／1 每秒：同 IP 前 2 次成功、第 3 次 429 且 `AuthAttempt` 計數未增；另一 IP 同時成功；模擬 2 秒回補後原 IP 再成功。非可信 socket 偽造 `CF-Connecting-IP`／XFF 回 400，未寫 `AuthAttempt`。這驗證機制與一組有限家人情境，不代表真實共享 Wi-Fi 的誤攔率或分散式攻擊容量。
- 原 body 接收迴圈每個 chunk 重新給 5 秒，已改為**整個 body 共用 5 秒 deadline**。slow trickle 合成每 2 秒到一小塊，第三塊已越過總時限時回 408；下游 app 不執行、並發 slot 釋放。`tests/test_security_stage.py tests/test_deployment_boundary.py` 變更後聚焦 **29 passed**，隨後納入上述最終全後端 190 passed。
- `npm run typecheck` 與 `npm run build -- --outDir ../frontend/dist-security-stage` 通過，建置成品隔離在新目錄。第一次建置受沙箱的 Vite 設定路徑讀取拒絕，核准的重跑成功。Compose Cloudflare overlay 的 `docker compose config --no-interpolate --no-path-resolution --format json` 通過；僅解析設定，未啟動 Docker、Cloudflare 或主機服務。
- `frontend/e2e/self-registration.spec.ts` 最終在桌機／390×844 手機模擬 **2 passed**（`data/security-stage-e2e-followup/.last-run.json` 為 passed），使用獨立 `data/security-stage-e2e.db`、port 8031、`frontend/dist-security-stage`，single worker。既有測試定位舊行政名單／稽核畫面造成先前失敗；改依目前十級名單與管理 API 驗證稽核後通過。此次再以 mock edge HTML 403 驗證匿名前端不把 HTML 當 JSON，顯示中文安全提示、姓名／葷素與同一 request_id 保留；另以本機 fake Turnstile script／session sitekey 模擬 Siteverify 503，驗 `interaction-only`、重置 widget、姓名／餐食與 request_id 在重試時不丟失。後端 timeout 到 503 的映射由 fake `urlopen` 測試驗證；沒有真實 widget／Cloudflare 連線。首次瀏覽器啟動 `spawn EPERM` 是沙箱限制；核准重跑後才實際執行。未測外部 WAF、真實共享 Wi-Fi 誤攔或 Linux 重啟恢復。
- `git diff --check` 通過（有 Windows LF→CRLF 提示）。本機 8052 listener PID 2136、8044 listener PID 45460 仍在；直接 localhost health 因缺 ngrok proxy identity 回 400，符合既有邊界，不是透過公網的健康驗證。8031 E2E listener 測後未留存。未執行正式資料遷移、公開入口切換、異地備份或實際災難還原。
