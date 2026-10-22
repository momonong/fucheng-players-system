# 空白欄與選手級數

2026-10-22 確認：新增空白欄直接放人，空白欄只換位置；數字級數欄保留原調級行為。

## 操作

- 表格上方「＋ 新增空白欄」直接在最右側新增；欄邊界的＋在該處插入。新增欄預設空標題，可直接改字，不挑選級數。原「加回級數欄」選單移除。
- 新欄與既有 `kind=text` 欄的 body 空格均可放選手或文字。放入普通欄只改座標，保留該選手的 `competition_level`。移入 `kind=level` 欄仍改成該欄級數；交換兩人時，分別依兩人的目的欄決定，不互換兩人的級數欄位。
- 文字格、合併區、表頭仍不可放人；一格仍只能有一位選手。刪除有人的欄必須先移走選手；至少一個數字級數欄及一排 body 的原保護維持。總欄數50、普通欄40的原上限維持。
- 普通欄中的選手改餐食或明確調整當次級數，均保留座標。數字欄中的明確調級仍依舊契約移往對應欄底；明確「移到級數」仍代表移往該數字欄。新增正取／遞補沿原規則定位，缺少該級數欄時同交易補回。
- 會員級數及報名時 `hard_level_snapshot` 不受上述操作影響。原歷史、列印與 Excel 外觀維持；普通欄內選手依保存的 registration ID 與 rows 呈現，不由欄名推斷級數。

## JSON 與舊分頁

布局文件 `schema_version=2` 表示普通欄可放人；資料表不變，不新增 migration。既有 workspace、初始化布局、保存版及 receipt 不由 GET 或 migration 回填。新前端每筆安排操作送 `layout_schema_version:2`，只在成功寫入交易將 mutable workspace 升級；無變更或失敗操作仍回滾，不為能力升級製造安排淨差。

缺少能力欄位的表格操作（grid operation）請求視為 legacy 1，只能繼續操作 schema 1 布局。schema 2 拒絕 legacy 表格操作的新寫入並回409，提示重新整理。request ID 的既有 receipt 先於能力／token 檢查回傳，因此舊 unknown 請求仍可用原 key／payload 確認；不能利用能力升級換掉原請求。新前後端須同批更新，schema 2 不支援直接退回只接受 schema 1 的舊 app。

## 復原、重做與驗證

新 server receipt 私有 `_undo` 同時保存前後完整 `registration_id → competition_level`，不回傳給 client 作任意 snapshot 寫入。Undo／Redo 核對 actor、完整 token、revision、保存基準、順序、目前布局與級數，另驗證快照的名單集合、級數1–10及布局。目的普通欄不再能推導級數，必須從 server 的級數快照還原。舊 receipt 只有 schema 1 且所有選手位置可從數字欄確定級數時才相容；缺少級數快照的 schema 2 紀錄拒絕復原。

復原不把 mutable workspace 降回 schema 1；revision 與受影響報名 version 單調增加，級數稽核與布局／receipt 同交易。unknown 保留原 key／payload；成功 receipt 後讀回失敗只重讀。

合成驗證入口為 `tests/test_neutral_columns.py`，涵蓋普通欄移動／插入、雙向及雙普通欄交換、會員與快照不變、餐食／調級／取消／遞補／新增同步、不可變歷史、復原重做、舊讀取及舊分頁拒絕、損壞 server snapshot 與交易回滾。`frontend/e2e/neutral-columns.spec.ts` 驗證桌面／觸控新增與拖曳、完整保存／重載／唯讀歷史、瀏覽器列印及 Excel；實際執行結果以本輪 release 收據為準，不代表正式部署或人工接受。
