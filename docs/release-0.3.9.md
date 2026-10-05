# 0.3.9：各場級數欄可自由刪除與加回

## 行為與保護

- 空的1–10級欄可從欄邊 ⋯ 刪除；有選手時先移走再刪，至少保留一個級數欄。含文字仍須確認，原合併內容、底色及穩定格位處理沿用。
- 表格上方可加回已移除的級數，放在最右側；新正取、候補遞補、調級及移到欄底用到缺少級數時，在原寫入交易補回。讀取不擅自改表。
- 刪欄不刪會員或報名，不改其他選手的級數、位置與版本。復原／重做、衝突核對和原請求重送沿用。
- 表格不再強制保留十欄寬度；保存、歷史、列印及 Excel 都呈現實際欄位。舊十欄資料不自動改寫。
- Python／npm 同步0.3.9，依賴及資料表 schema `0010_deployment_report` 不變；同一映像支援根路徑與 `/fucheng/`。

## 驗證

沿用相同功能來源已通過的後端完整217項，加上候補遞補補測1項；桌面／手機新流程2項通過，涵蓋刪除、有人的欄保護、加回、保存、重載、歷史唯讀、列印與匯出。Excel及PDF另解析確認僅保留1、3–10級九欄且包含合成選手。來源與限制詳見 [功能驗證](flexible-level-columns.md)。

升版後 locked sync、TypeScript／build、npm audit與映像 root／prefix 驗證結果記入發布紀錄。建置採 allowlist staging，不包含資料、帳密、備份或舊成品；沒有宣稱 GitHub Actions 執行測試或手機真機人工驗收。

## 發布與部署契約

使用者授權先合併推送、發布v0.3.9與Docker Hub `0.3.9`／`latest`，再更新4090。部署仍需停寫、成組備份與逐表資料指紋核對，HP入口及其他服務保持既有配置。實際結果見 [家中部署紀錄](home-deployment.md)。

**精簡欄位使用後不可直接降回仍強制十欄的舊app**，即使資料表schema相同也不代表相容。新版啟動後發生失敗時，不自動降回舊image覆蓋新操作；保留資料、先排查與向前修復。需要還原時沿用匹配備份／新目標及保留故障資料的維運程序。


## 0.3.9 級數欄自由調整部署（2026-10-05）

先合併 [PR #16](https://github.com/momonong/fucheng-players-system/pull/16)，推送版本標籤並發布 [v0.3.9](https://github.com/momonong/fucheng-players-system/releases/tag/v0.3.9) 與 Docker Hub `0.3.9`／`latest`，再更新 4090 既有 `fucheng-home` app／backup。空級數欄可刪除並加回，含選手先移走；保存、歷史、列印與 Excel 依實際欄位呈現。

- 合併／tag／映像來源：`cce12db6a327892b6b703c0fda6cefefcecb524d`。
- Digest：`sha256:72a8582278bd6412432a1e32ec265c2018215053660defd13dccaba32dca8262`；image ID：`sha256:eb2e876eb3420adbbd2a385578941be067f8c5ef844d07a56cf78f4376251ce4`。兩個 Docker Hub tag 的 digest 相同，遠端 config digest 與拉回 image ID 均核對相符。
- Source manifest：`c0b1f7d9f16422b811c1a77036f0ab06f52e37f823c6581e9e67e13e918900dc`，75 個 allowlist 檔案；context audit 通過，無資料、秘密、備份或舊成品。
- 後端完整217項＋候補遞補補測1項、桌面／手機新流程2項及匯出／PDF解析證據沿用相同功能來源。升版 locked sync、typecheck／build 通過，npm audit 0 vulnerabilities；映像 JS/CSS 與上述 E2E 成品逐位元相同。
- 根路徑及 `/fucheng/` 獨立合成映像測試均通過 health、登入登出、Cookie 路徑、匿名拒絕、資產一致性、空級數欄刪除／加回與資料完整性。首次子路徑測試遇 Docker 預設地址池耗盡，核對網路後改用本次專屬10.203.39.0/24及10.203.40.0/24重驗；保留既有網路／volume，不 prune。測試 app 已停止。
- 更新前正常停止 app／backup，以舊 runtime 成組 backup／export，archive及成員 hashes 全通過。停寫 checkpoint：`manual-export-20261005T091651591832Z-b3408121.db`；私密備份、舊 env 及證據留在 ignored `data/release-0.3.9/`。
- 原 `fucheng-home_data`／`fucheng-home_home_backups` 保留，無 migration或reseed；schema `0010_deployment_report`、integrity ok、FK error 0。16張業務表完整內容 fingerprint 不變，342會員、2場次、81報名、3安排保存版、45安排操作及2公告保留。
- app／backup 同一新 image ID 且 healthy，備份健康正常。可信 loopback 管理員登入／讀取／登出、Secure/HttpOnly前綴Cookie、匿名401、錯誤Host400及裸API404通過。HP Caddy 根首頁、OrderFlow、府城首頁及health均200。
- 公開HTTPS瀏覽器載入新版 `index-DvG74ytG.js`／`index-DKqNSIay.css`、首頁、342位會員與管理員登入表單。未在真實資料測試刪欄／調級；公開登入後操作與手機真機手感仍待使用者驗收。
- 4090轉送、HP Caddy／cloudflared／OrderFlow轉送 active。Caddy SHA保持 `0e9b6473c465309ea5fad4dde547b9f286d3a363acd69142a3bd3157505da209`；無入口、DNS、SSH、其他應用或ASUS變更，服務目錄沿用。

精簡欄位開始使用後，不可因schema相同就直接降回強制十欄的舊app；新版啟動後不自動降版，先保留資料排查並向前修復。必要還原使用匹配備份與新目標，保留後續操作及故障庫。帳密沿用；同機備份仍不代表異地備份。
