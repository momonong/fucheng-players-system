# 列印表頭與格線驗證（2026-10-21）

0.4.2 候選起點為 `dfa0ef3270a66f15fb2e809e9a4783b08fe4e419`。修正真正列印時的會員表頭底色與表頭／資料格線；網頁卡片、筆畫排序、比賽格位／合併／歷史語意與圈素位置保留。沒有後端、DB、migration 或依賴升級，自身版本同步0.4.2。Git／映像發布／部署待原目標對話接續。

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
