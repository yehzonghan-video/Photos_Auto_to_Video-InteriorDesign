from pathlib import Path
import base64
from io import BytesIO
from PIL import Image
import streamlit.components.v1 as components

from .rendering import data_url, label_tile, template_config

editor = components.declare_component("interior_studio_editor", path=str(Path(__file__).resolve().parents[1] / "frontend"))


def payload(photos):
    rows = []
    for photo in photos:
        row = photo.metadata()
        # 瀏覽器收到原始檔案，不因預覽重新壓縮；Canvas 自動套用 EXIF 方向。
        with Image.open(BytesIO(photo.original)) as image:
            mime = Image.MIME[image.format]
        row["image"] = f"data:{mime};base64," + base64.b64encode(photo.original).decode("ascii")
        row["tiles"] = {}
        for label in photo.labels:
            tile = label_tile(label)
            row["tiles"][label["id"]] = dict(src=data_url(tile), width=tile.width, height=tile.height)
        rows.append(row)
    return dict(photos=rows, template=template_config())
