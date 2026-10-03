# 0.3.3：手機與桌面管理流程

管理員在小螢幕不必依靠拖曳精確格位完成日常安排：900px 以下預設名單操作，桌面預設完整表格，兩者可手動切換。

## 功能與修正

- 選手點選面板提供當次資料、歷次級數，以及交換、前後插入、空格移動與移至欄底；確認前顯示影響預覽。同名選手仍依報名 ID 識別。
- 所有操作共用原有安排控制器、版本／token、CSRF、receipt 與稽核。結果未知保留原 request ID／payload；外來更新以 409 拒絕，不自動覆寫。Undo／Redo、完整保存、歷史、列印及 Excel 沿用既有流程。
- 會員與公告在小螢幕採清單／編輯兩頁，返回及旋轉畫面保留目前輸入；報名管理使用觸控卡片與原生 modal。桌面表格及精確文字／合併／底色操作保留。
- 修正成功提示遮擋手機導覽、名單歷史面板高度，以及切換模式時隱藏文字編輯器意外保存。草稿不是跨重新整理的離線儲存。

## 驗證與限制

- TypeScript、正式建置與 npm high audit 通過（0 vulnerabilities），未更換依賴。
- 核心桌面／觸控流程根路徑 8 passed、`/fucheng` 8 passed。
- 既有回歸 22 個隔離批次共 38 passed，另補文字編輯 2 passed；涵蓋 360–1440px、報名／候補、會員、公告圖片、格位手勢、保存與輸出。
- 為避免合成測試大量請求觸發正常限流，採新服務程序分批驗證；不宣稱單次全套 E2E 通過。全部為合成資料；手機真機、軟鍵盤與手感待管理員驗收。

## 部署相容性

版本同步更新 Python 與 npm metadata 至 0.3.3；無後端、migration 或依賴變更，schema 維持 `0010_deployment_report`。使用 allowlist staging 與逐檔來源 manifest 建置 Linux/amd64 單一 app image，不包含資料、帳密、備份或工作目錄的既有 dist。

家中沿用 4090 Docker、`https://momonong.me/fucheng/` 與既有 HP 入口；日後球館 Windows Docker Desktop／WSL2 可拉取相同映像，以 `FUCHENG_BASE_PATH` 切換根路徑。資料另經成組備份／還原搬移；部署前先備份，同批替換 app／backup／ops。詳見 [部署文件](deployment.md#033-發布與升級)。

GitHub 合併、tag/release、Docker Hub digest 與線上部署是各自驗證步驟；完成證據另存於日期化部署紀錄。
