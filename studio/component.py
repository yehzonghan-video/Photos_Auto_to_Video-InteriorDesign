from pathlib import Path
import base64
import hashlib
import streamlit.components.v1 as components

from .rendering import data_url, label_tile, template_config
from .photo_processing import preview_data

editor = components.declare_component("interior_studio_editor", path=str(Path(__file__).resolve().parents[1] / "frontend"))


def payload(photos, cache=None, assets=None, overlays=None):
    cache = {} if cache is None else cache
    live_ids = {photo.id for photo in photos}
    for ident in list(cache):
        if ident not in live_ids:
            del cache[ident]
    rows = []
    for photo in photos:
        row = photo.metadata()
        photo_assets = cache.setdefault(photo.id, {"tiles": {}})
        # 編輯器只收較小預覽；原始／最佳化工作副本保留給 AI 與 FFmpeg。
        digest = hashlib.sha256(photo.original).hexdigest()
        if photo_assets.get("digest") != digest:
            photo_assets["image"] = "data:image/jpeg;base64," + base64.b64encode(preview_data(photo)).decode("ascii")
            photo_assets["digest"] = digest
        row["image"] = photo_assets["image"]
        row["content_hash"] = digest
        row["tiles"] = {}
        for label in photo.labels:
            style = {key: label[key] for key in ("text", "font_size", "color", "background", "opacity", "radius")}
            previous = photo_assets["tiles"].get(label["id"])
            if previous is None or previous["style"] != style:
                tile = label_tile(label)
                previous = dict(src=data_url(tile), width=tile.width, height=tile.height, style=style)
                photo_assets["tiles"][label["id"]] = previous
            row["tiles"][label["id"]] = previous
        photo_assets["tiles"] = dict(row["tiles"])
        rows.append(row)
    return dict(photos=rows, template=template_config(), schema_version=3,
                assets=[asset.metadata() for asset in (assets or {}).values()], overlays=overlays or [])
