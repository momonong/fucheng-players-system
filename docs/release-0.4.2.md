# 0.4.2：保留列印表頭底色與一致格線

會員及管理名單的淺綠表頭改用實體 SVG 前景填色，瀏覽器關閉「背景圖形」時仍保留已接受的 `#f0f3ee`。比賽與名單共用的列印表格改採零間距、單側邊框，保留 0.75 pt 格線；一般資料列整列換頁，避免 Chrome 合併邊框與列碎片在重複表頭邊界疊粗、缺線或裁切。較高的單列仍由瀏覽器自然處理分頁。

原會員 14 pt、比賽 16 pt、圈素 12 pt／600 及上移 3 pt 保持；342 人會員兩頁、80 人安排一頁，95 筆管理名單兩頁。會員網頁深綠卡片、筆畫排序、比賽實際格位／合併、色階、白色覆蓋與歷史未知語意均保留。沒有 API、資料庫、migration 或套件依賴升級；Python／npm 自身版本同步為 0.4.2。

本機工程與實際瀏覽器 PDF 證據、Chrome／Edge 原生列印預覽的驗證限制見[本次驗證紀錄](print-headers-verification-20261021.md)。正式來源已合併、標記並發布；既有家中試用站已更新，實際身份與資料保留結果見下文。


## 正式發布與家中試用站（2026-10-21）

[PR #22](https://github.com/momonong/fucheng-players-system/pull/22)、`v0.4.2` tag／[GitHub Release](https://github.com/momonong/fucheng-players-system/releases/tag/v0.4.2) 指向 `08b12bff6a8976434b55300f7cb1d9f1dde9e3b0`。79 檔 allowlist context、source manifest `92c4bde59dd918f75707a43096c151248ab616cc0922c46187ab252ae46c9e0a`、root／prefix 合成 smoke 及最終 CSS／JS byte 比對均通過。

Docker Hub `0.4.2`／`latest` registry manifest digest 同為 `sha256:faaa578ad5fa48a642f6ee80892986b20af82286111bf9f1f5309556236752cd`（Docker manifest v2、linux/amd64，無額外 index）。Pinned pull 的 config/native image ID `sha256:0bb6bdcdfab16b0c627589cd895f140bd3bd52ccbf1358b085d0748361e2d46f` 與通過測試的映像一致；manifest/index 與 config digest 分開記錄。

家中試用站於台北時間 17:21 同批更新 app／backup 至該固定 registry digest，兩者 healthy。升級前以舊 runtime 成組備份並驗 archive hash，登入前 21 表全值（含帳密及原 sessions）相同；登入／GET／登出後 18 業務及管理表仍相同，新備份通過。無 migration、真實業務修改或入口變更，原 volumes、env、0.4.1 映像與備份保留。回復方式與完整受限證據見[家中部署紀錄](home-deployment.md)及 ignored `data/release-0.4.2/`。公開 DOM 預覽、合成實際 PDF 與原生系統列印／實體驗收分層記錄；球館 Windows 不在本次部署範圍。
