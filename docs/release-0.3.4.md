# 0.3.4：手機安排表拖曳與素食名單

手機直接拉動人員時，舊版長按判定容易觸發選單、遮住目標。此版移除「名單操作」和模式切換，在同一安排表提供手機專用手勢：滑姓名區捲動、拉 44px 把手移動、點 ⋯ 開啟選單。桌面右鍵與鍵盤操作保留。

- 拖曳不必等待長按；交換、插入、空格移動仍以畫面預告提交。長按選單、拖曳中選單及第二指介入不會誤寫。未知結果保留原 request ID／payload；起拖 token 遇到外來修改以 409 拒絕。
- 手機單雙點使用有效 pointerup，修正瀏覽器在失敗恢復後漏送第一次 click 的情況；取消與滑動清除點按計數。
- 登入名稱移到下一行、備份狀態標籤右側。
- 素食按鈕右上新增唯讀名單，顯示當次級數、隊長、姓名與同名辨識。隊長暫按同一橫列固定 1 級選手判定；搜尋不裁名單，歷史缺位置或餐食不補現況。

## 驗證

根路徑與 `/fucheng/` 核心各 12 passed，另各 2 個 desktop 觸控專用 skip；桌面／手機回歸 20 passed，最終多指／點按防護補驗 4 passed（包含於上述回歸範圍）。型別、正式建置、diff check 通過，npm audit 0 vulnerabilities。獨立唯讀審查未發現阻斷問題。詳細證據見 [驗收紀錄](acceptance.md)。Android／iPhone 真機手感仍待使用者驗收，模擬測試不代表人工接受。

## 升級與搬移

同步 Python／npm metadata 至 0.3.4；沒有後端、migration 或依賴變更，schema 仍為 `0010_deployment_report`。以 allowlist staging、來源 manifest 建置 Linux/amd64 單一 app image，禁止帶入資料、秘密、備份或既有 dist。

家中更新既有 4090 Docker project，公開路徑仍為 `https://momonong.me/fucheng/`；app／backup／ops 同批固定新 digest。更新前停止寫入，透過 runtime 備份與成組 export，再啟動並核對資料 fingerprint。保留帳號、原 volumes、舊映像及回復資料，不做 migration 或重新灌入資料。

日後球館 Windows Docker Desktop／WSL2 可用相同 Linux image，以 runtime 前綴與 origin 配置根路徑；資料透過成組備份還原搬移。GitHub release、映像發布與實際部署分別確認，部署證據見 [家中部署紀錄](home-deployment.md)。
