# 0.3.5：素食名單欄名／隊名與管理列排版

素食名單入口改成疊在「素食 x 人」按鈕右上角的 28px 小圓形，保留 44px 觸控區與主按鈕文字間距。點主按鈕切換高亮，點圓形開名單，避免誤觸與大型並排圖示。

- 名單顯示姓名／同名辨識、本場級數、實際多層欄名及隊名。支援管理員自訂表頭、合併表頭、跨列合併隊名，以及文字位於合併區非起點的布局。
- 管理員隊名優先：取同列左側最近的非空文字欄，沒有才找右側。一般級數格備註不當隊名。
- 沒寫隊名時，以同列最高當次級數選手當隊長，1 級最高、沒有則依序往下；取姓名末兩字加「隊」，例如周文軒 → 文軒隊。只推導顯示，不回寫資料或建立分隊。
- 搜尋不裁素食名單；歷史只讀當時保存的 rows/layout。之後移動／改名不改舊版，缺格位或餐食不補現在資料。
- 備份狀態和管理員名稱整組靠右，維持備份在左、名稱在右。手機容器使用完整可用寬度，避免只對齊內容區。

## 驗證與限制

純解析 5 項、手機多層名單／歷史／拖曳及桌面工作流程通過；最後靠右調整另驗桌面與手機，360–1440px 無頁面溢出。全後端 211 passed（2 個既有棄用警告）、Production build／TypeScript、npm high audit（0 vulnerabilities）與 diff check 通過。獨立唯讀審查發現並修正觸控區覆蓋主按鈕文字的問題。完整證據見 [驗收紀錄](acceptance.md)；Chromium 觸控模擬不等於 Android／iPhone 真機接受。

## 發布、升級與搬移

Python／npm 版本同步 0.3.5，依賴與後端 schema 未變，無 migration。以乾淨已提交來源、allowlist staging 及 source manifest 建置 Linux/amd64 image，排除資料、秘密、備份與既有 dist。

先合併推送 GitHub、發布 v0.3.5 與 Docker Hub `0.3.5`／`latest`，核對 registry digest，再升級既有 4090 `fucheng-home`。升級前停寫，透過 runtime 建立成組備份／export 並核對 hash；app／backup／ops 同批固定新 digest，保留帳密、原 volumes、舊映像與回復資料。部署後核對健康、業務資料指紋、登入／Cookie、資產及公開入口。

根路徑與 `/fucheng/` 由 runtime 設定，同一 image 可用於球館 Windows Docker Desktop／WSL2；搬移仍須按場域設定 origin／入口並還原成組備份。實際部署結果見 [家中部署紀錄](home-deployment.md)。
