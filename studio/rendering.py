"""照片與文字先產生共用素材，瀏覽器及 FFmpeg 使用相同點陣文字。"""
import base64
from io import BytesIO
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .animation import pose

ROOT = Path(__file__).resolve().parents[1]
BGM_API_VERSION = 10
W, H = 1080, 1920


def template_config(name="items"):
    # 只允許程式註冊的模板，避免任意路徑讀取。
    if name not in ("items", "compare", "tour"):
        raise ValueError("此模板尚未提供。")
    return json.loads((ROOT / "templates" / f"{name}.json").read_text(encoding="utf-8"))


def font_path():
    candidates = [os.environ.get("STUDIO_FONT_PATH", ""),
                  "C:/Windows/Fonts/msjh.ttc", "C:/Windows/Fonts/msjhbd.ttc",
                  "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError("找不到中文字型。Windows 使用微軟正黑體；Cloud 請安裝 fonts-noto-cjk，或設定 STUDIO_FONT_PATH。")


def photo_image(photo):
    with Image.open(BytesIO(photo.original)) as source:
        source = ImageOps.exif_transpose(source).convert("RGBA")
        bg = Image.new("RGBA", source.size, (0, 0, 0, 255))
        bg.alpha_composite(source)
        return bg.convert("RGB")


def crop_photo(photo, width=W, height=H):
    source = photo_image(photo)
    return fit_image(source,photo,width,height)


def fit_image(source,photo,width=W,height=H):
    if getattr(photo, "fit", "contain") == "contain":
        # 完整照片等比例置中；留黑邊時不套用會切掉照片的縮放與裁切。
        factor = min(width / source.width, height / source.height)
        size = (max(1, int(source.width * factor + .5)),
                max(1, int(source.height * factor + .5)))
        image = source.resize(size, Image.Resampling.LANCZOS)
        frame = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        frame.paste(image, ((width - size[0]) // 2, (height - size[1]) // 2))
        return frame
    # cover 裁切：維持長寬比，先在原始像素選取視窗，再縮放輸出。
    factor = max(width / source.width, height / source.height) * photo.zoom
    cw, ch = width / factor, height / factor
    left, top = (source.width - cw) * photo.crop_x, (source.height - ch) * photo.crop_y
    return source.transform((width, height), Image.Transform.EXTENT,
                            (left, top, left + cw, top + ch), Image.Resampling.BICUBIC).convert("RGBA")


def label_tile(label):
    font = ImageFont.truetype(font_path(), int(label["font_size"]))
    lines, line = [], ""
    # 逐字換行同時適用中文與英文；限制標籤寬度避免超出直式畫面。
    for char in label["text"]:
        if char == "\n" or (line and font.getlength(line + char) > 800):
            lines.append(line)
            line = "" if char == "\n" else char
        else:
            line += char
    lines.append(line)
    padding, step = 24, int(label["font_size"] * 1.35)
    width = min(848, int(max(font.getlength(line) for line in lines)) + padding * 2)
    height = len(lines) * step + padding * 2
    tile = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(tile)
    rgb = tuple(int(label["background"][i:i+2], 16) for i in (1, 3, 5))
    draw.rounded_rectangle((0, 0, width-1, height-1), int(label["radius"]),
                           fill=(*rgb, round(label["opacity"] * 255)))
    for i, line in enumerate(lines):
        draw.text((padding, padding + i * step), line, font=font, fill=label["color"], anchor="lt",
                  stroke_width=2, stroke_fill="#000000")
    return tile


def data_url(image, fmt="PNG"):
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def tile_position(label, tile):
    return min(label["x"] * W, W - tile.width), min(label["y"] * H, H - tile.height)


def render_frame(base, labels, tiles, time, overlays=None, global_time=None):
    frame = base.copy()
    from .overlays import composite_overlay
    layers = [(label.get("layer",10),index,"label",(label,tile)) for index,(label,tile) in enumerate(zip(labels,tiles))]
    layers += [(item[0]["layer"],len(labels)+index,"png",item) for index,item in enumerate(overlays or [])]
    for _, _, kind, material in sorted(layers, key=lambda entry:(entry[0],entry[1])):
        if kind == "png":
            composite_overlay(frame, material, time if global_time is None else global_time)
            continue
        label, tile = material
        state = pose(label, time)
        if state is None:
            continue
        x, y = tile_position(label, tile)
        x += state["x"] * W
        y += state["y"] * H
        scale, alpha = state["scale"], state["alpha"]
        if label["line"]:
            overlay = Image.new("RGBA", frame.size)
            draw = ImageDraw.Draw(overlay)
            px, py = label["point_x"] * W, label["point_y"] * H
            draw.line((x + tile.width / 2, y + tile.height / 2, px, py),
                      fill=(255, 255, 255, round(210 * alpha)), width=4)
            draw.ellipse((px-10, py-10, px+10, py+10), fill=(255, 255, 255, round(255 * alpha)))
            frame.alpha_composite(overlay)
        current = tile
        if scale != 1:
            current = tile.resize((max(1, round(tile.width * scale)), max(1, round(tile.height * scale))), Image.Resampling.BICUBIC)
            x += (tile.width - current.width) / 2
            y += (tile.height - current.height) / 2
        if alpha != 1:
            current = current.copy()
            current.putalpha(current.getchannel("A").point(lambda a: round(a * alpha)))
        frame.alpha_composite(current, (round(x), round(y)))
    return frame.convert("RGB")
