# 手機與桌面管理流程

## 2026-10-04 手機表格修正（本機候選）

使用者真機回饋否決 0.3.3 的「名單操作」：需要直接在安排表內移動人員，且觸控拖曳不可被右鍵選單遮住。本輪移除替代名單與模式切換，沿用同一格位表、安排控制器、資料與權限。尚未發布或部署；線上仍是 0.3.3。

### 互動與驗收契約

- 手機直接顯示安排表。滑動姓名區可原生捲表；專用 ⠿ 把手至少 44px，按住後直接拉動，不等長按。移動超過 6px 才成為可提交拖曳；單純點把手不寫入。900px 以下加寬表格欄位及提供操作提示。
- 手機（窄畫面或最近輸入為 touch）的 contextmenu 只阻止瀏覽器選單，不開儲存格／表頭／軸選單。明確 ⋯ 仍可開啟工具；桌面滑鼠右鍵、Shift+F10 保留。拖曳中各選單關閉且不能重新開啟，避免遮擋落點。
- 拖到選手中央交換，上下邊界插入，空格直接移動；放手僅提交已顯示的預告。取消、失去 capture、第二指介入或 Escape 不提交。起拖保留原 token；外來變動以 409 拒絕。未知請求仍保留固定 request ID／payload，不能自動覆寫或重新計算目標。
- 保存、Undo／Redo、歷史唯讀、列印與 Excel 使用原本契約。文字／合併／底色及行列工具保留。會員與公告的手機清單／編輯頁、報名觸控面板也保留。
- 管理員名稱移到帳號工具列下方，與備份狀態同列、位於其右側；備份狀態尚未取得時仍顯示名稱。
- 素食按鈕右上角的名單圖示開啟唯讀名單，顯示「當次級數・隊長・姓名」。姓名相同時附辨識註記；依 registration ID 對應，使用本場 diet，不受搜尋或素食高亮開關裁減。
- 隊長暫按「同一 stable row 的固定 1 級欄選手」推導，已向使用者提出確認問題、尚待回覆。空的 1 級格標「隊長未安排」，位置未知標「隊長未知」。歷史使用所選版 rows/layout；layout=null 不從目前安排或 legacy 顯示表推定隊長，diet=null 不補現況。

### 根因與協作審查

舊把手要求靜止 350ms，提前移動超過 8px 即取消，迫使用戶長按；把手 contextmenu 只 preventDefault，仍冒泡到 td 開啟選單。body portal 選單攔住 elementFromPoint，拖曳無法命中被遮住的格位。原測試等待 ghost 後才移動，未覆蓋快速起拖與 contextmenu。

回歸另捕捉到 Chromium 在失敗恢復後收到兩次 touch pointerdown/up、卻省略第一次 compatibility click。手機姓名改由未移動且未取消的 pointerup 計算單／雙點，略過 touch compatibility click；原生滑動、第二指及 cancel 會清除計數。桌面仍使用 click/dblclick。

本對話負責實作及整合，獨立唯讀 subagent 核對根因、事件隔離及資料邊界。審查另發現拖曳時 Shift+F10 可能留下延後開啟的選單，已將禁止開啟的檢查加入共用入口；軸選單測試也檢查其實際 group 面板。

驗證使用獨立 `frontend/dist-mobile-grid-touch`、`data/mobile-grid-touch-20261004-e2e.db` 及獨立 loopback ports；不用真實資料、不覆寫正式 image／預覽成品。結果見 [驗收紀錄](acceptance.md)。Chromium touch 事件、contextmenu 注入與視窗尺寸測試不等於 Android/iPhone 真機；Safari 原生長按、軟鍵盤及操作手感仍待驗收。

## 0.3.3 歷史交付

0.3.3 曾加入手機「名單操作」與桌面表格切換、會員／公告草稿保留及報名面板。當時 typecheck、production build、npm high audit 通過；核心根路徑 8 passed、前綴 8 passed，22 個隔離回歸批次共 38 passed，文字編輯另 2 passed。這些是舊版工程證據，不能取代本次真機問題修正的驗收。

[0.3.3 發布說明](release-0.3.3.md) 與 [部署紀錄](home-deployment.md) 保留歷史。沒有 APK／PWA 快取或資料庫 migration；重新整理或離開頁面後的永久草稿儲存不在功能範圍。
