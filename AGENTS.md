# 專案指引

## Docker部署共同規則

- 單一app image包含React成品＋FastAPI，SQLite用Linux named volume；維護／備份復用image。正式Tunnel直連app，nginx只供https-test，見docs/deployment.md。
- 透過scripts/deployment_package.py的allowlist staging與source manifest建置；禁止data／帳密／備份／既有dist入context、image或離線包。未提交版標snapshot與hash。
- volume寫入經runtime.py生命周期鎖與maintenance守門；start不migration。遷移先停寫、備份，回退匹配image/schema並還原新目標、保留故障庫。不繞過guard直接寫volume。
- 部署驗證僅獨立project/port/volume合成資料；真實資料來源與操作另授權。公開Tunnel須另行明確授權，不動既有服務，禁止prune／down -v。

## 範圍與共同約束

- 目前包含球館首頁、公告管理、公開會員分級、會員／比賽管理、「免登入選名報名」、精確格位安排表（文字標題／插行列／文字空格合併）及完整安排保存／唯讀歷史／當次安排列印；會員帳號、自助取消、分隊／對戰引擎及正式部署不在範圍。
- 公開分級名單允許免登入查看姓名、級數、辨識註記與內部選取 ID；報名候選不提供級數。公開名單不得含餐食、原會員編號、帳號、會費或稽核，回應使用明確 schema。
- SQLite 每個連線維持 `foreign_keys=ON`、`busy_timeout=10000`、WAL 與 `synchronous=FULL`；會員／比賽／報名／公告修改與各自稽核紀錄必須同一交易。
- 姓名可重複；`members.id` 才是識別。未知葷素保持 `unset`。停用不等於刪除。
- 管理寫入需要後端 session 權限與 CSRF；更新必須檢查 `version`，不可靜默覆寫。
- 合成測試資料不得換成對話圖片或未授權的真實會員資料。
- 會員 level、不可回寫的 hard_level_snapshot 與報名列 competition_level 各自獨立。僅 open／closed 場次正取可調級，調級原因可省略且稽核留空，不假造原因；其他操作原因規則不變。取消保留歷史，重報以新快照初始化，候補遞補保留原列當次級數；不可用當次級數替換既有快照統計語意。
- 起始安排基準以 auth／CSRF POST 或首次合法調級前同交易建立一次，GET／migration 不補造歷史。完整安排快照不可變，保存須在 BEGIN IMMEDIATE 核對完整名單 token 與最新基準，固定 request_id 綁定 actor／payload，快照及稽核同交易。顯示編輯者與實際 admin 分開；淨差按報名 ID 比較上一保存版，不用 hard_level_snapshot 充當基準。

## 已驗證指令

```text
uv sync --locked
uv run --locked pytest -q -p no:cacheprovider --basetemp .test-tmp
cd frontend && npm ci
cd frontend && npm audit --audit-level=high
cd frontend && npm run typecheck
cd frontend && npm run build -- --outDir ../frontend/dist-public
cd frontend && npm run test:e2e
```

Python 使用 uv、`pyproject.toml`、`uv.lock` 與專案 `.venv`；前端使用 npm 與 `package-lock.json`。正式服務不在啟動時安裝依賴，也不常駐 Node.js。文件入口見 `README.md`。

免登入新增報名使用自動訪客上下文與 CSRF，共用 `registrations.py` 的寫鎖交易及 actor／payload 綁定 idempotency。選名不證明本人，稽核用 public visit，不假冒 member actor；取消、更正、遞補只限管理員。E2E 用 `data/public-e2e.db`、8031、`frontend/dist-public`，不可覆寫原服務成品或資料。

不可覆寫既有 dist-public／dist-delete／dist-levels／dist-level-drag 或舊預覽 DB。本輪安排保存驗證使用 dist-arrangement、FUCHENG_E2E_DATABASE_URL=sqlite:///data/arrangement-e2e.db、FUCHENG_E2E_PORT=8040、FUCHENG_E2E_STATIC_DIR=frontend/dist-arrangement；人工合成預覽為 8039／arrangement-preview.db，與測試及原8037預覽隔離。重建／重啟使用中的成品前確認該服務用途；舊 Docker／ngrok 升級另依授權及維運契約。

## 精確格位安排共同契約

- 布局使用 stable row/column ID 與 header/body 角色；十個級數欄語義固定，文字欄不代表級數。插空列的索引移動不等於重新分組。搜尋只顯示匹配姓名，其他選手保持無姓名的已占用格；素食按本場 registration.diet 高亮，不篩掉人、不寫入。
- 拖到選手中央交換兩人；上下邊界插入並向下讓位，空格直接移動來源留洞。payload明確swap／insert／move_empty，放手採已顯示預告；legacy move保留插入語義。文字／合併／header不可落人，固定十級身份不變。跨級swap兩人level/version與各自稽核同交易，整操作receipt防重；其他人不動。舊level API與正取新增／取消／遞補同交易同步布局。
- 僅文字／空格可合併，跨數字級數標頭或多段非空文字衝突須拒絕；解除保留原底格文字座標。合併可直接改字，保留原非空文字來源格；空白區才用anchor。欄title只改顯示，missing/null以原級數或文字欄標題呈現，不能改十級身份。完整快照含 rows/columns/cells/merges。0007 歷史 layout=null/schema_version=1，未保存位置／餐食／長期級數維持未知，禁止回填現況。
- 小存与大存固定 request_id／actor／payload、同場串行，未知或待讀回時整場鎖；409重新核對，不自動重算目標。文字草稿按場次與 stable cell 保存，成功讀回後才清除。
- B 使用獨立 worktree 環境；本機合成預覽8042／data/grid-preview.db／dist-grid，E2E8043／data/grid-e2e.db／dist-grid；不要在預覽使用中重建成品。現用 A 的主目錄、8041／f9d0、DB／static／密碼／Docker均不由B操作。後續公開交付另依授權。

當次安排列印使用當前所檢視的完整 rows/layout，搜尋不裁名單，所有已知本場素食印「素」，歷史未知不補現況。列印只能browser print/PDF驗證，不操作實體印表機。新版格位編輯驗證用獨立dist-grid-edit、data/grid-edit-e2e.db、8043，不覆寫現用static/DB；無新增migration。

刪除行／自訂文字欄只依stable axis ID與確認時token執行，不按更新後索引重算；固定十級欄、含選手行及最後body行拒絕刪除。文字須明確範圍確認；受影響merge保留合法剩餘區與唯一文字（必要時搬到剩餘anchor），衝突拒絕。刪軸不改其他選手座標／報名version；成功且讀回驗證後才清除已失效選格、編輯器及草稿，失败／未知保留原請求與輸入。

灰階以row／自訂文字column的shade 0–3保存，missing視為0、GET不回填舊JSON；交叉與merge涵蓋軸取max，不疊加。灰階入完整保存／淨差／歷史／列印，列印用實體SVG填色以保留背景圖形關閉時的灰階。歷次級數參考僅admin查同member confirmed、未刪ended、日期早於所選且不晚於台北今天的最近5場registration.competition_level；不回寫快照或擴public schema。


局部色cell_shades綁stable格位、strict1–3 override軸色，0只清除；merge閉包選取且保底格，delete軸prune，空色不佔位。undo僅依server成功receipt前狀態及目前head/token/revision，同actor/基準驗證後以新transaction/receipt留存；version不得倒退，不接受client任意snapshot、不刪歷史。大保存與外來更新斷鏈；本頁stack失敗不pop，unknown固定payload重試。新增契約仍schema0008但不保證舊app可無損回退。本輪驗證8043/grid-undo-e2e.db/frontend/dist-grid-undo，保留前輪dist-grid-cell-shade與全部現用成品。


固定表頭用column顯示選取，header_shade只影響th/print、不得染body或改level/id；表頭/body選取互斥且不混選merge。安排專用請求等待涵蓋完整body，逾時寫入保持unknown與原key/payload；receipt後讀回逾時保持refresh，只重讀不再POST。新版驗證frontend/dist-grid-header/grid-header-e2e.db/8043，不覆寫現用grid-undo成品。
