"""工作階段資料與所有前端輸入的驗證；不包含檔案持久化。"""
from dataclasses import dataclass, field
from io import BytesIO
import math
import re
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PHOTOS = 12
MAX_LABELS = 12
MAX_TOTAL_SECONDS = 120
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_SESSION_BYTES = 80 * 1024 * 1024
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
    if end <= start or enter > end - start:
        raise ValueError("消失時間必須晚於出現時間，進場時長不能超過標籤顯示時間。")
    result = dict(id=str(raw["id"])[:64], text=text,
                **{key: number(raw[key], 0, 1) for key in ("x", "y", "point_x", "point_y")},
                font_size=number(raw["font_size"], 24, 96), color=color(raw["color"]),
                background=color(raw["background"]), opacity=number(raw["opacity"], 0, 1),
                radius=number(raw["radius"], 0, 60), line=bool(raw["line"]),
                animation=animation, start=start, end=end, enter=enter)
    if raw.get("source") == "gemini":
        for key, limit in (("description", 200), ("category", 30), ("ai_item_id", 180), ("confidence_level", 1)):
            value = raw.get(key, "")
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError("AI 標籤附加資料不正確。")
            result[key] = value
        if result["confidence_level"] not in ("高", "中", "低"):
            raise ValueError("AI 信心程度不正確。")
        result.update(source="gemini", needs_review=bool(raw.get("needs_review", True)))
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

    def metadata(self):
        return {key: getattr(self, key) for key in
                ("id", "name", "duration", "zoom", "crop_x", "crop_y", "fit", "labels")}


def load_photo(name, data):
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("照片不能為空，且單張不得超過 15 MB。")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("僅接受 JPG、JPEG、PNG、WEBP 照片。")
            if image.width * image.height > 32_000_000:
                raise ValueError("照片不可超過 3200 萬畫素，請先縮小尺寸。")
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("請上傳靜態照片，不支援動畫圖片。")
            image.load()
            image = ImageOps.exif_transpose(image)
            w, h = image.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("無法讀取此圖片，請確認檔案未損壞。") from exc
    return Photo(uuid.uuid4().hex, str(name)[:180], data, w, h)


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
        if len({label["id"] for label in labels}) != len(labels):
            raise ValueError("標籤識別碼不可重複。")
        changes.append((known[row["id"]], dict(duration=duration, labels=labels, fit=fit,
                        zoom=number(row["zoom"], 1, 3),
                        crop_x=number(row["crop_x"], 0, 1), crop_y=number(row["crop_y"], 0, 1))))
    if sum(c[1]["duration"] for c in changes) > MAX_TOTAL_SECONDS:
        raise ValueError("影片總長度最多 120 秒。")
    for photo, values in changes:
        for key, value in values.items():
            setattr(photo, key, value)
    return [c[0] for c in changes]
