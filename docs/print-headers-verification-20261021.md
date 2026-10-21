# 列印表頭與格線驗證（2026-10-21）

0.4.2 候選起點為 `dfa0ef3270a66f15fb2e809e9a4783b08fe4e419`。修正真正列印時的會員表頭底色與表頭／資料格線；網頁卡片、筆畫排序、比賽格位／合併／歷史語意與圈素位置保留。沒有後端、DB、migration 或依賴升級，自身版本同步0.4.2。正式 Git／映像發布及試用站部署已完成，身份見文末紀錄。

## 問題與做法

原版實際 Chrome PDF 在背景圖形開啟時，每頁有五塊 `#f0f3ee` 會員表頭；關閉時零塊，新增檢查對原版兩頁明確報 FAIL。改用既有 SVG 前景填色、th 背景透明，因此背景關閉仍保留淺綠色。

使用者 Chrome／Edge 截圖經量測確有同一格線表頭1px、body2px的差異；原圖／真實姓名未存入 fixture 或 Git。Linux Google Chrome **155.0.8059.79**（Playwright `channel=chrome`）的 headless PDF，即使模擬甲乙丙丁四組雙欄表頭，也未重現原生預覽的半寬線；不宣稱已完整重現所有原生繪製根因。本機另重現 collapsed-border 在續頁表頭與資料列碎片間疊成1.5pt。

最終採零間距、單側右／下邊框，table 提供左邊、thead 首列 th／td 提供上邊，全部 **0.75pt／#68736d**，沒有 pseudo 疊線；移除舊 override。列印 `tr {break-inside:avoid}` 讓一般列整列換頁，過高單列仍由瀏覽器處理。會員14pt／21.5pt行高、比賽16pt／38pt行高及圈素12pt／600／上移3pt未變。

## 最終結果

- typecheck、Vite7.3.7 build、diff-check、離線 uv lock 通過。lock 僅自身版本0.4.1→0.4.2，依賴未變。主對話本輪 audit 合計0，收據 `data/release-0.4.2/npm-audit.json`。後端未變，未重跑全套。
- 必要既有 E2E 共 **10項通過**：桌面／手機列印6項（13.5秒）、跨行合併／歷史／寬長表1項、表頭色階／白色覆蓋／跨幅合併3項（新server9.1秒）。80人案例先跑後曾使後三項受累積寫入限流污染（含明確429）；保留失敗收據，隔離新server後成功，未調限流或產品互動。
- 背景 on/off 主樣本 **20份PDF、40頁**：342人會員各2頁、450人長名／長註記各4頁、95筆管理各2頁、80人安排各1頁、legacy未知各1頁。所有字元在紙內，字元與字級清單和原版相同。342／80／legacy文字座標最大差0.75pt；450／95因整列換頁調整續頁起點。
- 實際 PDF **11,732條格線**的向量厚度均0.75pt，Poppler576dpi的連續同色run均 **6px＝0.75pt**；每個會員表頁五塊、管理表頁十塊實體淺綠填色，背景開關一致。450最後一頁只有註記，沒有表格。另七份色階／白覆蓋／rowspan等PDF共20頁、1,962條線也同為0.75pt／6px。
- Poppler PNG實際檢視通過：342／80主表、450／95重複表頭與首列分界、外框及跨行合併續接。寬長案例四個邏輯分幅自然成六張紙，選手不重複、rowspan外框保留。主對話也核對主樣本與續頁通過。

80人 fixture 為12行9欄、四個分組merge加四個備註merge。測試標題在通過後純更名為「分組與合併格」，既有收據路徑保留，不影響行為證據。

## 重跑與證據

隔離成品 `frontend/dist-print-headers`、port8071、`data/print-headers-e2e.db`，沒有覆寫舊dist／DB。QA根目錄 `data/print-headers-20261021/`：

- `accepted-final/`：最終桌面／手機PDF及截圖；`accepted-renders/`：紙面PNG。
- `accepted-regression/`：通過的跨行合併及該批限流失敗收據；`accepted-colors/`：後三項新server成功收據。
- `accepted-final-pdf-check.json`、`rowspan-pdf-check.json`、`colors-pdf-check.json`：向量／像素／表頭下緣存在性；`baseline-members-defect.json`：原版失敗；`text-position-comparison.json`：原版文字比對；`freeze.json`：來源及資產SHA-256。

既有 E2E 命令加 `FUCHENG_PRINT_HEADER_QA=1` 可產背景on/off配對。使用含 pdfplumber／Pillow 的 bundled Python執行：

```sh
python scripts/verify_print_headers_pdf.py data/print-headers-20261021/accepted-final
```

檢查從實際向量中心量測連續像素，抓半寬與相接雙粗線，另驗表頭下緣存在，避免只查已有線而漏過缺線；失敗輸出可讀JSON並非零退出，`--baseline`可保存失敗紀錄。實體印表機、使用者原生Chrome／Edge系統列印對話框及真機結果仍待人工核對，本機PDF證據不代替該層驗收。


## 工程 freeze 後的正式發布與部署

[PR #22](https://github.com/momonong/fucheng-players-system/pull/22) 已合併，正式來源 `08b12bff6a8976434b55300f7cb1d9f1dde9e3b0` 的 0.4.2 已發布並於 2026-10-21 台北時間 17:21 更新既有試用站。映像資產與本輪 freeze byte 一致，資料保留、登入與新版備份檢查通過。詳見[正式發布結果](release-0.4.2.md#正式發布與家中試用站2026-10-21)及[家中部署紀錄](home-deployment.md#042-列印表頭與格線部署2026-10-21)；不將部署成功等同使用者原生列印或實體驗收。

原目標對話另以公開網址核對會員及現有會內賽 DOM 預覽：342 位會員／兩頁／十個 SVG 淺綠表頭、80 人安排／一頁／四個雙欄分組及兩個圈素；14 pt／16 pt 字級、圈素上移 3 pt 與 0.75 pt 共用格線維持。登入、唯讀檢視與登出完成，沒有編輯業務資料。公開截圖及非秘密量測收據在 `data/release-0.4.2/public-browser-verification.json`；真實名單未加入合成測試或 Git，原生系統列印限制維持上述範圍。
