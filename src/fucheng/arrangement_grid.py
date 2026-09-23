"""Bounded spatial document operations. Callers own the SQLite write transaction."""
import json
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import Field, BaseModel, model_validator

from .models import ArrangementWorkspace, CompetitionAudit
from .schemas import StrictInput

MAX_ROWS = 500
MAX_COLUMNS = 50
HEADER_ROW_ID = "column-headers"

class CellAddress(StrictInput):
    row_id: str = Field(min_length=1, max_length=36)
    column_id: str = Field(min_length=1, max_length=36)

class MoveCell(StrictInput):
    action: Literal["move"]
    registration_id: str = Field(min_length=1, max_length=36)
    target: CellAddress

class SwapCells(StrictInput):
    action: Literal["swap"]
    registration_id: str = Field(min_length=1, max_length=36)
    target_registration_id: str = Field(min_length=1, max_length=36)

class InsertPlayer(StrictInput):
    action: Literal["insert"]
    registration_id: str = Field(min_length=1, max_length=36)
    target: CellAddress
    side: Literal["before", "after"]

class MoveEmpty(StrictInput):
    action: Literal["move_empty"]
    registration_id: str = Field(min_length=1, max_length=36)
    target: CellAddress

class SetShade(StrictInput):
    action: Literal["shade_row", "shade_column"]
    axis_id: str = Field(min_length=1, max_length=36)
    shade: int = Field(ge=0, le=3, strict=True)

class ShadeHeader(StrictInput):
    action: Literal["shade_header"]
    column_id: str = Field(min_length=1, max_length=36)
    shade: int = Field(ge=0, le=3, strict=True)

class ShadeCells(StrictInput):
    action: Literal["shade_cells"]
    start: CellAddress
    end: CellAddress
    shade: int = Field(ge=0, le=3, strict=True)

class UndoOperation(StrictInput):
    action: Literal["undo"]
    target_request_id: str = Field(min_length=8, max_length=64)

class RedoOperation(StrictInput):
    action: Literal["redo"]
    target_request_id: str = Field(min_length=8, max_length=64)

class MoveBottom(StrictInput):
    action: Literal["move_bottom"]
    registration_id: str = Field(min_length=1, max_length=36)
    level: int = Field(ge=1, le=10, strict=True)

class InsertAxis(StrictInput):
    action: Literal["insert_row", "insert_column", "insert_header"]
    before_id: str | None = Field(default=None, max_length=36)

class DeleteAxis(StrictInput):
    action: Literal["delete_row", "delete_column"]
    axis_id: str = Field(min_length=1, max_length=36)
    confirmed_text: bool = Field(default=False, strict=True)

class SetText(StrictInput):
    action: Literal["text"]
    target: CellAddress
    text: str = Field(max_length=500)

class ColumnTitle(StrictInput):
    action: Literal["column_title"]
    column_id: str = Field(min_length=1, max_length=36)
    text: str = Field(max_length=500)

class MergeCells(StrictInput):
    action: Literal["merge"]
    start: CellAddress
    end: CellAddress

class UnmergeCells(StrictInput):
    action: Literal["unmerge"]
    merge_id: str = Field(min_length=1, max_length=36)

class HeaderRange(StrictInput):
    action: Literal["merge_header"]
    start_column_id: str = Field(min_length=1, max_length=36)
    end_column_id: str = Field(min_length=1, max_length=36)

class UnmergeHeader(StrictInput):
    action: Literal["unmerge_header"]
    merge_id: str = Field(min_length=1, max_length=36)

class HeaderText(StrictInput):
    action: Literal["header_text"]
    merge_id: str = Field(min_length=1, max_length=36)
    text: str = Field(max_length=500)

Operation = Annotated[MoveCell | SwapCells | InsertPlayer | MoveEmpty | SetShade | ShadeHeader | ShadeCells | UndoOperation | RedoOperation | MoveBottom | InsertAxis | DeleteAxis | SetText | ColumnTitle | MergeCells | UnmergeCells | HeaderRange | UnmergeHeader | HeaderText, Field(discriminator="action")]

class GridMutation(StrictInput):
    request_id: str = Field(min_length=8, max_length=64)
    state_token: str = Field(min_length=64, max_length=64)
    operation: Operation


class LayoutRow(BaseModel):
    id: str
    role: Literal["header", "body"]
    shade: int = Field(default=0, ge=0, le=3, strict=True)

class LayoutColumn(BaseModel):
    id: str
    kind: Literal["level", "text"]
    level: int | None
    title: str | None = None
    shade: int = Field(default=0, ge=0, le=3, strict=True)
    header_shade: int | None = Field(default=None, ge=0, le=3, strict=True)

class PlayerCell(CellAddress):
    kind: Literal["registration"]
    registration_id: str

class TextCell(CellAddress):
    kind: Literal["text"]
    text: str

class LayoutMerge(BaseModel):
    id: str
    start: CellAddress
    end: CellAddress

class CellShade(CellAddress):
    shade: int = Field(ge=0, le=3, strict=True)

class HeaderMerge(BaseModel):
    id: str
    start_column_id: str
    end_column_id: str
    title: str | None = None

class GridLayout(BaseModel):
    schema_version: Literal[1] = 1
    rows: list[LayoutRow]
    columns: list[LayoutColumn]
    cells: list[Annotated[PlayerCell | TextCell, Field(discriminator="kind")]]
    merges: list[LayoutMerge]
    header_merges: list[HeaderMerge] = Field(default_factory=list, max_length=MAX_COLUMNS//2)
    cell_shades: list[CellShade] = Field(default_factory=list, max_length=MAX_ROWS * MAX_COLUMNS)

    @model_validator(mode="after")
    def valid_cell_shades(self):
        rows, columns = {r.id for r in self.rows}, {c.id for c in self.columns}
        seen = set()
        for cell in self.cell_shades:
            point = (cell.row_id, cell.column_id)
            if point in seen or cell.row_id not in rows or cell.column_id not in columns:
                raise ValueError("局部底色座標重複或不存在")
            seen.add(point)
        return self

class GridReceipt(BaseModel):
    request_id: str
    competition_id: str
    revision: int
    operation: Operation
    layout: GridLayout
    state_token: str | None = None
    undo_head: str | None = None
    redo_head: str | None = None


def fail(message):
    raise HTTPException(422, message)


def new_id():
    return str(uuid4())


def key(cell):
    return cell["row_id"], cell["column_id"]


def cell_at(layout, row_id, column_id):
    return next((c for c in layout["cells"] if key(c) == (row_id, column_id)), None)


def region(layout, merge):
    rows = [r["id"] for r in layout["rows"]]
    cols = [c["id"] for c in layout["columns"]]
    a,b = sorted([rows.index(merge["start"]["row_id"]), rows.index(merge["end"]["row_id"])])
    x,y = sorted([cols.index(merge["start"]["column_id"]), cols.index(merge["end"]["column_id"])])
    return [(r,c) for r in rows[a:b+1] for c in cols[x:y+1]]


def covered(layout):
    return {point for m in layout["merges"] for point in region(layout,m)}


def address(layout, point):
    if point["row_id"] not in {r["id"] for r in layout["rows"]} or point["column_id"] not in {c["id"] for c in layout["columns"]}:
        fail("目的格已不存在，請重新讀取")


def append_row(layout):
    if len(layout["rows"]) >= MAX_ROWS:
        fail("安排最多 500 列，請先整理空間")
    row_id = new_id()
    layout["rows"].append({"id": row_id, "role":"body"})
    return row_id


def default_layout(rows):
    layout = {"schema_version": 1, "rows": [], "columns": [
        {"id": new_id(), "kind": "level", "level": n} for n in range(1,11)], "cells": [], "merges": []}
    for _ in range(max(8, max((sum(r["competition_level"] == n for r in rows) for n in range(1,11)), default=0))):
        append_row(layout)
    positions = {n: 0 for n in range(1,11)}
    for row in rows:
        n = row["competition_level"]
        layout["cells"].append({"row_id": layout["rows"][positions[n]]["id"], "column_id": layout["columns"][n-1]["id"],
            "kind": "registration", "registration_id": row["registration_id"]})
        positions[n] += 1
    return layout


def encode(layout):
    # Cell insertion order is not part of the persisted spatial meaning.
    normalized = {**layout, "cells": sorted(layout["cells"], key=key), "merges": sorted(layout["merges"], key=lambda m:m["id"])}
    if "header_merges" in layout:
        normalized["header_merges"] = sorted(layout["header_merges"], key=lambda m:m["id"])
    if "cell_shades" in layout:
        normalized["cell_shades"] = sorted(layout["cell_shades"], key=key)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def signature(layout):
    # Merge UUIDs are bookkeeping: merge->unmerge->same merge restores the same meaning.
    return {**layout, "header_merges": sorted(({"start_column_id":m["start_column_id"], "end_column_id":m["end_column_id"], "title":m.get("title")} for m in layout.get("header_merges",[])), key=lambda m:(m["start_column_id"],m["end_column_id"])), "cell_shades": sorted(layout.get("cell_shades", []), key=key), "rows": [{**r, "shade":r.get("shade",0)} for r in layout["rows"]], "columns": [{**c, "shade":c.get("shade",0), "header_shade":c.get("header_shade"), "title": c.get("title") if c.get("title") is not None else (str(c["level"]) + " 級" if c["kind"] == "level" else "文字／備註")} for c in layout["columns"]], "cells": sorted(layout["cells"], key=key),
        "merges": sorted(({"start": m["start"], "end": m["end"]} for m in layout["merges"]), key=lambda m: (key(m["start"]),key(m["end"])))}


def ensure_workspace(db, competition, admin_id, rows):
    workspace = db.get(ArrangementWorkspace, competition.id)
    if workspace:
        return workspace
    encoded = encode(default_layout(rows))
    workspace = ArrangementWorkspace(competition_id=competition.id, revision=1, layout_json=encoded,
        initial_layout_json=encoded, admin_id=admin_id)
    db.add(workspace)
    db.add(CompetitionAudit(competition_id=competition.id, admin_id=admin_id, action="layout_initialize",
        changes_json=json.dumps({"layout": {"before": None, "after": "schema 1"}})))
    db.flush()
    return workspace


def bottom_target(layout, level):
    col = next(c for c in layout["columns"] if c["kind"] == "level" and c["level"] == level)
    rows = [r["id"] for r in layout["rows"] if r["role"] == "body"]
    occupied = {c["row_id"] for c in layout["cells"] if c["column_id"] == col["id"] and c["row_id"] in rows}
    occupied |= {r for r,c in covered(layout) if c == col["id"] and r in rows}
    index = max((rows.index(r) for r in occupied), default=-1) + 1
    row_id = rows[index] if index < len(rows) else append_row(layout)
    return {"row_id": row_id, "column_id": col["id"]}


def move(layout, registration_id, target):
    address(layout, target)
    if next(r for r in layout["rows"] if r["id"] == target["row_id"])["role"] != "body":
        fail("選手只能放在資料列")
    column = next(c for c in layout["columns"] if c["id"] == target["column_id"])
    if column["kind"] != "level":
        fail("選手只能放在級數欄")
    source = next((c for c in layout["cells"] if c.get("registration_id") == registration_id), None)
    if source and key(source) == key(target):
        return column["level"]
    blocked = covered(layout)
    occupant = cell_at(layout, **target)
    if key(target) in blocked or occupant and occupant["kind"] == "text":
        fail("目的格含文字或合併區，請選擇選手格或空格")
    if source:
        layout["cells"].remove(source)  # Leave this hole; never compact the source column.
    carry = {**target, "kind": "registration", "registration_id": registration_id}
    row_ids = [r["id"] for r in layout["rows"]]
    index = row_ids.index(target["row_id"])
    while True:
        if index >= len(row_ids):
            row_ids.append(append_row(layout))
        point = (row_ids[index], target["column_id"])
        old = cell_at(layout, *point)
        if next(r for r in layout["rows"] if r["id"] == point[0])["role"] != "body" or point in blocked or old and old["kind"] == "text":
            index += 1
            continue
        if old:
            layout["cells"].remove(old)
        layout["cells"].append({**carry, "row_id": point[0], "column_id": point[1]})
        if not old:
            break
        carry = old
        index += 1
    return column["level"]


def player_cell(layout, registration_id):
    cell = next((c for c in layout["cells"] if c.get("registration_id") == registration_id), None)
    if cell is None:
        fail("選手已不在安排中，請重新讀取")
    if key(cell) in covered(layout) or next(r for r in layout["rows"] if r["id"] == cell["row_id"])["role"] != "body" or next(c for c in layout["columns"] if c["id"] == cell["column_id"])["kind"] != "level":
        fail("選手位置不是合法資料格")
    return cell


def explicit_move(layout, op):
    source = player_cell(layout, op["registration_id"])
    if op["action"] == "swap":
        target = player_cell(layout, op["target_registration_id"])
        if source is target:
            return
        source_point, target_point = key(source), key(target)
        source["row_id"], source["column_id"] = target_point
        target["row_id"], target["column_id"] = source_point
        return
    target = op["target"]
    address(layout, target)
    occupant = cell_at(layout, **target)
    if op["action"] == "move_empty":
        if occupant is source:
            return
        if occupant is not None or key(target) in covered(layout):
            fail("目的格不是空白格，請重新核對")
    else:
        if not occupant or occupant["kind"] != "registration":
            fail("插入邊界必須指向選手格")
        player_cell(layout, occupant["registration_id"])
        if occupant is source:
            return
        if op["side"] == "after":
            index = next(i for i,r in enumerate(layout["rows"]) if r["id"] == target["row_id"]) + 1
            while index < len(layout["rows"]):
                point = {"row_id":layout["rows"][index]["id"],"column_id":target["column_id"]}
                old = cell_at(layout, **point)
                if layout["rows"][index]["role"] == "body" and key(point) not in covered(layout) and (old is None or old["kind"] == "registration"):
                    target = point
                    break
                index += 1
            else:
                target = {"row_id":append_row(layout),"column_id":target["column_id"]}
    move(layout, op["registration_id"], target)


def delete_axis(layout, op):
    axis = "rows" if op["action"] == "delete_row" else "columns"
    field = "row_id" if axis == "rows" else "column_id"
    item = next((v for v in layout[axis] if v["id"] == op["axis_id"]), None)
    if item is None:
        fail("指定位置已不存在，請重新讀取並核對")
    if axis == "columns" and item["kind"] == "level":
        fail("1到10級的固定級數欄不能刪除")
    removed = [c for c in layout["cells"] if c[field] == op["axis_id"]]
    if any(c["kind"] == "registration" for c in removed):
        fail("這一整排仍有選手，請先移走選手再刪除；報名不會被刪除")
    if axis == "rows" and item["role"] == "body" and sum(r["role"] == "body" for r in layout["rows"]) <= 1:
        fail("請至少保留一排資料格，供後續安排選手")
    custom_title = axis == "columns" and item.get("title") not in (None, "", "文字／備註")
    if (any(c.get("text", "").strip() for c in removed) or custom_title) and not op["confirmed_text"]:
        fail("這個範圍含文字，請核對要刪除與保留的內容後確認")
    new_merges = []
    moves = []
    coordinate = 0 if axis == "rows" else 1
    for merge in layout["merges"]:
        points = region(layout, merge)
        if not any(p[coordinate] == op["axis_id"] for p in points):
            new_merges.append(merge)
            continue
        content = [c for c in layout["cells"] if key(c) in points]
        texts = [c for c in content if c.get("text", "").strip()]
        if len(texts) > 1 or any(c["kind"] == "registration" for c in content):
            fail("受影響的合併區內容有衝突，請先解除合併並整理文字")
        remaining = [p for p in points if p[coordinate] != op["axis_id"]]
        if not remaining:
            continue
        if texts and texts[0][field] == op["axis_id"]:
            target = remaining[0]
            old = cell_at(layout, *target)
            if old and old.get("text", "").strip():
                fail("合併文字無法明確保留，請先解除合併並整理文字")
            moves.append((texts[0], target, old))
        if len(remaining) > 1:
            new_merges.append({**merge,
                "start": {"row_id": remaining[0][0], "column_id": remaining[0][1]},
                "end": {"row_id": remaining[-1][0], "column_id": remaining[-1][1]}})
    header_merges, header_moves = [], []
    if axis == "columns":
        ids = [c["id"] for c in layout["columns"]]
        for merge in layout.get("header_merges",[]):
            members = ids[ids.index(merge["start_column_id"]):ids.index(merge["end_column_id"])+1]
            remaining = [cid for cid in members if cid != op["axis_id"]]
            if merge.get("title") is not None and remaining and merge["start_column_id"] == op["axis_id"]:
                target = next(c for c in layout["columns"] if c["id"] == remaining[0])
                if target.get("title") not in (None,"",merge["title"]): fail("合併表頭文字無法明確保留，請先解除合併並整理標題")
                header_moves.append((target,merge["title"]))
            if len(remaining)>1: header_merges.append({**merge,"start_column_id":remaining[0],"end_column_id":remaining[-1]})
    # Mutation only after the full plan is checked; surviving IDs/coordinates never change.
    if axis == "columns" and "header_merges" in layout:
        layout["header_merges"] = header_merges
        for target,title in header_moves: target["title"] = title
    layout[axis] = [v for v in layout[axis] if v["id"] != op["axis_id"]]
    layout["cells"] = [c for c in layout["cells"] if c[field] != op["axis_id"]]
    for source, target, old in moves:
        if old is not None:
            layout["cells"].remove(old)  # Empty underlying text cannot duplicate the new anchor.
        layout["cells"].append({**source,"row_id":target[0],"column_id":target[1]})
    layout["merges"] = new_merges
    if "cell_shades" in layout:
        layout["cell_shades"] = [c for c in layout["cell_shades"] if c[field] != op["axis_id"]]


def shade_region(layout, start, end):
    """Smallest rectangle containing the selection and all intersecting merges."""
    address(layout, start); address(layout, end)
    rows = {r["id"]: i for i, r in enumerate(layout["rows"])}
    columns = {c["id"]: i for i, c in enumerate(layout["columns"])}
    top, bottom = sorted((rows[start["row_id"]], rows[end["row_id"]]))
    left, right = sorted((columns[start["column_id"]], columns[end["column_id"]]))
    rectangles = []
    for merge in layout["merges"]:
        a, b = sorted((rows[merge["start"]["row_id"]], rows[merge["end"]["row_id"]]))
        x, y = sorted((columns[merge["start"]["column_id"]], columns[merge["end"]["column_id"]]))
        rectangles.append((a, b, x, y))
    while True:
        previous = top, bottom, left, right
        for a, b, x, y in rectangles:
            if a <= bottom and b >= top and x <= right and y >= left:
                top, bottom = min(top, a), max(bottom, b)
                left, right = min(left, x), max(right, y)
        if previous == (top, bottom, left, right):
            break
    return {(r["id"], c["id"]) for r in layout["rows"][top:bottom + 1]
            for c in layout["columns"][left:right + 1]}


def set_cell_shades(layout, op):
    # The synthetic address is only an operation/selection coordinate; persisted
    # rows and player coordinates remain unchanged.
    rows = list(layout["rows"])
    index = next(i for i,r in enumerate(rows) if r["role"] == "body")
    rows.insert(index, {"id":HEADER_ROW_ID,"role":"header"})
    merges = list(layout["merges"]) + [{"start":{"row_id":HEADER_ROW_ID,"column_id":m["start_column_id"]},"end":{"row_id":HEADER_ROW_ID,"column_id":m["end_column_id"]}} for m in layout.get("header_merges",[])]
    points = shade_region({**layout,"rows":rows,"merges":merges}, op["start"], op["end"])
    for column in layout["columns"]:
        if (HEADER_ROW_ID,column["id"]) in points: column["header_shade"] = op["shade"]
    points = {p for p in points if p[0] != HEADER_ROW_ID}
    colors = {key(c): c for c in layout.get("cell_shades", []) if key(c) not in points}
    colors.update({p: {"row_id": p[0], "column_id": p[1], "shade": op["shade"]} for p in points})
    if points: layout["cell_shades"] = sorted(colors.values(), key=key)


def apply(layout, operation):
    op = operation.model_dump()
    action = op["action"]
    if action == "merge_header":
        ids = [c["id"] for c in layout["columns"]]
        if op["start_column_id"] not in ids or op["end_column_id"] not in ids: fail("表頭欄位已不存在")
        left,right = sorted((ids.index(op["start_column_id"]),ids.index(op["end_column_id"])))
        if left == right: fail("請選取至少兩個表頭格")
        for merge in layout.get("header_merges",[]):
            if ids.index(merge["start_column_id"]) <= right and ids.index(merge["end_column_id"]) >= left: fail("表頭合併區重疊，請先解除合併")
        layout.setdefault("header_merges",[]).append({"id":new_id(),"start_column_id":ids[left],"end_column_id":ids[right]})
        return None
    if action in {"unmerge_header","header_text"}:
        merge = next((m for m in layout.get("header_merges",[]) if m["id"] == op["merge_id"]),None)
        if merge is None: fail("表頭合併区已不存在")
        if action == "unmerge_header": layout["header_merges"].remove(merge)
        else:
            # Editing the displayed merged label edits the first underlying title;
            # unmerge keeps that edit and every other original column title.
            merge["title"] = op["text"]
            next(c for c in layout["columns"] if c["id"] == merge["start_column_id"])["title"] = op["text"]
        return None
    if action == "shade_header":
        column = next((c for c in layout["columns"] if c["id"] == op["column_id"]), None)
        if column is None:
            fail("欄位已不存在，請重新讀取")
        column["header_shade"] = op["shade"]
        return None
    if action == "shade_cells":
        set_cell_shades(layout, op)
        return None
    if action == "undo":
        fail("復原必須由交易服務核對伺服器紀錄")
    if action == "redo":
        fail("重做必須由交易服務核對伺服器紀錄")
    if action in {"swap", "insert", "move_empty"}:
        explicit_move(layout, op)
        return None
    if action in {"shade_row", "shade_column"}:
        axis = "rows" if action == "shade_row" else "columns"
        item = next((v for v in layout[axis] if v["id"] == op["axis_id"]), None)
        if item is None:
            fail("指定位置已不存在")
        if axis == "columns" and item["kind"] != "text":
            fail("固定級數欄不可整欄設色，請選擇資料排或文字欄")
        item["shade"] = op["shade"]
        return None
    if action in {"move", "move_bottom"}:
        target = op.get("target")
        if action == "move_bottom":
            # Remove before finding the last occupied body cell; never compact other players.
            source = next(c for c in layout["cells"] if c.get("registration_id") == op["registration_id"])
            layout["cells"].remove(source)
            target = bottom_target(layout, op["level"])
            layout["cells"].append(source)
        return move(layout, op["registration_id"], target)
    if action in {"insert_row", "insert_column", "insert_header"}:
        axis = "columns" if action == "insert_column" else "rows"
        if len(layout[axis]) >= (MAX_ROWS if axis == "rows" else MAX_COLUMNS):
            fail("已達安排大小上限（500列、50欄）")
        items = layout[axis]
        ids = [item["id"] for item in items]
        if op["before_id"] is not None and op["before_id"] not in ids:
            fail("插入位置已不存在")
        index = ids.index(op["before_id"]) if op["before_id"] else len(ids)
        role = items[index]["role"] if axis == "rows" and index < len(items) else "body"
        if action == "insert_header":
            index = next((i for i,r in enumerate(items) if r["role"] == "body"), len(items))
            role = "header"
        items.insert(index, {"id": new_id(), **({"kind":"text", "level":None} if axis == "columns" else {"role":role})})
    elif action in {"delete_row", "delete_column"}:
        delete_axis(layout, op)
    elif action == "column_title":
        column = next((c for c in layout["columns"] if c["id"] == op["column_id"]), None)
        if column is None:
            fail("欄位已不存在，請重新讀取")
        column["title"] = op["text"]
    elif action == "text":
        point = op["target"]
        address(layout, point)
        merge = next((m for m in layout["merges"] if key(point) in region(layout, m)), None)
        if merge:
            points = region(layout, merge)
            sources = [c for c in layout["cells"] if key(c) in points and c.get("text", "").strip()]
            if len(sources) > 1 or any(c["kind"] == "registration" for c in layout["cells"] if key(c) in points):
                fail("合併區內容衝突，原內容完整保留")
            source = sources[0] if sources else merge["start"]
            point = {"row_id": source["row_id"], "column_id": source["column_id"]}
        old = cell_at(layout, **point)
        if old and old["kind"] == "registration":
            fail("選手格不可改為文字")
        if old:
            layout["cells"].remove(old)
        if op["text"]:
            layout["cells"].append({**point, "kind":"text", "text":op["text"]})
    elif action == "merge":
        address(layout, op["start"]); address(layout, op["end"])
        points = region(layout, op)
        if len({r["role"] for r in layout["rows"] if r["id"] in {p[0] for p in points}}) > 1:
            fail("合併不可跨越級數標頭，請分別選取標題列或資料列")
        if len(points) < 2:
            fail("請選取至少兩個儲存格")
        occupied = [c for c in layout["cells"] if key(c) in points]
        if any(c["kind"] == "registration" for c in occupied) or covered(layout).intersection(points):
            fail("只能合併文字或空白格，不能包含選手或既有合併區")
        if sum(bool(c.get("text", "").strip()) for c in occupied) > 1:
            fail("選取範圍有多段文字，請先整理；原內容完整保留")
        # Keep original underlying cells so unmerge restores their exact coordinates.
        layout["merges"].append({"id":new_id(), "start":{"row_id":points[0][0], "column_id":points[0][1]},
            "end":{"row_id":points[-1][0], "column_id":points[-1][1]}})
    elif action == "unmerge":
        found = next((m for m in layout["merges"] if m["id"] == op["merge_id"]), None)
        if not found:
            fail("合併區已不存在")
        layout["merges"].remove(found)
    return None


def validate(layout, rows):
    try: GridLayout.model_validate(layout)
    except ValueError: fail("安排布局資料格式不合法")
    row_ids = [r["id"] for r in layout["rows"]]
    if HEADER_ROW_ID in row_ids: fail("表頭選取識別不得作為資料列")
    columns = {c["id"]:c for c in layout["columns"]}
    if len(row_ids) != len(set(row_ids)) or len(columns) != len(layout["columns"]):
        fail("行列識別重複")
    if sorted(c["level"] for c in columns.values() if c["kind"] == "level") != list(range(1,11)):
        fail("級數欄必須完整保留1到10級")
    if not 1 <= len(row_ids) <= MAX_ROWS or not 10 <= len(columns) <= MAX_COLUMNS or not any(r["role"] == "body" for r in layout["rows"]):
        fail("安排大小或資料排不合法")
    for column in layout["columns"]:
        header_shade = column.get("header_shade")
        if header_shade is not None and (type(header_shade) is not int or not 0 <= header_shade <= 3):
            fail("表頭底色色階不合法")
    shaded = set()
    for cell in layout.get("cell_shades", []):
        address(layout, cell)
        if key(cell) in shaded or type(cell.get("shade")) is not int or not 0 <= cell["shade"] <= 3:
            fail("局部底色座標重複或色階不合法")
        shaded.add(key(cell))
    seen = set(); players = {}; merged = set()
    roles = {r["id"]: r["role"] for r in layout["rows"]}
    merge_ids = set()
    for m in layout["merges"]:
        address(layout, m["start"]); address(layout, m["end"])
        points = set(region(layout,m))
        if m["id"] in merge_ids or len(points) < 2 or len({roles[r] for r, c in points}) != 1:
            fail("合併區識別或範圍不合法")
        merge_ids.add(m["id"])
        if sum(bool(c.get("text", "").strip()) for c in layout["cells"] if key(c) in points) > 1:
            fail("合併區包含多段文字")
        if merged & points: fail("合併區重疊")
        merged |= points
    for cell in layout["cells"]:
        address(layout,cell)
        if key(cell) in seen: fail("儲存格重複")
        seen.add(key(cell))
        if cell["kind"] == "registration":
            rid = cell["registration_id"]
            if rid in players or key(cell) in merged: fail("選手重複或位於合併区")
            col = columns[cell["column_id"]]
            if col["kind"] != "level" or roles[cell["row_id"]] != "body": fail("選手不在級數資料格")
            players[rid] = col["level"]
    if players != {r["registration_id"]:r["competition_level"] for r in rows}:
        fail("布局與正取名單不一致，請重新讀取")


def sync_registration(db, registration):
    """Called in the existing create/cancel/promote/level transaction, never by GET."""
    workspace = db.get(ArrangementWorkspace, registration.competition_id)
    if not workspace:
        return
    layout = json.loads(workspace.layout_json)
    source = next((c for c in layout["cells"] if c.get("registration_id") == registration.id), None)
    if registration.status != "confirmed":
        if source: layout["cells"].remove(source)
    else:
        col = next((c for c in layout["columns"] if source and c["id"] == source["column_id"]), None)
        if not source or col["level"] != registration.competition_level:
            if source: layout["cells"].remove(source)
            move(layout, registration.id, bottom_target(layout, registration.competition_level))
    encoded = encode(layout)
    if encoded != workspace.layout_json:
        workspace.layout_json = encoded
        workspace.revision += 1
