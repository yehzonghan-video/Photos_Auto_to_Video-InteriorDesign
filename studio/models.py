"""工作階段資料與所有前端輸入的驗證；不包含檔案持久化。"""
from dataclasses import dataclass, field
import math
import re
import uuid

from .photo_processing import MAX_INPUT_BYTES, read_upload

MAX_PHOTOS = 12
MAX_LABELS = 12
MAX_TOTAL_SECONDS = 120
MAX_UPLOAD_BYTES = MAX_INPUT_BYTES
MAX_SESSION_BYTES = 80 * 1024 * 1024  # 保留相容名稱；超標時自動最佳化，不直接拒絕。
ANIMATIONS = ("left", "right", "up", "down", "fade", "scale", "none")


def number(value, low, high):
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"數值必須介於 {low} 與 {high} 之間。")
    return result


def color(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError("顏色格式不正確。")
    return value


def new_label(duration=4):
    return dict(id=uuid.uuid4().hex, text="裝修項目", x=.12, y=.28,
                point_x=.58, point_y=.52, font_size=46, color="#ffffff",
                background="#222822", opacity=.88, radius=18, line=True,
                animation="left", start=0., enter=.6, end=float(duration))


def validate_label(raw, duration):
    text = str(raw.get("text", "")).strip()
    if not text or len(text) > 80:
        raise ValueError("標籤文字需為 1～80 個字。")
    animation = raw.get("animation", "left")
    if animation not in ANIMATIONS:
        raise ValueError("不支援此動畫。")
    start = number(raw.get("start", 0), 0, duration)
    end = number(raw.get("end", duration), 0, duration)
    enter = number(raw.get("enter", .6), 0, 3)
    empty_before = raw.get("comparison_side") == "before" and bool(raw.get("auto_timing")) and start == end == 0 and enter == 0
    if (end <= start and not empty_before) or enter > end - start:
        raise ValueError("消失時間必須晚於出現時間，進場時長不能超過標籤顯示時間。")
    result = dict(id=str(raw["id"])[:64], text=text,
                **{key: number(raw[key], 0, 1) for key in ("x", "y", "point_x", "point_y")},
                font_size=number(raw["font_size"], 24, 96), color=color(raw["color"]),
                background=color(raw["background"]), opacity=number(raw["opacity"], 0, 1),
                radius=number(raw["radius"], 0, 60), line=bool(raw["line"]),
                animation=animation, start=start, end=end, enter=enter,
                layer=int(number(raw.get("layer", 10), 0, 1000)))
    if raw.get("source") == "gemini":
        for key, limit in (("description", 200), ("category", 30), ("ai_item_id", 180), ("confidence_level", 1)):
            value = raw.get(key, "")
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError("AI 標籤附加資料不正確。")
            result[key] = value
        if result["confidence_level"] not in ("高", "中", "低"):
            raise ValueError("AI 信心程度不正確。")
        result.update(source="gemini", needs_review=bool(raw.get("needs_review", True)))
    if raw.get("comparison_side") in ("before", "after"):
        result.update(comparison_side=raw["comparison_side"], auto_timing=bool(raw.get("auto_timing",False)))
        if raw.get("comparison_title_version") in (1,2):
            result["comparison_title_version"] = int(raw["comparison_title_version"])
        if raw.get("safe_area_version") == 1:
            result["safe_area_version"] = 1
        result["exit"] = number(raw.get("exit",0),0,min(3,end-start))
    if isinstance(raw.get("origin_label_id"),str):
        result["origin_label_id"]=raw["origin_label_id"][:64]
    return result


@dataclass
class Photo:
    id: str
    name: str
    original: bytes
    width: int
    height: int
    duration: float = 4.
    zoom: float = 1.
    crop_x: float = .5
    crop_y: float = .5
    fit: str = "contain"
    labels: list = field(default_factory=list)
    optimization_note: str = ""
    role: str = "general"

    def metadata(self):
        return {key: getattr(self, key) for key in
                ("id", "name", "duration", "zoom", "crop_x", "crop_y", "fit", "labels", "role")}


def load_photo(name, data):
    working, w, h, note = read_upload(data)
    return Photo(uuid.uuid4().hex, str(name)[:180], working, w, h, optimization_note=note)


def update_project(photos, rows):
    """先完整驗證，再一次套用，避免失敗造成部分更新。"""
    if not isinstance(rows, list) or len(rows) != len(photos):
        raise ValueError("照片清單已變更，請重新操作。")
    known = {p.id: p for p in photos}
    if {r.get("id") for r in rows} != set(known) or len({r.get("id") for r in rows}) != len(rows):
        raise ValueError("照片識別碼不正確。")
    changes = []
    for row in rows:
        duration = number(row["duration"], 1, 20)
        fit = row.get("fit", "contain")
        if fit not in ("contain", "cover"):
            raise ValueError("不支援此照片顯示方式。")
        if not isinstance(row["labels"], list) or len(row["labels"]) > MAX_LABELS:
            raise ValueError("單張最多 12 個標籤。")
        labels = [validate_label(label, duration) for label in row["labels"]]
        role=row.get("role",known[row["id"]].role)
        if role not in ("general","before","after"):raise ValueError("照片分類不正確。")
        if len({label["id"] for label in labels}) != len(labels):
            raise ValueError("標籤識別碼不可重複。")
        changes.append((known[row["id"]], dict(duration=duration, labels=labels, fit=fit, role=role,
                        zoom=number(row["zoom"], 1, 3),
                        crop_x=number(row["crop_x"], 0, 1), crop_y=number(row["crop_y"], 0, 1))))
    if sum(c[1]["duration"] for c in changes) > MAX_TOTAL_SECONDS:
        raise ValueError("影片總長度最多 120 秒。")
    for photo, values in changes:
        for key, value in values.items():
            setattr(photo, key, value)
    return [c[0] for c in changes]
