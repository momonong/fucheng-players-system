# 0.4.1：清楚的會員分級與比賽列印

會員分級表與比賽名單改用 A4 橫向預覽／列印，優先保持清楚字級和上下留白，內容較多時自然分頁。會員姓名 14 pt、比賽安排姓名 16 pt，表格所有內外格線統一 0.75 pt；合成 342 人會員分兩頁、80 人比賽一頁、95 筆管理名單兩頁。較長姓名、註記或較大布局可增加頁數，不縮小字體。

會員網頁保留原深綠白字，各級以緊湊卡片及小間距分開，依螢幕寬度呈現 1–5 欄。移除各級人數，保留總人數；會員名單及列印依姓名筆畫排序，同名以辨識註記及 ID 穩定排序。比賽名單、候補及原安排格位不重排。

素食以圈「素」標在姓名右側；圈徑 16 pt、圈內字 12 pt／600，姓名旁標記上移 3 pt 以接近視覺中央，圖例為同樣圈素加「素食」。保留當次餐食與歷史未知語意、所有原格位、合併、色階及明確白色。Excel 保持可編輯，A4 橫向一頁寬、高度自然分頁。管理員登入按鈕與密碼欄間距調整為 16 px。

Python／npm 版本同步為 0.4.1；發布前 audit 發現 Vite 相關弱點，僅將 Vite 7.3.6 精準更新至 7.3.7 最小修補版（[安全公告](https://github.com/advisories/GHSA-698v-4r3x-3vcv)、[官方版本](https://github.com/vitejs/vite/releases/tag/v7.3.7)），其他 npm／Python 依賴版本未變。沒有新增 migration，schema 仍為 `0011_admin_management`。同一 Linux/amd64 image 支援根路徑及 `/fucheng`。既有部署先停寫、以原 runtime 成組備份，再同批更新 app／backup；原資料、帳號及 volume 保留。球館 Windows 部署仍待方便重開機時進行。

乾淨 `npm ci`、`npm audit --audit-level=high` 通過，所有嚴重度合計 0 個弱點。驗證包含 typecheck／build、既有後端、桌面與手機列印、筆畫排序、歷史凍結、白色 override、跨幅合併與 XLSX 讀回。0.4.1 後端全套 257 項通過；Vite 7.3.7 最終六項桌面／手機列印測試通過（11.9 秒），十份實際 PDF 的頁數、所有文字位置與字級皆與已接受版相同。完整證據與先前廣泛手機編輯測試的已知限制見[列印驗證紀錄](print-layout-verification-20261020.md)。未把該三項印前互動失敗宣稱通過；本次不改其拖曳／歷史控制器或 merge API。

版本標籤、建置來源與 Docker Hub digest 以 [GitHub 發布頁](https://github.com/momonong/fucheng-players-system/releases/tag/v0.4.1)的實際結果為準；現站更新另記於[家中部署紀錄](home-deployment.md)。GitHub 沒有 CI workflow，列出的檢查為本機及隔離合成驗證。使用者已接受表格設計；實體列印、手機真機及球館 Windows 尚未驗證。
