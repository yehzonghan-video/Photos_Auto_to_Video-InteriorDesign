from pathlib import Path
import base64
import hashlib
from io import BytesIO
from PIL import Image
import streamlit.components.v1 as components

from .rendering import data_url, label_tile, template_config

editor = components.declare_component("interior_studio_editor", path=str(Path(__file__).resolve().parents[1] / "frontend"))


def payload(photos, cache=None):
    cache = {} if cache is None else cache
    live_ids = {photo.id for photo in photos}
    for ident in list(cache):
        if ident not in live_ids:
            del cache[ident]
    rows = []
    for photo in photos:
        row = photo.metadata()
        assets = cache.setdefault(photo.id, {"tiles": {}})
        # 瀏覽器收到原始檔案，不因預覽重新壓縮；Canvas 自動套用 EXIF 方向。
        digest = hashlib.sha256(photo.original).hexdigest()
        if assets.get("digest") != digest:
            with Image.open(BytesIO(photo.original)) as image:
                mime = Image.MIME[image.format]
            assets["image"] = f"data:{mime};base64," + base64.b64encode(photo.original).decode("ascii")
            assets["digest"] = digest
        row["image"] = assets["image"]
        row["tiles"] = {}
        for label in photo.labels:
            style = {key: label[key] for key in ("text", "font_size", "color", "background", "opacity", "radius")}
            previous = assets["tiles"].get(label["id"])
            if previous is None or previous["style"] != style:
                tile = label_tile(label)
                previous = dict(src=data_url(tile), width=tile.width, height=tile.height, style=style)
                assets["tiles"][label["id"]] = previous
            row["tiles"][label["id"]] = previous
        assets["tiles"] = dict(row["tiles"])
        rows.append(row)
    return dict(photos=rows, template=template_config())
