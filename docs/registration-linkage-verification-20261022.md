# 公開報名與管理端連動驗證（2026-10-22）

公開報名與管理名單、當次安排及統計的核心連動驗證通過，本輪沒有發現需修改產品的報名連動錯誤。已開啟的管理頁需透過「報名與設定」「排級數」或重新載入讀回最新狀態；取消正取後只標示待遞補，管理員須手動確認候補遞補。

## 驗證來源與範圍

起點為 `feat/club-report-upload`／`f5e17259b6c25a9e8ba2b3ca87a155a932ca82ca`加既有健檢回傳工作樹；本次只將自身版本改為0.4.3、保留回歸測試與更新文件。先前部署source manifest的80檔中，除四份版本metadata，其餘76檔逐一hash相同；依賴lock也只改自身版本。Linux／Python3.14.6／pytest8.4.2；瀏覽器為本機Chrome，全部使用新建合成會員／場次／SQLite，沒有操作真實會員資料。

## 後端永久回歸

[tests/test_registration_linkage.py](../tests/test_registration_linkage.py)沿用既有fixtures與`tmp_path`，不另建測試框架、不輸出情境JSON。四情境如下：

1. 公開正取／候補後核對管理報名列、安排rows／cells、公開與管理人數、餐食、原始級數及當次級數統計；取消、FIFO手動遞補、再報名以新ID／序號／新快照加入。另一場報名及兩個舊保存版保持原值。
2. 有正取名額時，刪空級數欄後GET不補造；注入workspace更新失敗，報名、序號、audit及layout全回滾；移除注入後以原request_id重試，在同交易用新stable ID補欄。
3. 額滿後公開候補不占格、不補欄；取消正取再手動遞補，於同交易補回缺少級數欄並放入正確格位，不改舊保存版。
4. 管理端與三個公開請求併發搶最後名額，同會員同時從兩入口報名；三筆201、一筆409，只一正取、兩候補，會員／序號唯一且audit恰三筆。舊state_token保存回409，重新讀回後可保存。

2026-10-22完整後端回歸：**273 passed，77.93秒，2 warnings**。其中四項是上述新增情境；獨立PowerShell傳輸測試另列，未混入273項。

```bash
UV_CACHE_DIR=/tmp/fucheng-release043-uv-cache uv run --locked --no-sync pytest -q -p no:cacheprovider --basetemp data/release-0.4.3/backend-tmp tests --ignore=tests/test_host_report_sender.py
```

執行經正式沙箱批准，因受限環境的TestClient會停在anyio portal；沒有修改產品或放寬驗證。log為ignored `data/release-0.4.3/backend-pytest.log`。既有94項專案範圍測試與四情境的先前分項證據保留於`data/registration-linkage-20261022/backend/`。

## 瀏覽器連動

先前四組核心情境全部通過：根路徑／`/fucheng`各桌面與手機，使用獨立管理員／匿名瀏覽器contexts。確認同名辨識、正取／候補收據、餐食、模式切換讀回、缺欄補回、取消不自動遞補、手動遞補、再報名、新ID／序號、切場／重載及public／admin稽核；沒有pageerror或水平溢出。

本次0.4.3獨立build的HTML／CSS／JS三檔SHA-256與上述實際瀏覽器成品完全一致；原summary、截圖及觀察保留於`data/registration-linkage-20261022/frontend/summary.json`，比對記錄為`data/release-0.4.3/evidence-reuse.json`。歷史四組保留為補充證據，不重複加入本次執行計數。

已將核心情境保留為[正式Playwright測試](../frontend/e2e/registration-linkage.spec.ts)，沿用既有seed／正式config自動發現，不修改共用框架；移除要求「固定3秒必須沒有自動刷新」的斷言，避免將目前限制固定為長期契約。

本輪另用ignored獨立config指向同一正式測試檔與本次成品，僅接受全新合成DB及專用8088／8089：根路徑、`/fucheng`各桌面／手機，**4/4通過**，兩路徑各2 passed、9.1／9.0秒，skipped／unexpected／flaky均0。已檢視桌面／手機最終截圖，並以connect_ex確認兩port均ECONNREFUSED；沒有停止其他服務。

```bash
FUCHENG_LINKAGE_RUN=r2 node frontend/node_modules/@playwright/test/cli.js test --config data/release-0.4.3/playwright.config.ts
FUCHENG_BASE_PATH=/fucheng FUCHENG_LINKAGE_RUN=r2 node frontend/node_modules/@playwright/test/cli.js test --config data/release-0.4.3/playwright.config.ts
```

重現時須換全新run ID，runner拒絕覆寫既有DB。結果、log、截圖及cleanup證據保留於`data/release-0.4.3/`的`e2e-results-{root,prefix}-r2.json`、`e2e-{root,prefix}-r2.log`、`test-results-{root,prefix}-r2/`與`e2e-cleanup.json`。初次config缺ESM設定而未啟動，修正後r1因worker重新產生動態密碼、與server seed不符，在登入即失敗；修正測試config沿用父程序動態密碼後，以新r2 DB通過，未改產品或減弱斷言。失敗證據保留，臨時合成密碼欄已遮蔽。

## 既有E2E限制與未驗證項目

先前抽跑的舊E2E並非全部通過，以下失敗照實保留：

- `competition-flow`桌面：報名／取消／遞補／餐食步驟完成，最後舊列印斷言只emulate print，沒有開啟目前的PrintPreview。
- `self-registration`手機：舊selector指向手機隱藏的桌面grid，在匿名報名步驟前即失敗；本次核心手機情境使用實際手機清單及dialog。
- `flexible-level-columns`桌面／手機：刪欄／加欄／保存已完成，重載後舊測試未重新選回自己的場次，檢查了另一場。完整舊測試仍記為failed。

這些舊測試本輪未修改，沒有宣稱全量E2E通過。正式站、真實Turnstile、球館Windows／網路、實體手機、實體印表機及人工接受均不在本輪合成連動證據內。工具回傳的六項實際PowerShell TLS fixture證據及Windows限制另見[健檢回傳驗證](host-report-verification-20261022.md)。
