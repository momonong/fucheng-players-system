# A 版會員與比賽名單驗證（2026-10-20）

工作分支 `fix/print-roster-layout`，起點 `b1859eaf13d6ce0028fd749880d6819ce09258a3`。本紀錄取代先前「8 pt、完整縮成一頁」方案。使用者選定會員 A、比賽 A，並指定只有會員名單按筆畫排。以下工程驗證記錄以 freeze 當時尚未部署的狀態為基準；其後已於 2026-10-20 台北時間 23:33 部署既有家中試用站 snapshot，詳見[部署紀錄](home-deployment.md)。仍未提交、推送或發布版本／registry 映像。

## 實際行為

- 會員列印每頁五級、每級兩欄；各級按自己的 `ceil(人數/2)` 分左右欄，先左欄由上而下，再右欄。姓名 14 pt、行高 21.5 pt、辨識上標 10 pt、頁尾註記 12 pt；不縮小字體。更多人、長姓名或長註記自然增頁。
- 合成主名單依目前核對的各級數量 `[42,42,42,45,41,26,30,26,14,34]`，合計 342 人，第一頁 23 行、第二頁 17 行，實際 Chrome PDF 恰兩頁。姓名全部為合成資料。
- 比賽保留原 rows／columns／stable ID／空格／排序／合併／灰階與局部白色 override；姓名 16 pt、素字最終 12 pt（見 10/21 精修）、行高至少 38 pt。以 12 行×9 欄、80 人、四個 1×2 合併格與 27 個素字的合成布局驗證，實際 PDF 一頁。沒有把真實布局改成樣張隊伍。
- 全部表格內外框、表頭、級數線統一 0.75 pt。安排表頭的 0 色維持白色，灰階由既有 SVG 保留，背景圖形關閉仍有色階。表頭文字依 A 使用深綠色。
- 沿用原安排成熟分幅邏輯，容量改為每幅最多 10 欄、11 個 body 行；原始跨幅合併依交集標示續接，選手只屬於一幅。瀏覽器仍可因長文字增加實際頁數；幅數不等於實際紙張頁數。最大合法 500×50 布局完整保留末格與 80 名選手，該極端合成 PDF 為 455 頁；沒有壓縮成小字。
- 公開會員列表／列印與管理會員清單以 `Intl.Collator('zh-Hant-TW-u-co-stroke')` 排姓名，再按辨識註記／ID 穩定排序。各級人數移除，總人數保留。比賽、報名、候補、選名流程未改排序或後端回應。
- 公開畫面桌面每列五級、每級兩欄姓名，字 18 px；窄畫面改每列兩級／一級，手機字 20 px，長內容換行。登入表單保留 16 px gap。
- 列印按鈕開預覽、Ctrl／Command+P 開預覽、預覽內直接列印；背景 inert、焦點循環／還原、Escape／返回關閉。預覽縮放僅用於螢幕檢視，實際列印不縮字。
- Excel 仍可編輯，A4 橫式 `fitToWidth=1`、`fitToHeight=0`，解除高度硬塞一頁；資料、合併、底色與歷史不變。

## 環境與可重現指令

Ubuntu、Node 22、Chrome 155、Playwright channel `chrome`。沒有新增產品依賴、API、schema 或 migration。所有 E2E 只用隔離資源：`frontend/dist-print-a-20261020`、`data/print-a-e2e-20261020.db`、127.0.0.1:8068；runner 只新增此 DB allowlist。測試由 runner 啟停，未改現用服務、DB 或 static。

```bash
npm --prefix frontend run typecheck
npm --prefix frontend run build -- --outDir dist-print-a-20261020

export FUCHENG_E2E_DATABASE_URL=sqlite:///data/print-a-e2e-20261020.db
export FUCHENG_E2E_PORT=8068
export FUCHENG_E2E_STATIC_DIR=frontend/dist-print-a-20261020
export FUCHENG_E2E_BROWSER_CHANNEL=chrome

UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python \
  uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-print-a-20261020-allowed
```

| 檢查 | 結果與證據目錄（frontend/test-results/ 下） |
| --- | --- |
| TypeScript／Vite build／git diff --check | 通過；最終 assets `index-Cv2u8fR5.css`／`index-BrNtzusK.js` |
| Python 既有全套 | 257 passed，71.08 秒；兩則既有 FastAPI／Starlette deprecation warning |
| 會員 A、登入、管理 95 人、比賽 A、會員流程，桌面及手機 | 合計 10 項通過；`print-a-approved-20261020`。該組另兩項新排序測試的 fixture 預期已修正並在下列六項重驗通過 |
| 最大 500×50 與 legacy 未知餐食，桌面及手機 | 2 項通過；`print-a-final-20261020`，所有姓名及最後一格皆在 PDF，未知餐食沒有補造素字 |
| 80 人完整列印、歷史凍結、跨行／欄分幅 | 桌面 1 項通過；`print-a-regression-20261020` |
| 局部底色、表頭色階／歷史 PDF、目前／歷史 Excel | 桌面 3 項通過；`print-a-small-regression-20261020` |
| 白色 override／跨頁合併表頭／管理會員筆畫與同名辨識 | 桌面及手機 6 項全部通過；`print-a-gates-20261020`，最終版本 |
| Excel 獨立讀回 | 最終 gates 六份 XLSX 全部 PASS；逐格文字、座標、合併、底色、每人一次、純文字儲存格與 A4／fitToHeight=0 |
| Impeccable layout detector | 最終結果 `[]`，無未解釋 layout findings |
| 真 PDF 與視覺 | pdfinfo、pdftotext -raw、Poppler 渲染；主對話另獨立核對 7 頁主樣本字元皆界內、14／16 pt 實際字級及完整資料 |

E2E 使用不同 project／大量真寫入 fixture，連續接在 80 人案例後會觸發既有 429；已分批重新啟動合成 server，沒有更改產品限流。廣泛回歸的手機案例另有未解決印前互動失敗：`局部底色：格位橘底…` 在觸控拖曳預告未出現；`表頭修正：單選工具列…` 在歷史表頭選取；`匯出精修：工具列…` 在 setup merge 回 422。均未進入列印，本輪 diff 不涉及拖曳、歷史控制器或 merge API，未宣稱這三項通過。必要白色／跨頁／排序回歸與手機主樣本已獨立通過。

## 保留成果

`data/print-a-verification-20261020/` 為 ignored 合成證據：

- `members-342.pdf`、`members-342-page1.png`、`members-342-page2.png`：14 pt／12 pt 會員 A。
- `competition-a-80.pdf`、`competition-a-80.png`：16 pt、原格位／合併／素字／底色的比賽 A。
- `management-95.pdf`：正取 80、候補 8、取消 7，兩頁完整。
- `members-450-native.pdf`：長姓名／長註記與原生列印，自然四頁。
- `members-mobile.png`、`mobile-/`：390 px 畫面及手機相同主 PDF。
- `arrangement-extreme-500x50.pdf`、`arrangement-extreme-last.png`、`arrangement-legacy-unknown.pdf`：極端末格與歷史未知。
- `regression/`：歷史、白色 override、跨幅、底色的 PDF／XLSX 與來源 JSON。
- `pdf-pages.json`、`excel-verification.json`、`impeccable-layout.json`：核對收據。

未操作實體印表機，未代表使用者人工接受。工程 freeze 後已完成 snapshot 核對、停寫備份、同 schema 更新與資料保留檢查。

## 實站預覽與合成 PDF 的界線

公開實站只驗證預覽 DOM：會員為 2 個 A4 頁區塊、完整 342 姓名、14 pt；既有 80 人比賽為 1 個 A4 頁區塊、80 個非空人員格、11 個 body 行、4 個雙欄合併格、姓名 16 pt，th／td 四邊均為 1 CSS px。既有部署帳號公開登入、唯讀預覽及登出通過，沒有編輯、保存、拖曳或實際列印。上方實際 PDF 的兩頁／一頁、字元邊界及視覺證據使用合成 342／80 人樣本，不將實站 DOM 頁區塊數當作真實名單 PDF 頁數。

## 2026-10-21：網頁卡片與圈素精修

使用者保留已接受的 A 版 PDF 排版，改回會員網頁的分離卡片：原 `--teal` 深綠白字、12 px 圓角、10 px 級數間距。欄數依視窗 560／800／1050／1280 px 逐步從 1 至 5 欄；卡內兩欄姓名、18 px／手機 20 px、筆畫排序與辨識註記均保留，PDF 會員結構／字級／行高完全未改。

安排與管理名單的人名旁素字改為實線圓形，圈內字最終 12 pt、字重 600，圓徑 16 pt、邊框 0.75 pt，不依賴背景圖形。圖例改為同樣圈素加「素食」，使用獨立 `.print-diet-symbol`，不列入選手 `.print-vegetarian` 計數。四字姓名旁距 2 pt，可與圈素同列，原 16 pt 姓名／38 pt 行高與一頁主樣本均維持。歷史未知餐食沒有新增選手標記。

本輪只改三個產品檔：`styles.css`、`ArrangementPrint.tsx`、`CompetitionManager.tsx`；另擴充既有列印驗證及本紀錄。沒有修改後端、會員排序、比賽格位、保存／歷史控制器、PDF 欄寬、色階或合併。

- `typecheck`、Vite build、`git diff --check`、Impeccable layout detector `[]` 通過。
- 最終 `print-layout.spec.ts --grep '會員A|管理名單列印|比賽A'`：desktop／mobile 共 6 passed，12.1 秒。各含 342 人會員、95 筆管理、80 人安排；安排案例另驗 legacy 未知餐食。
- 390／640／820／1087／1440／1920 px 核對欄數、10 px gap、12 px 圓角、深綠白字、18／20 px 姓名及無水平溢出。
- 背景關閉產生實際 Chrome PDF，會員各兩頁、比賽各一頁、管理各兩頁、legacy 各一頁；八份共 12 頁字元皆界內。Poppler 渲染並檢視圈素與四字姓名、卡片桌面／手機 viewport。未重跑無關後端或手機編輯案例。

定稿資產：`index-D7qiDtYI.css`／`index-Cu8GgTCd.js`。證據保留 `data/print-polish-20261021/`：`desktop/`／`mobile/` 的 PDF、各尺寸 viewport／fullpage 截圖、`desktop/competition-a-80.png`、會員兩頁 PNG、管理第一頁 PNG，以及 `pdf-verification.json`。最終 E2E 原收據在 `frontend/test-results/print-polish-final-20261021/`。本機驗證未操作 Git、Docker 或部署，交原目標對話核對後更新試用站。

### 圈內文字定稿：12 pt／600

主對話檢視紙面後，圈內「素」字由 13 pt／700 調為 **12 pt／600**，圓徑 16 pt、實線 0.75 pt、旁距 2 pt 保持；只變更共用標記的 CSS 字級／字重，沒有更動姓名、表頭或任何 PDF 布局。前一版會員卡片與會員 PDF 證據可沿用。

`print-layout.spec.ts --grep '管理名單列印|比賽A'` 最終 desktop／mobile **4 passed，8.0 秒**；選手與圖例都明確檢查 12 pt／600，80 人一頁、管理 95 人兩頁、legacy 未知一頁，背景關閉仍可見圓框。`typecheck`／build／diff-check 通過。Poppler 渲染並檢視紙面；六份 PDF 獨立讀回全部字元界內，圈內字實際 12.0 pt，安排 27+1、管理 32+1、未知歷史僅圖例 1 個，沒有補造選手餐食。

**最新 freeze 資產**：`index-B3QvLKWe.css`／`index-COwDRJex.js`，取代上一筆 asset 名稱。最新證據 `data/print-circle-type-20261021/`，含 `desktop/competition-a-80.png`、desktop／mobile PDF、`pdf-verification.json`（實際字級 12.0）、`freeze.json`。原測試收據 `frontend/test-results/print-circle-type-20261021/`。未部署。

### 同日部署與公開只讀核對

上句「未部署」記錄工程 freeze 交付時點；其後已於 2026-10-21 台北時間 11:04 完成既有家中試用站更新，現用 `snapshot-a8b9f2243c65a79c`，資產與上述 freeze 逐位元相同。21 表、帳密、原 sessions、業務資料保留及備份通過，詳細來源與回復方案見[家中部署紀錄](home-deployment.md)。沒有 Git／registry 發布。

公開實站只核對預覽 DOM：會員網頁恢復 5 欄深綠分離卡片，10 px gap／12 px 圓角／18 px 姓名且無水平溢出；會員預覽為 2 個頁區塊、342 姓名、14 pt。原 80 人安排預覽保留 1 個頁區塊、80 個人員格與 4 個雙欄合併，實際可見 2 個選手圈素及 1 個圖例圈素；圈徑 16 pt、字 12 pt／600、框線 0.75 pt、50% 圓角，姓名 16 pt，所有 th／td 四邊皆為 1 CSS px（0.75 pt），圖例只圈素加「素食」。既有帳號公開登入、只讀及登出通過，沒有編輯、保存、拖曳或實際列印。

實站的頁區塊數不是實際 PDF 頁數；真 PDF 頁數、字級與字元邊界使用上節合成樣本驗證。公開收據與兩張截圖位於 ignored `data/deployment-20261021/cards-vegetarian-home/`：`public-browser-verification.json`、`public-members-cards.png`、`public-competition-circle.png`。

### 人名旁圈素垂直對齊定稿

使用者接受其餘卡片與 PDF 樣式後，只將人名旁 `.print-vegetarian` 視覺上移 **3 pt**（`translateY(-3pt)`）；不改行盒尺寸，不移動已對中的圖例。圈內字 12 pt／600、圓徑 16 pt、實線 0.75 pt、旁距 2 pt 皆保持。前一版紙面量測首個四字姓名字形中心約 y=160 pt、圓心約 y=163.9 pt；修正後圓心與姓名中心接近，沒有改成上標。

`typecheck`／build／diff-check 通過。80 人／管理 95 圈素 desktop／mobile **4 passed，6.9 秒**，含四字姓名與 legacy 未知餐食。Poppler 紙面已檢視；六份 PDF 逐字位置比對確認所有非標記文字的座標／字級完全相同，只有選手圈素字向上 3 pt，圖例維持原位；安排各一頁、管理各兩頁、legacy 各一頁，所有字元皆界內。

**最新 freeze 資產**：`index-PsSUwEnH.css`／`index-tvNyHE5u.js`，取代前筆。證據保留 `data/print-circle-align-20261021/`：`desktop/competition-a-80.png`、desktop／mobile PDF、`pdf-alignment-verification.json`、`freeze.json`。未修改版號、README、部署文件，未操作 Git／Docker／部署；由原目標對話視覺核對後進行已授權 release。

## 0.4.1 最終發布驗證與 Vite 最小安全修補

發布前 npm audit 的 Vite 相關弱點阻擋檢查，依[官方安全公告 GHSA-698v-4r3x-3vcv](https://github.com/advisories/GHSA-698v-4r3x-3vcv)及[Vite 7.3.7 官方版本](https://github.com/vitejs/vite/releases/tag/v7.3.7)，只精準鎖定 `vite: 7.3.6 → 7.3.7`；未使用 `npm audit fix --force`，沒有升級其他 npm／Python 套件版本，也沒有修改已接受的產品樣式或邏輯。

`package-lock.json` 逐筆比對確認只有 `node_modules/vite` 的 version／resolved／integrity 改變；npm 另外移除六筆 `peer` 分類 metadata（含 Vite），沒有其他套件版本、下載來源或 integrity 變動。原 root 版本 0.4.1 保留。產品 CSS／App／安排／管理列印來源的 SHA-256 與修補前完全相同。

- `npm ci --no-audit --no-fund` 成功；獨立 `npm audit --audit-level=high --json` 成功，info／low／moderate／high／critical／total 全為 **0**。
- `npm ls --depth=0`、typecheck、Vite 7.3.7 build、`git diff --check` 通過。
- 最終 `print-layout.spec.ts --grep '會員A|管理名單列印|比賽A'` desktop／mobile 共 **6 passed，11.9 秒**，含完整 342 人、長名／長註記 450 人、95 筆管理、80 人四個 merge／27 圈素，以及 legacy 未知餐食。
- 十份實際 PDF 共 20 頁，逐字座標／字級與修補前完全相同、所有字元界內：會員 342 各兩頁、450 各四頁、安排各一頁、管理各兩頁、legacy 各一頁。Poppler 紙面重新渲染並檢視。
- 原目標對話執行同版 0.4.1 後端全套：**257 passed，67.49 秒**，兩則既有 deprecation warning；`uv lock --check --offline` 通過。本次不重跑後端或無關手機編輯案例。

**最終發布 freeze**：Vite 7.3.7 重建仍產生 `index-PsSUwEnH.css`／`index-tvNyHE5u.js`。證據保留 `data/print-release041-final/`：`npm-audit.json`、`lockfile-diff.json`、`source-before.json`、`freeze.json`、`pdf-verification.json`、desktop／mobile PDF／截圖與紙面 PNG。原 E2E 收據 `frontend/test-results/print-release041-final/`。本段只記錄實作與本機驗證，Git 合併／推送／版本映像發布／部署由原目標對話接續執行。
