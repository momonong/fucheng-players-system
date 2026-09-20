# 驗收證據與限制

最後更新：2026-09-21。自動測試與功能驗收資料均為合成資料；經使用者明確授權的本機初始會員與 9/20 圖片案例只保存在 Git 忽略的資料庫、轉錄與對照報告中。

2026-09-21階段A Git交付範圍：緊湊表格、完整安排保存／唯讀歷史、0007、必要測試與部署接續文件，共33項來源變更；從 `0970af2` 整合至main並正常推送，沒有納入後續B需求。整合核對48個應用來源與3個runtime靜態檔仍符合公開驗證身份，沿用下述101項後端、final affected 39項及22項E2E與公開80人證據，不形式重跑。DB、帳密、成品與ignored launcher不進Git；未執行的Docker drill仍僅為準備腳本。以下「未提交」及資源狀態均保留為各次驗證當時紀錄，最新Git身份以交付commit／main／origin/main核對為準。此Git交付不重啟預覽、不改資料／帳密／session，也不是正式部署或Docker hold解除。

## 緊湊級數表格與完整安排版本（2026-09-20，取代下方 A+B 使用方式）

本輪工程驗證完成，等待使用者人工驗收；新功能已提供獨立原生HTTPS合成入口，舊Docker環境尚未更新。排級數以1～10橫向欄、低列高姓名格呈現，正取以外資訊及比賽設定移至「報名與設定」。移動不需要原因，逐次稽核留實際admin／時間／前後值；起始基準只建立一次，大存不可變完整快照、可選版本名稱／顯示編輯者／備註、server秒時間。現在工作對最新保存版、歷史對直接前版，新增／移出依報名ID辨識；不把報名快照當上版。公開資料與其他管理操作原因限制不變。

既有ngrok合成預覽的Docker升級於2026-09-20 14:34台北因共用Docker不可用而hold：ps API500、version兩次unable to start；當時舊公開health404、8448/8450逾時，8039仍200。沒有build／volume操作／migration／舊env變更或重啟共用服務。離線allowlist與指定合成0006備份已核對；`deployment_arrangement_drill.py`只有py_compile／--help通過，**不是遷移或回退已驗證**。證據 `data/deployment-ngrok-r11-evidence-20260920/preflight-blocked.json`；r11 image／Docker演練仍未執行。其後另獲授權建立下列原生入口，不代表解除Docker hold。

原生公開合成驗收（2026-09-20 22:44～22:52台北）：

- [公開新版安排管理](https://f9d0-140-116-158-107.ngrok-free.app/admin/competitions) 正常TLS載入、登入與health JSON200。首次ngrok提示可按Visit Site，未略過TLS驗證。獨立 `data/arrangement-native-preview.db`、0007、83合成會員／3場／85報名，主場80正取；未讀取或複製真實資料／舊volume。初始Backup API備份還原與Alembic metadata check通過。
- 已驗證48個應用來源及3個靜態檔SHA，從 `frontend/dist-arrangement` 複製到獨立runtime/static，沒有重建舊成品。browser公開驗收沿用已驗證核心程式，不形式重跑既有全套測試。
- CUA真實瀏覽器桌面1440×900：80人十欄、拖曳不問原因、自動儲存、重載仍為1→4；回基準清色且無淨差不能大存。第一次採預設「版本 1」、登入帳號作顯示編輯者、空備註；保存後清色。再拖4→6按上一保存版顯色。
- 手機viewport390×844：搜尋圖示展開、按辨識註記縮至1人，表格寬1100px、捲至最右第10級，頁面無水平溢位。手機尺寸完成第二次保存，自訂「公開驗收版本 2」／「合成現場編輯者」／備註；保存後清色。實際操作帳號仍獨立列出levels-preview-admin。這是桌面瀏覽器尺寸模擬；未宣稱實體手機或本次觸控長按已驗證，既有touch E2E證據仍見下方。
- 歷史第二版相較前版4→6，第一版相較起始基準1→4，皆完整80人、唯讀；回目前安排保持6級及無淨差。時間顯示至秒（基準22:43:31、第一版22:48:26、第二版22:49:45）。三版各80列；基準在首次合法合成調級前實際建立，沒有偽造過去基準。
- DB只讀核對：歷史瀏覽前後全部16表hash相同；會員全列、hard_level_snapshot及其他非調級報名欄位與初始備份一致。此次瀏覽器新增5筆level audit（含合成選手03的3→1→3往返及同名選手3→1→4→6），原因皆null，保留逐次歷史；integrity=ok、FK錯誤0。
- 安全：未登入管理401；錯誤Origin／缺CSRF403；錯Host／缺forwarded／HTTP proto／公開偽造forwarded／來源127.0.0.2的forwarded均400；Secure／HttpOnly／SameSite=lax。僅127.0.0.1:8041 listener，信任同機loopback程序，沒有Docker網路隔離保證；inspector／remote-management關閉。沒有公開debug或access body日誌。
- 保護核對：48來源、3複製成品、當次36個既有檔案及先前439個保護檔案皆未改（大封裝沿原基準只比size／mtime）。8037 PID57548與8039 PID55404保留；Docker／GPU零操作。browser console無error/warn。

完整證據在 `data/arrangement-native-runtime/`：`identity.json`、`security.json`、`browser-evidence.json`、`data-verification.json`、`protection-final.json`、`desktop-current.png`、`mobile-history.png`。登入檔、PID／停止方式見README。原生入口已可人工驗收，但不代表使用者已接受、正式部署完成或r11 Docker升級／回退完成。

功能驗收後另依使用者指定新增合成 `admin`，同庫之外未寫入。過程曾短暫套用短密碼；最新指示已改用既有hash_password的正常12字元規則，取消fixture例外並撤銷所有admin舊sessions。最終新密碼HTTPS登入200、管理讀取200、登出204，舊密碼401；定向session撤銷前200／撤銷後401，Secure／HttpOnly／SameSite仍有效。原管理員及版本actor保留，帳密只存ignored檔，沒有寫入產品預設或更改正式規則；最終證據 `admin-rotation-verification.json`。上述16表不變證據特指歷史瀏覽區間，不包含其後已授權的admin／session修改。

共用owner於22:54:49已恢復Docker並停止舊府城容器至exited，由main／orchestrate轉達；本task未操作或重新探測Docker，hold持續。原生入口未受影響，舊Docker/r11仍不在本次已完成項目內。

23:09入口恢復：8170原生程序後來消失，根因未知；免費agent拒絕指定重用，因此目前入口改為f9d0且app使用精確新Origin。80人完整功能驗收於原8170完成，來源／DB／成品不變；新入口補做最新正常密碼登入及session撤銷驗證。舊8037／8039在恢復查詢時亦無listener，本task未操作它們。新app／ngrok已跨啟動工具shell結束保持運作；不宣稱永久背景執行。

後端與 migration 證據：

- 首輪 `uv run --locked pytest -q tests/test_arrangements.py tests/test_competition_levels.py -p no:cacheprovider --basetemp .test-tmp-arrangements-first`：32 passed（21.25秒）。
- 完整回歸 `uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-arrangement-all`：**101 passed（50.48秒）**。此為補上state.editable前的本輪完整版本；不是引用上一輪78項。
- 最後補上同一讀取快照的editable、外部結束後重讀呈現唯讀，以及0006升級前備份還原新目標後，針對受影響範圍 `uv run --locked pytest -q tests/test_arrangements.py tests/test_public_registration.py -p no:cacheprovider --basetemp .test-tmp-arrangement-final`：**39 passed（23.98秒）**。兩輪皆僅2項既有上游棄用警告，沒有形式重跑未變測試。
- 涵蓋optional原因／原原因規則、無GET隱性baseline寫入、直接level先ensure、並行init只一次、初次level/audit失敗連baseline回滾、版本與保存audit任一步失敗整體回滾、同名／取消重報／候補遞補／更名、snapshot不可變與真actor、跨場404／權限／CSRF／終態限制。完整token過期涵蓋level／取消／遞補／重報／姓名註記／比賽版本／另存；同key並行只一版、不同key並行保存一成一409、save/level並行符合完整序列化切點、舊save重送回原版不倒退latest。GET在讀取途中另一connection寫入level／version時仍回同一讀取快照。
- 0002／0005／**0006→0007**合成升級保留原所有表原欄位，包含原會員、快照、已改當次級數、version、順位及既有audit。新versions為空，不補造歷史；Alembic check無差異。升級前0006備份Restore新target保留原內容／revision；升級後backup／restore皆integrity=ok、FK=0。故意invalid FK使migration失敗時，DDL及revision回滾。這是SQLite／程式層證據，尚未進行新image/volume部署回退演練。

前端與瀏覽器證據：

- `npm run build -- --outDir ../frontend/dist-arrangement` 通過，包含tsc型別檢查。沒有依賴變更。`git diff --check`通過。
- 全程使用 `FUCHENG_E2E_DATABASE_URL=sqlite:///data/arrangement-e2e.db`、`FUCHENG_E2E_PORT=8040`、`FUCHENG_E2E_STATIC_DIR=frontend/dist-arrangement`、`PYTHONUTF8=1`，單worker；desktop1440×900、mobile390×844、isMobile／hasTouch。
- 新功能首輪 `npm run test:e2e -- --grep '緊湊八十人|大存未知|免原因移動|儲存後讀回' --output test-results/arrangement-first`：8 passed（24.9秒）。
- 加入同名／名單變更、真正另一admin帳號及最後editable修正後，首次全套 `npm run test:e2e -- --output test-results/arrangement-final`：17 passed／5 failed。新10項全過，失敗來自共用合成fixture：新同名資料撞原固定搜尋，以及大量新會員令原測試假設的預設100名候選不含指定會員。
- 新同名fixture改獨立名稱，原管理測試改為先搜尋指定會員；原功能及安全斷言全部保留。因影響共用DB，重跑整套 `npm run test:e2e -- --output test-results/arrangement-isolated-final`：**22 passed（57.2秒，新10＋既有12）**。不是首次全套全綠；8040測試server已退出。
- 最終22涵蓋：80人十欄密集版面、原大卡／快捷區／常駐統計不存在、搜尋圖示；真實trusted mouse與CDP touch長按拖曳、普通name橫捲不寫入、拖到邊緣自動橫捲可抵第10欄、Escape／touchCancel；5→4→6有兩audit淨5→6、回5消色；大存清色、再次異動、兩歷史各對前版、唯讀回看不寫DB、回目前不還原；名稱／顯示editor／真actor與可選note、同名／重報／遞補新增移出、更名後舊快照不改。
- 故障與時序涵蓋：level commit後503、commit前斷線原樣重試；其他卡仍可獨立操作；真409；PUT成功後GET掛起／失敗同卡仍鎖，重讀成功才解鎖；大存commit後503，**另一帳號再改級／另存／再改級**後以原key重試，仍回原receipt且current latest不倒退；大存在途切場晚回應不跳場；409大存保留tag／顯示editor／note，重讀核對後新token再存。

獨立人工預覽：[8039 排級數](http://127.0.0.1:8039/admin/competitions)，`data/arrangement-preview.db`／`frontend/dist-arrangement`。83位合成會員、3場、85報名，主場80人安排。`scripts/create_level_preview.py --variant arrangement`新建，不複製真資料；初始1→3示例先建立baseline再調整。來源及initial backup／restore均integrity=ok、FK=0、0007，見 `data/arrangement-preview-verification.json`。

`data/arrangement-preview-browser-verification.json`記錄最終8039桌面／手機80姓名格／10欄、搜尋1人、可到最遠欄、整表高度約458.5px、無頁面水平溢出、無pageErrors；desktop容器1372px、mobile335px／內容1100px。此次QA只有登入／選場／搜尋／歷史檢視，adminWrites=[]。截圖 `data/arrangement-preview-{desktop,mobile}-{table,search-far,history}.png`及E2E `compact-80.png`／`membership-history.png`已目視核對。orchestrate另以IAB只讀核對80人桌面及手機搜尋／橫捲。手機為Chromium觸控模擬與viewport證據，不替代球館實機與使用者操作驗收。

原6個DB的78表內容hash前後一致；原dist成品及r7～r10共439檔一致（<20MB用SHA256＋stat，大型archive僅size／mtime，不稱全檔hash）。見 `data/arrangement-protected-before.json`／`arrangement-protected-after.json`／`arrangement-protection-verification.json`；source allowlist已核對涵蓋新後端／0007／前端檔，未實際建置image。這是task4當時的歷史檢查：當時8037 PID57548及8448／8450 listener仍在，8032～8035未復活。當前原生／舊Docker狀態以上方收尾紀錄為準，task4當時未動Docker／ngrok／selfhost。

新8039最終listener **55404**、launcher **63776**；PID檔 `data/arrangement-preview.pid`／`arrangement-preview-launcher.pid`，日誌同前綴stdout／stderr，帳密僅 `data/arrangement-preview-admin.json`。本輪曾為載入editable修正只重啟新8039，已告知orchestrate，未停止其他服務。停止前比對netstat8039 PID及Python身分，再依README停該listener。8039留供驗收。

交付：主要目錄 `D:\projects\fucheng-players-system`，分支 `feat/competition-arrangement-versions`，起始及HEAD `0970af21abf4a8761a898f06d8b4d34da8a7d341`。此為task4當時交付：無新增worktree，成果未提交／merge／push，當時尚無新版公開入口。其後task5已交付頁首所列原生公開合成入口；舊Docker由owner停止且維持hold。後續部署task須以新source manifest建新image，明確停寫／備份／migration；回退是舊image＋0006 pre-update備份Restore到新target，保留0007更新後DB，禁止破壞性downgrade。自訂甲乙丙表頭／當次安排列印／編隊／隊長／循環賽未實作。

## 姓名卡片拖曳與逐次自動儲存（2026-09-20）

本輪 A+B 工程驗證完成，等待人工操作驗收。滑鼠拖曳、手機長按把手拖曳、點選／鍵盤移動共用逐次自動儲存；管理員先手填本次原因，每次移動固定當下原因、版本及 request_id。同一卡片完成後才能再移動，其他卡片獨立。已儲存撤回是有原因的新反向異動；結果不確定保留原操作重試，409 不替換版本或自動覆寫。會員長期級數、報名快照、當次級數與既有名單／列印語意保持獨立。

驗證使用 `FUCHENG_E2E_STATIC_DIR=frontend/dist-level-drag`、`FUCHENG_E2E_DATABASE_URL=sqlite:///data/level-drag-e2e.db`、`FUCHENG_E2E_PORT=8038`、`PYTHONUTF8=1`，單 worker。desktop 1440×900；mobile 390×844，isMobile／hasTouch 開啟。

- `npm run typecheck`、`npm run build -- --outDir ../frontend/dist-level-drag` 通過，未更新依賴。
- `npm run test:e2e -- --grep '姓名卡片|自動保存未知|真實409' --output test-results/level-drag-first`：6 passed（17.7 秒）。真實 Chromium 滑鼠／CDP touch 事件均 isTrusted，含長按前移動取消、touchCancel／Escape、卡片非把手原生捲動；自動儲存、連續移動、反向撤回與逐次原因／稽核；commit 後 503 且後續另改級再原 key 重試回最新紀錄；未 commit 斷線重試；另一卡片獨立；真實 409、切場保留原因／未完成操作、遲回應不跳場、較新版本不被舊回應取代、終態唯讀。
- `npm run test:e2e -- --grep-invert '姓名卡片|自動保存未知|真實409' --output test-results/level-drag-regression`：8 passed／4 failed。失敗是既有測試使用全頁 status 或模糊比賽按鈕姓名，與新卡片提示／把手撞名；已縮至通知 `.toast[role="status"]` 及 `.competition-item` 精確名稱，未刪除斷言或改業務行為。
- `npm run test:e2e -- --grep '刪除需確認|整批八十人' --output test-results/level-drag-regression-fixed`：80 人匯入桌面／手機 2 passed，刪除案例在還原後另一處同名定位 2 failed。補齊該檔比賽列表定位後，`npm run test:e2e -- --grep '刪除需確認' --output test-results/level-drag-deletion-final`：2 passed（6.7 秒）。合計 **18 個不同 E2E 通過（新 6＋原 12）**，不是首次全套全綠。
- 本輪未修改後端或 migration，未重跑先前 78 項 Python 測試；下節 78 passed 是既有 HTTP 部署階段證據。8038 測試服務已退出。

人工預覽 [8037 比賽管理](http://127.0.0.1:8037/admin/competitions) 使用新建 `data/level-drag-preview.db`／`frontend/dist-level-drag`。83 位合成會員、3 場比賽、85 筆報名，主場 80 正取／2 候補／1 取消；沒有複製真實資料。`scripts/create_level_preview.py --variant level-drag` 保留原預設 variant 與拒絕覆寫行為。初始備份 `backups/level-drag-preview-initial.db` 與還原 `data/level-drag-preview-restore-check.db` 均 integrity=ok、foreign_key_errors=0、revision=0006，見 `data/level-drag-preview-verification.json`。

80 人預覽另以真實 Chromium 驗證兩種尺寸：80 張姓名卡、十區、3 級篩選 9 張、篩選仍保留十個區域及十個快捷目的、區內可捲動、無水平溢位與 pageErrors。這次視覺 QA 沒有送出調級修改；結果 `data/level-drag-preview-browser-verification.json`，overview／board 截圖 `data/level-drag-preview-*-*.png` 已目視檢查。長姓名及未知結果提示由新 E2E 截圖核對。觸控是 Chromium 模擬，未取代球館實體手機操作驗收。

保護前後比對 `data/level-drag-protected-before.json`／`level-drag-protected-after.json`／`level-drag-protection-verification.json`：原 dist-public／dist-delete／dist-levels、r7／r8／r9 共 321 檔無差異（小於 20MB 以 SHA256＋大小／時間，大型 archive 僅大小／時間）；原 5 個 DB 的 63 張表內容 hash 一致。8448／8450 listener 持續存在；8032～8035 在本輪開始／完成檢查皆無 listener，沒有重啟或停止它們。既有 ngrok／Docker、真實資料及舊交付包未更新。

8037 實際 listener PID **57548**、啟動父程序 **54164**，分存 `data/level-drag-preview.pid`／`level-drag-preview-launcher.pid`；帳密只存 `data/level-drag-preview-admin.json`。停止時先比對 netstat 的 127.0.0.1:8037 PID 與 Get-Process Python 身分，才依 README 停止該 listener，不能拿其他預覽 PID 操作。8037 留供驗收。

交付位於主要目錄 `D:\projects\fucheng-players-system`，起始 main `289be6ca9692f2ed701a86f16a444b8e7151475c`，工作分支 `feat/competition-level-drag`；無新 worktree，變更未提交，未 merge／push。task4 本機驗證後，task5 另依授權更新公開預覽，見下節；上段保護結果是 task4 換版前的歷史證據。大版本快照、版本名稱／備註、與上一保存版本的淨差異顏色、自訂標題與當次安排列印另待後續階段，並未以報名快照代替上一保存版本。

### r10 公開預覽更新與操作驗證

沿用 `https://30a1-140-116-158-107.ngrok-free.app/`／`fucheng-ngrok-preview-20260920`，只替換 app／backup。r10 `local/fucheng:snapshot-b7a6f33e2b8e4777` 由 allowlist 的 47 檔 build context 建置，三個新前端模組均在 manifest；Docker 內 typecheck／build 通過。完整 image、source、archive SHA256 見部署手冊。後端、schema、runtime 與 r9 文字一致；部分檔案只有 Git 換行正規化造成 bytes 不同，未作應用修正。

- 換版前正常手動備份，正常停止 app／backup 後再建立 checkpoint `manual-20260920T030501454562Z-2de5c494.db`，SHA256 `473c6316a7d826541ffa797d58d78ff0dd01f47a5a72566c1e1862af0dbc9db3`；integrity=ok、foreign_key_errors=0、revision=0006。原 image／env／checkpoint 保留，無 migration／reseed。換版前後 15 張資料表筆數與內容 hash 完全相同，3 會員／1 場／2 報名保留。
- 真實公開 **CUA IAB**：正常 TLS 登入、先填原因、滑鼠把手拖曳合成甲 3→6、自動儲存、重開仍為 6、歷史顯示操作者／時間／原因成功；沒有儲存按鈕介入、TLS bypass 或 ngrok skip header。390×844 手機尺寸實操點選 6→3，再使用已儲存撤回 3→6，反向紀錄存在，無水平溢位；最後登出。長按主路徑沿用上節 trusted CDP touch E2E，未在此次 IAB 重演長按或宣稱實體手機驗收。
- 驗收只新增三筆有原因的 `level` 稽核；合成甲當次級數最終 6、version +3、報名快照仍 3。所有會員欄位／級數、比賽、兩筆報名身分／餐食／快照／順位／狀態與既有稽核保留。登入相關表有預期 session／attempt 變動。
- 正常 TLS API：health 200、未登入管理 401、錯 Origin 403、缺 CSRF 403、偽造 forwarding 400、拒絕後合法 session 仍 200、登出 204；cookie 仍 Secure／HttpOnly／SameSite=Lax。
- 原本機 DB／dist／帳密指紋一致；r7～r9 原包完整 SHA256SUMS 驗證通過。換版後即時快照中其他容器 ID／StartedAt 全保持；收尾時發現三個 KaChing portable api／mcp-read-api／mcp 容器其後另有變化（03:05:27～03:05:42 UTC），本 task 未操作它們，未調查或回復外部工作。ngrok、8448／8450、selfhost 容器保持，8037 PID57548 保留。8032～8035 在此次起始就無 listener，沒有重啟。無新 worktree／Git 提交／推送／資源清理。

本次證據集中於 ignored `data/deployment-ngrok-r10-evidence-20260920/`：`updated.json`、`backup-stopped.json`、`data-preservation.json`、`source-package-verification.json`、`public-api-security.json`、`iab-evidence.json`／截圖與 AX 紀錄、`final.json`。既有 18 distinct E2E 與 78 backend 證據沿用，不形式重跑。公開工程操作驗收通過，使用者接受成果與球館實機驗收仍是獨立狀態。

## ngrok 公開 HTTPS 合成預覽（2026-09-20，另行授權）

URL `https://30a1-140-116-158-107.ngrok-free.app/`。使用全新 `fucheng-ngrok-preview-20260920` project/data/backups、精確HTTPS origin與ngrok trusted peer，復用r9 image（沒有程式/image變更，也未更新舊交付包）。local-http模式未接Tunnel；既有8032～8035、8448、8450保持運作。只初始化3位合成會員與1個2099年合成場次。

- 正常TLS外部HTTP client驗首頁200、health200、Secure/HttpOnly/SameSite=Lax、登入及登出；Origin403、CSRF403、未登入管理401、偽造forwarding400。原負向測試一度預期代理會清洗偽造header後200，實際安全拒絕400，已更正測試期望，未放寬應用防護或重複seed。來源 `public-api-evidence.json`。
- app內網錯Host400、不受信peer偽造proxy400；公開HTTP307轉同域HTTPS，`host-peer-evidence.json`。未修改已過78項測試的程式，所以沿用既有全套結果，未為形式重跑。
- 真實CUA IAB首頁、登入、儲存合成會員辨識註記、登出通過；`iab-evidence.json`、`iab-admin.png`、`iab-member-saved.png`、`iab-logout.txt`。orchestrate首訪經ngrok Visit Site提示後成功，main亦看到合成賽事；沒有TLS警告繞過或skip header。
- 本次證據、private env/token與合成帳密均位於ignored `data/deployment-ngrok-evidence-20260920/`；總索引`ngrok-final.json`。Token/密碼未輸出、未入套件、未更改原ngrok設定。準確停止與存續条件見部署手冊。工程可訪問性通過，仍不宣稱使用者已接受成果、正式資料部署或球館實機驗收。

## 本機 HTTP 合成預覽（2026-09-20，另行授權）

r9 `data/deployment-release-20260920-r9/` 加入明確 opt-in、獨立 project/volume/cookie 的本機 HTTP 預覽。app `local/fucheng:snapshot-1076c3922cbd1465`，image ID `sha256:387861452a77d4e34c66f9ba6c7e6d30136cd3779076ee4c01b86992afe39858`，source SHA256 `1076c3922cbd1465441071ed2da39be500f41f673a322bf9858fc18e41d74c00`，image archive SHA256 `da919750dee95e164b4e678c05b8d171617fde1eac8aa8d4df6cc1e2f637ba38`。r7/r8原交付保留；8448沿用r7/r8映像未重建，HTTPS工程證據不冒充IAB憑證通過。

- `uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-http-all`：78 passed，2項既有上游warnings。包括HTTP非法設定13組fail-closed、HTTP Host/Origin/CSRF/管理session與cookie名稱、原HTTPS Secure cookie及代理語義回歸。前端未變，build重用已驗成品cache。
- 新HTTP容器由空白volume初始化，3個合成會員／1個合成場次；禁止復用未標記庫、HTTP restore/import/migrate、HTTPS啟用HTTP標記庫。首次internal-only bridge雖配置port卻不發布host listener，已改獨立普通bridge、雙loopback發布；沒有Tunnel服務，拒forwarding headers。此網路不提供出站隔離，不得宣稱具有此能力。
- 真正 **CUA Codex IAB** 訪問 `http://localhost:8450/`：首頁、管理登入、儲存會員辨識註記、比賽管理與登出均成功，沒有ignoreHTTPSErrors或略過TLS警告。證據 `data/deployment-http-evidence-20260920/iab-evidence.json` 與 `iab-*.png`／首頁及登出AX紀錄。另由orchestrate自己的IAB核對首頁可用。
- API共用cookie jar登入HTTP/HTTPS各自合成帳號，雙session共存；HTTP登出後HTTPS仍200，雙向替換token皆401，HTTPS cookie維持Secure、HTTP專用cookie無Secure。證據 `cookie-isolation.json`，此項是API測試context，並非瀏覽器跨站jar實測。
- 帳密僅本機ignored `data/deployment-http-evidence-20260920/synthetic-admin.json`；停止方式、來源與資源清單見該目錄 `http-final.json` 及部署手冊。保留本機預覽供人檢視，仍待人類接受；沒有公網、正式資料或編隊/循環賽功能授權。

## Windows Docker可搬移套件（本機工程驗證，待階段核對／人工驗收）

正式拓撲為單一app image（React成品＋FastAPI）與SQLite named volume，備份／維護复用app image；Cloudflare named tunnel直連app，nginx只供本機HTTPS測試。沒有啟動公開Tunnel、球館遠端、真實資料遷移或正式上線。

最終套件：`data/deployment-release-20260920-r8/`。app tag `local/fucheng:snapshot-16baa6405474f861`，image ID `sha256:9c9debe226d721af860a96a11de90eb0128f54f9d9965f69c28712773e665d3d`，source manifest SHA256 `16baa6405474f861217fc92668d91bb5ae0b7fa3556154d9e807fcfec51647bb`。離線 `fucheng-images.tar` SHA256 `5d775963ee9aecc9c001cf9328b99cf3317733b8bcc27dd7c63809125d2f6580`。這是含未提交級數與部署變更的working-tree snapshot；HEAD `1ba5c68809866150f9d4e8a5c5e38c393dec2aca`只表示起始提交，不能代表全部image來源。r8只更新雙loopback Compose與手冊，沿用r7相同image、source與archive。r7已按原交付hash還原保留；r1～r6為過程材料，不能交付替代r8。

### 已完成證據

- 人工預覽後續修正：原Compose只綁IPv4，實测IPv6連線拒絕；現僅為https-test加上`[::1]`映射，兩種loopback路徑均200，IP網址仍400、錯誤Origin仍403。只重建nginx測試容器，app image／來源manifest／image archive未變，套件Compose、手冊與SHA256SUMS已刷新。**Codex IAB在本task修正前後均回ERR_CERT_AUTHORITY_INVALID，未進入頁面或登入；不能把main先前ERR_CONNECTION_REFUSED全部歸因於IPv6，也不能把自動Chromium測試當成人工IAB成功。** 自簽憑證例外須由人員處理，未安裝信任、未關閉驗證或放寬Host/Origin。證據`preview-loopback-20260920.json`；此項人工驗收仍未通過。
- `uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-deploy-all`：**63 passed**，2則既有上游warning；包含4項部署Origin/Host/Secure cookie及Cloudflare/ngrok受信peer/IP語義測試。後續只修改容器runtime／helpers，未重跑未變的應用測試。`npm --prefix frontend audit --audit-level=high`：0 vulnerabilities。Docker多階段build內npm ci/typecheck/build及uv locked依賴安裝成功，不覆寫本機dist。
- 真實build context export精確比對44個允許檔案；source ZIP與凍結build-context逐檔一致，image內manifest與label一致；裸image沒有DB、Node runtime或會員資料，UID10001。app無host port、唯讀rootfs；實際連線pragma為FK=1、busy_timeout=10000、journal=wal、synchronous=2(FULL)。外部非受信容器偽造Forwarded/XFF/XFP/CF-Connecting-IP均400。
- 本機HTTPS Chromium桌面1440×1000／手機390×844：登入、Secure/HttpOnly/SameSite cookie、公開首頁／分級／選名報名、管理當次級數3→7且快照仍3、Origin/Host/CSRF拒絕、登出與無水平溢位。最終r7獨立還原庫結果 `data/deployment-evidence-20260919/https-browser-results-8448.json`；截圖 `https-8448-*.png`。屬手機viewport測試，未取代球館實體手機與外網驗收。
- fresh init／無預設密碼CLI建立管理員／未初始化拒啟動／重複Init拒絕／第二writer与服務中migration拒絕／force-recreate持久化均通過。0005舊程式fixture→0006→舊image＋0005 pre-update備份回退通過；正取／候補／取消快照逐列回填，更新後寫入保留於舊DB。舊image是**HEAD 0005程式與前端＋本輪deployment guard**的合成回退fixture，並非曾正式部署的版本。證據 `drill-upgrade-1789816812824004800.json`、`drill-persistence-1789816762625716400.json`。
- 新runtime另補受影響恢復測試：migration失敗留下maintenance且拒啟動；損毀／缺失active DB由有效備份還原至新檔、保留故障檔與操作證據；interrupted init獨立volume救援。完整命令及結果見最新 `drill-recovery-*.json`，最終索引見 `deployment-final.json`。一次重跑曾因測試fixture重用舊volume而被guard正確拒絕，修正測試volume唯一名稱後通過，不列為產品成功證據。
- 備份失敗stderr/backup-health可見、手動checkpoint不受自動retention刪除。**長時短週期測試發現舊版備份留下3760組partial-WAL/SHM，先前僅檢查DB數量不足以證明保留政策。** r7將BackupAPI目的副本轉為DELETE journal，來源live DB仍WAL；Legacy WAL匯入先hash再複製可寫暫存驗證，不用immutable或掛可寫來源；Restore在鎖內驗metadata/hash並回收已匯入備份空白sidecars，完成後來源bytes不變。8次備份後只有2個scheduled DB／metadata、0個partial/importing sidecars；舊累積檔保留盤點，不廣泛刪除。證據 `backup-standalone-retention.json` 與 `deployment-final.json`。
- 完整可攜包另複製到 `data/deployment-portable-test-20260920-r7/`，**僅用Windows內建PowerShell5.1＋Docker**執行load（逐檔SHA及全部image ID）、Legacy WAL備份Import、新volume Restore（不先Init）、StartTest、Status、ExportBackups；重複匯入、既有匯出目錄、錯誤hash、服務中Migrate均拒絕。腳本補顯式Utility module載入、在body解析套件路徑，以消除PS5.1與PS7差異。精確命令／exit/stdout/stderr：`portable-final-operations.json`。
- 新版ExportBackups封存持backup.lock，Windows驗tar及解開後每檔hash；匯出的單檔備份再經ImportBackup還原到第二個全新project/volume，所有資料表筆數及內容hash相同：`portable-roundtrip.json`。這是合成、同主機的離機交接流程演練，不聲稱已擁有真實異地備份。
- Cloudflare image實查2026.9.1，ngrok3.39.8且config check通過；兩者均只在network none執行版本／配置命令，未啟動Tunnel。官方來源與未驗項見部署手冊。

### 保護與交付狀態

主要目錄 `D:\projects\fucheng-players-system`、分支 `feat/competition-level-management`、HEAD未變，無新worktree、未commit/merge/push/registry/正式部署。起始26個級數差異完整保留；原前端與級數業務碼未回復。部署新增Docker/Compose/runtime/PowerShell helpers、封裝與演練腳本、proxy邊界與測試，並更新既有文件；src/app.py僅增加可選部署middleware，config新增對應環境欄位。起始manifest／diff存 `baseline-files.json`／`baseline.patch`；本輪檔案範圍由 `preservation-final.json`及最終索引列明。

原各DB全表hash／筆數、dist-public/dist-delete/dist-levels及帳密檔hash前後一致：`protected-before.json`、`protected-after.json`。原8032～8035及共用selfhost-models／KaChing服務沒有被停止或修改。所有Docker演練只碰fucheng專屬合成project／volume；保留容器、volumes、網路及過程包清單與停止方式見 `deployment-final.json`，沒有prune／down -v或未授權清理。

仍待：orchestrate階段核對與人類接受、球館虛擬化/WSL/Docker/電源/重啟實查、無人登入恢復責任、domain/account及真正named tunnel、外網手機、唯一正式資料來源與搬移授權、真正離機備份保管。以上不阻止本機套件完成，但不能描述為正式上線完成。

## 當次比賽級數與人員管理（2026-09-19）

第一階段工程驗收完成：會員長期級數、報名快照及當次比賽級數獨立；管理員只調正取且原因必填，支援姓名／註記搜尋、當次級數篩選、升冪分區、固定全場與篩選人數、取消歷史與候補分開。沒有編隊、隊長、A/B 分組、抽籤、對戰或公開參賽名單功能。

- 後端原有全套：`uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-levels`，45 passed（24.48 秒）。新增案例及相關 public／migration 最終驗證：`uv run --locked pytest -q tests/test_public_registration.py tests/test_competition_levels.py -p no:cacheprovider --basetemp .test-tmp-level-final`，28 passed（15.98 秒）。兩者部分重疊，共 **59 個不同後端案例有通過證據**；`--collect-only` 確認目前共 59 項，不把它說成一次全套 59 passed。2 項既有上游 deprecation warning 保留，無依賴變更。
- 新案例驗證管理／公開／批次新列初始化、同會員別場不變、會員與快照不變、重讀歷史含 actor／時間／前後級數／原因；非法級數／多餘欄位／空原因／未登入／缺 CSRF／舊版本拒絕；同級數回 422 且沒有空白調級稽核。相同 key 重送不增版本，跨 actor／payload key 重用拒絕。
- 故障注入在 registration_audits INSERT 觸發 ABORT，報名當次級數、version、操作者／時間及稽核全部回滾。並行兩筆調級、調級與取消都是一筆成功、一筆 409。已取消列不可修改；重報新列用新會員快照初始化；候補遞補保留原列級數。closed／實際過截止仍允調級，deleted／ended／cancelled／draft 阻擋；刪除還原不重設級數。
- 最後將刪除／還原案例強化為「先人工調級，再經真正 delete／restore API」確認當次級數及整筆報名保留；只重驗 `tests/test_competition_levels.py -k lifecycle --basetemp .test-tmp-level-lifecycle`，6 passed（3.54 秒），沒有因此重跑其他未變案例。
- Migration **0006_competition_level**：合成 0002 及 0005 升級、全原表原欄位逐欄保留、候補序、取消紀錄、公開 actor、已刪除狀態皆通過；故意令會員目前級數不同於快照，確認回填來自快照。備份還原、integrity_check／foreign_key_check、Alembic check 及兩個起始版本的故障 DDL／revision rollback 通過。原會員及正式庫未套用。
- `npm run typecheck` 通過；最終 `npm run build -- --outDir ../frontend/dist-levels` 通過（JS gzip 74.18 kB）。Vite 暫存與 Playwright cache／結果目錄的 sandbox 權限已依授權建置／測試範圍取得，未改套件或覆寫既有成品。
- E2E 全程使用 **8036／data/levels-e2e.db／frontend/dist-levels**、單 worker、desktop 1440×900 與 mobile 390×844。首次全套 12 passed／2 個既有刪除測試因 role=status 多個元素而失敗；定位縮至 `.toast[role="status"]` 後 `--grep '刪除需確認' --output test-results/levels-deletion` 為 2 passed（6.7 秒）。新增表單聚焦與歷史失敗情境後，受影響的 `--grep '當次級數安排' --output test-results/levels-final` 再次 2 passed（7.8 秒）。共 **14 個不同 E2E 案例通過**，不稱首次全套全綠。
- 新安排瀏覽器案例包含保存重開、分區與搜尋統計、實際另一筆 API 競寫造成 409（不是只 mock 409）、保留輸入及原 version、切換場次再返回保留草稿、503 模擬故障後以原 key 重試、歷史前後值、讀錯場歷史防護，以及手機無水平溢位。503 為前端失敗情境，資料庫交易故障由後端 trigger 測試驗證。桌面／手機截圖已目視檢查：`frontend/test-results/levels-final/competition-levels-*/levels-failed-input.png` 及 `levels-saved.png`。

### 可操作合成預覽與原環境保護

[8035 比賽管理](http://127.0.0.1:8035/admin/competitions) 使用全新合成 `data/levels-preview.db`，83 位合成會員、3 場比賽、共 85 筆報名。其中主場 80 正取／2 候補／1 取消；另一場用相同會員驗證級數獨立。沒有複製真實資料庫。初始 Backup API 備份 `backups/levels-preview-initial.db`、還原 `data/levels-preview-restore-check.db`，檢查報告 `data/levels-preview-verification.json` 的來源／還原皆 integrity=ok、FK errors=0、0006。

在這個 80 人預覽另外啟動真實 Chromium 檢查 desktop 1440×900／mobile 390×844：全場正取 80、3 級篩選 9、無水平溢位、調級表單可聚焦及輸入；未送出新的報名／調級修改。結果 `data/levels-preview-browser-verification.json`，兩平台 overview／group／form PNG 在 `data/levels-preview-*-*.png`，均已目視檢查。這是模擬手機 viewport，未取代球館實機驗收。

實際 8035 listener PID **20008**，啟動父程序 **53140**；分別保存在 levels-preview.pid／levels-preview-launcher.pid。帳密只存 `data/levels-preview-admin.json`，未輸出。啟停及重建防覆寫行為見 README。8036 測試服務已退出，8035 依預覽交付保留。

受保護的 8032／8033／8034 listener PID 仍為 59376／35904／59116。運作中兩份預覽 DB 主檔直接 hash 被 Windows 檔鎖阻止，改用 read-only SQLite 各表完整列指紋前後比對：club-preview.db（0004）與 club-delete-preview.db（0005）全表一致，證據 `data/levels-protected-db-before.json`／`after.json`。原 fucheng.db／competition-case.db 與 dist-public／dist-delete 成品共 8 檔 SHA-256 一致，證據 `data/levels-protected-before.json`／`after.json`。沒有停止既有服務或升級其庫。

交付位於主要目錄 `D:\projects\fucheng-players-system`，分支 `feat/competition-level-management`，起點／HEAD 仍為 `1ba5c68809866150f9d4e8a5c5e38c393dec2aca`，所有本階段變更未提交；未建立 worktree、未 commit／merge／push／deploy。正式資料遷移、Linux／HTTPS／球館實機，以及第二階段人工編隊與隊長管理均未執行。

## 9/20 已確認 80 人名單匯入（2026-09-18）

依使用者確認，9/20 為 2026 年、80 人全數正取、沒有候補且不開放額外報名。17 筆近似姓名、另外同名／弱候選由使用者確認；15 筆新會員姓名經 7 筆更正後，使用者明確同意依原圖欄號作為這 15 人的初始硬實力級數。既有會員仍沿用目前級數，不回寫來源欄號。黃安彬兩筆會員的資料及初始匯入歷史一致、皆未報名，本場沿用穩定排序第一筆，僅登記一次，兩筆原會員記錄均保留。

- 後端：`uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-roster-import`，**41 passed**（21.57 秒），2 則既有上游 warning。新案例包含全交易回滾、新會員與餐食快照、超額／版本／資料變更／同名／重複列拒絕、權限與 CSRF、批次重送、兩個並行請求匯入 80 人仍只有 80 報名及稽核。
- E2E：`cd frontend; npm run test:e2e`，**10 passed**（23.5 秒），皆在獨立 8031 合成庫。新增桌面／手機 80 人匯入後的實際瀏覽器名單、級數篩選、80 筆稽核與列印模式，原 8 個案例亦通過。應用程式前端未更改，沿用已建置成品。
- 已授權資料操作：只在 club-preview.db 執行管理員 API，65 位既有會員加 15 位新會員，共 80 正取、0 候補、0 空位；場次 closed。餐食 64 葷、2 素、14 未設定；其中原圖明確 1 位素食，另 1 位沿用既有會員預設，14 位新會員無餐食資料故不猜測。
- 預覽會員總數 342，327 筆原會員逐欄未改動；testing 場次及其報名／稽核逐欄與匯入前備份一致。原 fucheng.db、competition-case.db 雜湊在操作前後不變。完整姓名、ID、決策及結果只保留於 Git 忽略的 data/ 下。
- 匯入前 Backup API 備份：backups/club-before-confirmed-80-import-20260918.db；結果與備份路徑：data/club-tournament-0920-import-result.json；資料庫 integrity_check／foreign_key_check 通過。本輪不需 migration，仍為 0004_club_website。

自動核准機制拒絕重啟現有 8032，理由為早先「不要停止現有服務」限制；因此 8032 原程序保持運作，另在 8033 啟動新版 API 操作同一份預覽副本。8033 PID 記於 data/roster-import.pid，啟停及功能邊界見 README。原 8032 可直接讀到新名單，不需停止服務。此輪驗證當時尚未提交、未合併、未部署；後續 Git 整合授權見下節。

## 球館網站整合驗收（2026-09-18）

本輪已將首頁、公開分級、比賽入口與公告管理接成同一網站。依使用者最新授權，所有人可免登入查看啟用會員姓名／級數／辨識註記；公開 schema 移除餐食。下方 9/17「完整分級限管理員」描述為當時歷史邊界，現由本節取代。

- 後端完整測試初次為 36 passed／1 個新測試 helper 參數錯誤；修正 helper 後 `uv run --locked pytest -q tests/test_website.py -p no:cacheprovider --basetemp .test-tmp-website3` 為 3 passed。共 37 個不同案例已通過；既有 2 則上游 deprecation warning 保留。初次 migration revision 斷言亦已更新到 0004。
- `npm run typecheck`、`FUCHENG_BUILD_DIR=../frontend/dist-public npm run build` 通過。沒有新增依賴。
- `npm run test:e2e` 原 6 個桌面／手機管理與報名案例通過；新增 2 個首頁案例的級數 select 定位修正後，`npm run test:e2e -- --grep "首頁公告"` 2 passed（7.8 秒）。共 8 個不同 E2E 已通過，均使用 8031／public-e2e.db 合成資料。
- 新案例涵蓋公告草稿不公開、發布、置頂、下架、未授權／缺 CSRF 拒絕、空白內容及多餘欄位拒絕、idempotency 重送不重複、version conflict 保留輸入、公告與稽核失敗整筆回滾。公告文字中的 `<script>` 在瀏覽器僅當文字顯示。
- 首頁 → 免登入分級 → 搜尋同名／級數篩選 → 比賽報名 → 首頁導覽已由桌面與手機驗證；手機首頁無水平溢位，截圖已視覺檢視。比賽公開時程不含草稿，狀態 open 但時間已截止時顯示 closed，也不出現在可報名清單。

### 原會員副本與啟動成果

使用者已授權以原會員資料副本檢視新版。執行 `uv run --locked python scripts/create_club_preview.py`，從 `data/competition-case.db` 以 Backup API 建立 `data/club-preview.db`，升級 0002 → 0003 → **0004_club_website**。原 327 會員、2 管理員、1 比賽、649 會員稽核、1 比賽稽核與其他原表所有舊欄位逐一比對完全一致。原副本當時尚無比賽報名紀錄，不將其描述為已匯入 9/20 參賽名單。

遷移後 integrity_check／foreign_key_check、Alembic check、再次備份還原比對均通過。結果在 `data/club-preview-verification.json`；檢查完後僅新增預覽管理員及兩則事實性使用說明公告，不新增虛構比賽或真實會員報名。`data/fucheng.db` 與 `data/competition-case.db` 主檔雜湊在操作前後一致；未對原庫遷移或回寫。

8032 已由舊合成預覽切換到這個副本，首頁 HTTP 200，公開 API 現有 327 會員、2 公告與 1 已公開比賽；公開會員欄位恰為 id／name／distinguishing_note／level。管理帳密檔為 `data/club-preview-admin.json`，背景程序 PID 檔為 `data/club-preview.pid`。舊合成資料保留。啟停、備份路徑與限制見 README。

原工作目錄／分支不變，仍為 `feat/member-self-registration`，HEAD 為 2679bf4，尚未 commit、合回 main、推送或正式部署。沒有額外 worktree。尚未完成真實手機現場試用、外網 HTTPS 與 Linux/systemd 部署；自動開放報名時間與公告預約發布不在本輪，預告可由公告提供。

## 第三階段歷史驗收：免登入選名報名

2026-09-17 依使用者確認改為公告欄式選名報名，會員帳號與自助取消方案已撤下。工作目錄 `D:\projects\fucheng-players-system`，分支 `feat/member-self-registration`，該次驗證的起始／當時 HEAD 為 `2679bf4ff61a06528bc11c604a2f4fd219491bdf`。當時變更未提交，沒有額外 worktree、合併、推送或正式部署。

- 後端：`uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-public2`，**34 passed**（17.02 秒），僅 2 則既有上游 deprecation warning。
- 前端：`npm run typecheck`、設定 `FUCHENG_BUILD_DIR=../frontend/dist-public` 後 `npm run build` 通過；依賴／lockfile 未變。
- 瀏覽器：`npm run test:e2e`，**6 passed**（20 秒），桌面 1440×900／手機 390×844，各涵蓋會員管理、比賽管理與免登入報名。
- Migration：`0003_public_registration`。合成第二階段資料 upgrade、逐欄保留、Backup API 備份及還原、integrity_check／foreign_key_check 通過；只對新合成預覽執行 `alembic check`，No new upgrade operations detected。

餐食選項調整：公開報名僅顯示葷食／素食，預設葷食，API 拒絕 unset；歷史資料仍保留未設定。調整後執行 `uv run --locked pytest -q tests/test_public_registration.py -p no:cacheprovider --basetemp .test-tmp-public-meals`（14 passed）、`npm run build` 與 `npm run test:e2e -- --grep "免登入搜尋"`（桌面／手機共 2 passed）。瀏覽器確認只有兩個選項、預設葷食，改選素食後失敗重送仍保留選擇。

### 核心證據

1. 候選搜尋需要姓名，返回最多 20 筆 id／name／distinguishing_note；同名東區／西區可精確選擇，不公開級數、預設餐食或名單。空查詢／LIKE wildcard 不可取得全表，停用會員不列出。
2. 沒有會員帳號 API／資料表，也沒有匿名取消、更正、遞補或歷史 API。匿名上下文不能取得管理權限。CSRF 缺少／跨來源拒絕，額外 status／sequence／level／reason 欄位拒絕。
3. 5 位不同會員同時報容量 3：3 正取、2 候補。管理員取消正取後 2 正取／2 候補／1 空位；3 位新會員同時報名皆候補，原取消者重新報名排最後。管理員確認第一候補後為 3 正取、5 候補、0 空位，餐食統計正確。
4. 同會員同時提交：相同 key 回同筆、不新增第二筆稽核；不同 key 一次成功、一次 409。跨 visit 或內容重用 key 拒絕，換訪客用新 key 重報也拒絕。
5. 草稿／截止／結束／取消及仍為 open 但已到截止時間均禁止新增；會員停用不取消既有報名，餐食／硬實力快照不被後續預設資料修改回寫。
6. 人工注入稽核 trigger 失敗後，報名、next_sequence、稽核完整回滾。CHECK 拒絕 public actor 同時帶 admin_id。過期 visit 在取得寫鎖後再次驗證回 401；速率限制、Secure／HttpOnly／SameSite cookie 測試通過。
7. 升級合成庫含 5 會員、1 管理員、1 比賽、2 正取／2 候補／1 取消及各類舊稽核，所有舊欄位與候補序保留，備份還原一致。故意注入舊外鍵錯誤，migration 失敗後 DDL 與 revision 回到第二階段。

### 真正瀏覽器及預覽

桌面與手機各執行：管理員建立比賽與先加入正取／候補；全新匿名瀏覽器直接開首頁，搜尋同名會員、選西區、選素食、確認報名成為候補；管理員取消後再匿名重報，管理名單確認順位由 3 變 4。失敗請求保留姓名與餐食，成功頁沒有取消操作，管理員可辨識免登入來源並執行取消及查看稽核。前兩階段管理流程與列印也通過。

截圖在 `frontend/test-results`，包括 `public-confirm.png`、`public-receipt.png`、`public-admin-audit.png`。已檢視手機確認與結果畫面，調整標題與連結對比，手機結果頁無水平溢位。測試使用 `data/public-e2e.db`、8031、`frontend/dist-public`。

預覽 [http://127.0.0.1:8032/](http://127.0.0.1:8032/) 已切換免登入版，使用全新 `data/public-preview.db`。選合成賽、搜尋「王」或「陳」可操作；只有管理員帳密在本機 `data/public-preview-admin.json`。原 8012、原會員庫及 9/20 案例庫保留，沒有正式資料操作。舊帳號版合成庫保留但不再使用；其未提交原始碼封存在 `backups/account-flow-source-before-public-registration.zip`，不含帳密或資料庫。啟停見 README。

### 限制及未執行項目

選名登記不驗證本人，可能代報；CSRF／速率限制／唯一約束只提供技術防護，不代表本人確認。取消、更正與遞補由管理員處理。搜尋會公開必要姓名與辨識註記，並非完整會員資料對外公開。正式 DB 升級、Linux/systemd、實際 HTTPS、球館現場與長輩可用性尚未驗收，步驟見 deployment.md。

## 第一、二階段歷史證據

- 基準：Windows x86-64 開發機、一般 CPython 3.14.6、uv 0.12.15、Node.js 24.11.0、npm 11.6.1。
- `uv sync --locked` 可建立專案 `.venv`；FastAPI 0.141.1、SQLAlchemy 2.0.53、Alembic 1.20.0、Pydantic 2.13.5 可安裝與匯入。
- 後端自動測試涵蓋：空資料庫 Alembic 遷移、SQLite pragma／級數／會費期間約束、未登入禁止管理、登入／登出失效、CSRF、公開敏感欄位排除、重名、改名、停用／恢復、修改歷史、交易失敗、過期版本衝突、備份還原。
- 前端 `npm audit --audit-level=high`、TypeScript 檢查與 Vite 正式建置通過。
- Playwright 以桌面 1440×900 及手機 390×844 執行：登入、新增、修改、公開名單、搜尋、級數篩選、列印模式、手機無水平溢位。
- 備份以 SQLite Backup API 建立，還原至另一個乾淨資料庫並核對內容與 `integrity_check=ok`。

## 第二階段已驗證

- 後端完整測試 `20 passed`。新增情境包含：名額 3／報名 5、正取取消不自動遞補、新報名不搶候補空位、第一有效候補確認、候補取消與重新排尾、增加／非法降低名額、截止後理由、終態唯讀、會員停用保留報名、當次餐食與硬實力快照、權限、CSRF、版本衝突、idempotency 重送、兩人競爭最後名額、兩管理員同時遞補及稽核失敗整筆回滾。
- Alembic 測試先建立 `0001_member_management` 的合成會員／帳號／稽核資料，再升級 `0002_competition_registration`；舊資料保留且新表初始為空。
- 前端 `npm audit --audit-level=high` 為 0 個已知漏洞；TypeScript 檢查與 Vite production build 通過。成品 JavaScript gzip 66.53 kB、CSS gzip 3.52 kB。
- Playwright 在 desktop 1440×900 與 mobile 390×844 執行會員及比賽流程，共 `4 passed`：建立比賽、加入正取／候補、取消不自動遞補、人工遞補、餐食摘要、全場與篩選摘要分離、衝突時保留輸入、管理名單列印與手機無水平溢位。
- 真實資料的只讀案例流程：從運作中資料庫使用 SQLite Backup API 建立 `backups/competition-phase2-source-20260916.db`，還原為 `data/competition-case.db` 後才升級。升級前後及再次備份還原皆 `integrity_check=ok`，會員 327、管理員 2、會員稽核 649 筆完全相同；原 `data/fucheng.db` 未遷移、未寫入。
- 9/20 圖片逐格確認為 8 欄 × 10 個有姓名的格子，共 80 人，不是用空表格容量推算。精確姓名對照結果：44 筆單一啟用匹配、29 筆無精確匹配、1 筆同名多候選、6 筆辨識待確認；沒有模糊比對或自動新增會員。圖片只有 1 筆明確素食標記，其餘已匹配者的提案餐食來源標為會員預設。

案例尚未建立正式比賽或報名列，因為年份、正式名額上限、報名截止時間仍待使用者確認，而且圖片順序不是報名先後；在這些資料不足時建立候補會捏造順位。來源轉錄與含會員 ID 的對照報告只在 Git 忽略的 `data/`，來源圖片仍在使用者指定的下載目錄。

## Python 3.15 調查

2026-09-16 時 Python 3.15 正式版尚未發布，官方時程為 2026-10-01；當下是 rc2。實測 `uv 0.12.15` 的下載清單雖顯示 rc2，但指定 `3.15.0rc2` 回報 `No download found`，指定或重裝 `3.15` 反而安裝 3.15.0b2，且首次解算帶入 Pydantic 2.14.0b2。這個預發布組合不作為第一版正式基準，因此採目前可安裝的穩定 CPython 3.14.6 與 Pydantic 2.13.5。

Python 3.15 正式版發布後，應更新 `.python-version` 與 `requires-python`，刪除並依 lockfile 重建獨立 `.venv`，重新執行匯入、Alembic、API、資料庫、完整測試與負載測試；未完成前不可宣稱 3.15 已支援。

## 尚未驗證與現場驗收

- 尚未在 Linux systemd 實機執行；本次 Windows 主機沒有可用的 Linux 執行環境（WSL 發行版列舉亦遭主機拒絕）。目前只有 service／timer 範本、強化設定與操作文件。部署主機需執行 `systemd-analyze verify`、啟停、重啟後健康檢查與權限測試。
- 尚未建立 Cloudflare Tunnel、網域、外部帳號或公開部署。
- 尚未在 2 GB 雙核心舊筆電、20 GB 實際磁碟或球館 Wi-Fi 驗收。開發機負載結果只能證明此程式與測試條件，不能外推到目標硬體。
- 尚未由真實管理員與長輩使用者進行現場可用性驗收。本機已有經使用者授權匯入的真實初始名單，但自動測試、負載測試與列印驗證仍只使用合成資料；授權匯入不等於現場可用性驗收。
- 正式上線前要以去識別或經授權的資料演練遷移、備份、還原、帳號復原、HTTPS cookie 與失敗回復。

## 第一版既有結果

- 後端：鎖定環境重建後為 `15 passed`；另有 FastAPI／Starlette 測試客戶端的上游 deprecation warning 2 則，沒有測試失敗。測試涵蓋一次性 CSV 匯入、重名、交易內稽核、防止重複匯入、未設定葷素的具名管理員回填，以及備份／還原危險路徑拒絕。
- 前端：`npm ci`、型別檢查與 Vite 7.3.6 production build 通過；成品 JavaScript gzip 63.31 kB、CSS gzip 2.66 kB；npm audit 為 0 個已知漏洞。
- 瀏覽器：Playwright desktop + mobile `2 passed`；包含衝突提示、輸入保留、多級對照、390×844 手機無水平溢位及長姓名不裁切。列印另以 327 筆合成資料（各級筆數同目前名單）驗證 11 欄、42 列，產出的 PDF 為單頁 A4 橫式，Poppler 重新渲染確認標題、表頭、內容與頁面邊界無裁切。
- 備份還原：除自動測試外，另以 E2E 合成資料庫執行 CLI 一致性備份並還原到新的乾淨目的地；來源與還原檔皆為 `integrity_check=ok`，會員筆數相同。
- 混合負載：單一 Uvicorn worker，100 使用者在 10 秒內逐步到站、每次瀏覽停頓 0.8～2.5 秒、每 5 秒一筆管理寫入；62.3 秒共 3,421 requests，0 errors（0.0000%），p50 4.1 ms、p95 7.9 ms、p99 15.6 ms、max 33.3 ms；服務程序 RSS 89.6 MiB、CPU 5.75 秒。
- 上述負載在 Windows x86-64 開發機與合成小型資料集完成；不是 Linux systemd、2 GB 目標硬體或球館網路的驗收數字。

## 比賽刪除／還原驗證（2026-09-18）

- `uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp-delete-all`：45 passed，2 項既有上游棄用警告。新增 4 項驗證覆蓋管理權限、CSRF、必須確認、版本衝突／重送、刪除與報名並行、刪除／還原稽核失敗整體回滾、公開入口隱藏、所有名單寫入阻擋，以及還原後餐食／級數／排序與報名稽核保持原狀。
- `cd frontend; npm run typecheck`、`npm run build -- --outDir ../frontend/dist-delete` 通過。
- `$env:FUCHENG_E2E_STATIC_DIR='frontend/dist-delete'; npm run test:e2e`：12 passed，desktop 1440×900、mobile 390×844。新情境實際透過瀏覽器建立比賽、查看確認名稱與人數、安全焦點、Escape／保留、確認刪除、已刪除唯讀名單、再次確認還原；既有會員、報名／候補、80 人匯入、公告與公開網站流程一併通過。截圖位於 frontend/test-results/competition-deletion-*/delete-confirmation.png 與 restored-roster.png，已目視檢查桌面／手機確認視窗。
- 初次 E2E 的新選單定位及共用帳號超過 10 次登入限制已修正：新情境使用另一個合成管理員，保留正式速率限制，再完整執行 12 項通過。
- 合成第二階段 schema 升級至 head 並備份還原的既有測試通過，保存會員、管理員、所有報名狀態及候補順序、舊稽核。獨立新版預覽亦逐欄核對原有 342 會員、2 場比賽、81 報名及其他表，升級後備份還原、integrity_check、foreign_key_check、Alembic check 均通過；來源庫雜湊未變。完整報告：data/club-delete-preview-verification.json。
- 原 8032／8033 與其成品、資料庫未改；沒有對真實場次做刪除測試。最新預覽為 8034／data/club-delete-preview.db，兩份預覽資料獨立。正式資料庫遷移與 Linux／HTTPS 部署、球館實機手機驗收仍未執行。

## Git 整合範圍（2026-09-18）

使用者於功能驗收後授權將目前全部更新提交、合併至 main 並推送 origin。此次範圍為首頁／公告、公開會員分級、免登入報名、已確認名單批次匯入、可還原的比賽刪除，以及相關遷移、測試與文件；不包含真實資料、資料庫、帳密、備份或建置成品。功能分支起點為 2679bf4，main 可快轉至相同已驗證程式；後續工作從整合後 main 接手。

整合沿用本頁最近記錄的 45 項後端與 12 項 E2E 通過結果，驗證後僅調整文件接手敘述及預覽腳本的 schema revision 回報。Git 發布不代表資料庫遷移或正式部署；8032／8033／8034 預覽程序及各自資料保持不變。
