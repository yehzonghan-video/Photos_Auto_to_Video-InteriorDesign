"""PNG 素材與全片圖層；照片／PNG 只保存在目前工作階段。"""
import base64
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import math
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from .models import ANIMATIONS, number
from .animation import overlay_pose

MAX_ASSETS, MAX_OVERLAYS = 24, 32
MAX_ASSET_BYTES = 5 * 1024 * 1024
MAX_ASSET_PIXELS = 8_000_000
ROOT = Path(__file__).resolve().parents[1] / "assets" / "overlays"


@dataclass
class PNGAsset:
    id: str
    name: str
    original: bytes
    width: int
    height: int
    builtin: bool = False

    def metadata(self):
        return dict(id=self.id, name=self.name, width=self.width, height=self.height,
                    builtin=self.builtin, image="data:image/png;base64," + base64.b64encode(self.original).decode("ascii"))


def load_asset(name, data, builtin=False):
    if not data or len(data) > MAX_ASSET_BYTES:
        raise ValueError("PNG 素材需為 1 byte～5 MB。")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != "PNG" or getattr(image, "n_frames", 1) != 1:
                raise ValueError("圖層只接受靜態 PNG，不接受改副檔名的其他格式或 APNG。")
            if image.width * image.height > MAX_ASSET_PIXELS:
                raise ValueError("單張 PNG 不得超過 800 萬畫素。")
            image.load()
            image = ImageOps.exif_transpose(image).convert("RGBA")
            normalized = BytesIO(); image.save(normalized, "PNG")
            original = normalized.getvalue()
            if len(original) > MAX_ASSET_BYTES:
                raise ValueError("PNG 轉成透明圖層後超過 5 MB，請縮小素材。")
            ident = ("builtin-" if builtin else "upload-") + sha256(original).hexdigest()[:32]
            return PNGAsset(ident, str(name)[:180], original, image.width, image.height, builtin)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("無法讀取 PNG，請確認檔案未損壞。") from exc


def discover_assets():
    """以副檔名自動發現開發者素材；不追蹤指向素材目錄以外的連結。"""
    assets, warnings = {}, []
    if ROOT.exists():
        for path in sorted(ROOT.iterdir()):
            if path.suffix.lower() != ".png" or not path.is_file():
                continue
            try:
                path.resolve().relative_to(ROOT.resolve())
                if len(assets) >= MAX_ASSETS:
                    raise ValueError("預設素材最多 24 個。")
                if path.stat().st_size > MAX_ASSET_BYTES:
                    raise ValueError("超過 5 MB。")
                asset = load_asset(path.name, path.read_bytes(), True)
                if asset.id not in assets and sum(len(item.original) for item in assets.values()) + len(asset.original) > 40*1024*1024:
                    raise ValueError("預設素材總容量超過 40 MB。")
                assets[asset.id] = asset
            except (ValueError, OSError) as exc:
                warnings.append(f"{path.name}：{exc}")
    return assets, warnings


def validate_overlays(rows, assets, duration):
    duration = number(duration, 0, 120)
    if not isinstance(rows, list) or len(rows) > MAX_OVERLAYS:
        raise ValueError("全片最多 32 個 PNG 圖層。")
    result, ids = [], set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("PNG 圖層資料格式不正確。")
        ident = raw.get("id")
        if not isinstance(ident, str) or not 1 <= len(ident) <= 64 or ident in ids:
            raise ValueError("PNG 圖層 ID 不正確或重複。")
        ids.add(ident)
        source = raw.get("source")
        if raw.get("type") != "png" or source not in assets:
            raise ValueError("PNG 素材已不存在，請重新上傳。")
        start = number(raw["start"], 0, duration)
        length = number(raw["duration"], 1/30 - 1e-8, 120)
        if start + length > duration + 1e-7:
            raise ValueError("PNG 時間範圍超過影片，請縮短圖層或增加照片長度。")
        enter, exit = number(raw.get("enter", .5), 0, 3), number(raw.get("exit", .5), 0, 3)
        if enter + exit > length + 1e-7:
            raise ValueError("PNG 進場與出場時長總和不能超過持續時間。")
        animation, exit_animation = raw.get("animation", "fade"), raw.get("exit_animation", "fade")
        if animation not in ANIMATIONS or exit_animation not in ANIMATIONS:
            raise ValueError("PNG 動畫不正確。")
        layer = number(raw.get("layer", 20), 0, 1000)
        if layer != int(layer):
            raise ValueError("圖層順序必須為整數。")
        result.append(dict(id=ident, type="png", source=source, name=assets[source].name,
            start=start, duration=length, layer=int(layer),
            x=number(raw["x"], 0, 1), y=number(raw["y"], 0, 1),
            width=number(raw.get("width", .3), .03, 1), scale=number(raw.get("scale", 1), .1, 5),
            rotation=number(raw.get("rotation", 0), -180, 180), opacity=number(raw.get("opacity", 1), 0, 1),
            animation=animation, exit_animation=exit_animation, enter=enter, exit=exit))
    return result


def geometry(item, asset, width=1080, height=1920):
    """與 frontend/overlay-model.js 相同的尺寸、旋轉包圍框與中心限制。"""
    w = max(1, math.floor(width * item["width"] * item["scale"] + .5))
    h = max(1, math.floor(w * asset.height / asset.width + .5))
    angle = math.radians(item["rotation"])
    c, s = abs(math.cos(angle)), abs(math.sin(angle))
    factor = min(1, (width-4) / (w*c+h*s), (height-4) / (w*s+h*c))
    w, h = max(1, math.floor(w*factor)), max(1, math.floor(h*factor))
    bw, bh = w*c+h*s, w*s+h*c
    x = max(bw/2, min(width-bw/2, item["x"]*width))
    y = max(bh/2, min(height-bh/2, item["y"]*height))
    return dict(width=w, height=h, x=x, y=y, box_width=bw, box_height=bh)


def prepare_overlays(overlays, assets):
    prepared = []
    for item in overlays:
        asset = assets[item["source"]]; g = geometry(item, asset)
        with Image.open(BytesIO(asset.original)) as original:
            tile = original.convert("RGBA").resize((g["width"],g["height"]), Image.Resampling.LANCZOS)
        tile = tile.rotate(-item["rotation"], resample=Image.Resampling.BICUBIC, expand=True)
        prepared.append((item, tile, g))
    return prepared


def composite_overlay(frame, prepared, time):
    item, tile, g = prepared
    state = overlay_pose(item, time)
    if state is None:
        return
    current = tile
    if state["scale"] != 1:
        current = tile.resize((max(1,round(tile.width*state["scale"])),max(1,round(tile.height*state["scale"]))),Image.Resampling.BICUBIC)
    alpha = state["alpha"] * item["opacity"]
    if alpha != 1:
        current = current.copy()
        current.putalpha(current.getchannel("A").point(lambda value: round(value*alpha)))
    x, y = g["x"]+state["x"]*1080-current.width/2, g["y"]+state["y"]*1920-current.height/2
    frame.alpha_composite(current,(round(x),round(y)))
