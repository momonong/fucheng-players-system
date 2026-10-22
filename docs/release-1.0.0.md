# 1.0.0：第一版正式版本

使用者已確認目前網頁效果可作為第一版，將0.4.6的既有功能提升為1.0.0正式版。本次只調整專案自身版本與發布文件，功能及依賴不變。

## 功能範圍

- 球館首頁、圖文公告、公開會員分級與免登入選名報名。
- 管理員、會員、比賽及報名管理；安排表格以邊界「＋」新增空白欄，普通欄只移動位置、既有級數欄維持本場調級。
- 完整安排保存、唯讀歷史、復原／重做、列印與Excel匯出；公告支援公開／置頂、圖片及可還原刪除。

## 相容與現站

SQLite維持`0013_announcement_deletion`，安排layout JSON維持schema 2，沒有migration。資料、帳號、媒體及既有布局不因版本提升改寫；schema 2仍須搭配相容前後端，回復沿用匹配映像／備份及保留故障庫的既有流程。

2026-10-23 台北時間 00:43:14 已部署至既有 [momonong.me/fucheng/](https://momonong.me/fucheng/)，只更換映像，沒有 migration；app／backup 健康；更新前成組備份與 22 表所有欄位、帳號及媒體核對一致，原帳號 HTTPS 登入／讀取／登出後 19 張非認證表仍相同，既有報告與新版備份驗證通過。公開頁面與 JS／CSS 核對正常，瀏覽器首頁與 342 位會員名單顯示正常。詳見[家中部署紀錄](home-deployment.md#100-第一版正式部署2026-10-23)。版本與映像識別見 [GitHub Release v1.0.0](https://github.com/momonong/fucheng-players-system/releases/tag/v1.0.0)與 [Docker Hub 1.0.0](https://hub.docker.com/r/momonong/fucheng-players-system/tags?name=1.0.0)。

## 驗證界線

本次版本與鎖檔核對、離線`uv lock --check`／`uv sync --locked`、前端typecheck及build通過。三份前端成品的檔名與SHA-256全部等於0.4.6，依賴及其他套件版本未變，包含`colorama`仍為0.4.6。受限實證保存於ignored `data/release-1.0.0/`的`version-lock-verification.json`、`python-lock-validation.json`、`frontend-build-validation.json`及`frontend-static-equality.json`。

可重用的歷史工程證據：0.4.5後端300項通過、6項因缺PowerShell略過；0.4.6隔離桌機／觸控、根路徑／子路徑E2E共8項通過。本次未重跑完整後端或E2E。

使用者對目前網頁效果的確認不涵蓋球館Windows、實體手機／印表機、真正Turnstile報名與斷電／重開機驗收，這些仍待現場核對。
