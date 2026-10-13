"""照片以原檔優先；負荷超標時縮小工作副本，預覽另用較小圖片。"""
from dataclasses import replace
from io import BytesIO
import math
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_INPUT_BYTES = 200 * 1024 * 1024
WORKING_PIXELS = 32_000_000
WORKING_BYTES = 15 * 1024 * 1024
SESSION_PIXELS = 60_000_000
SESSION_BYTES = 80 * 1024 * 1024
PREVIEW_PIXELS = 4_000_000
PREVIEW_EDGE = 2560


def _size(width, height, pixels, edge=None):
    factor = min(1, math.sqrt(pixels / (width * height)))
    if edge:
        factor = min(factor, edge / max(width, height))
    return max(1, math.floor(width * factor)), max(1, math.floor(height * factor))


def _decode(data, pixels, edge=None):
    # 不關閉 Pillow 的極端解壓縮圖片保護；一般大照片改為縮圖而非拒絕。
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Image.DecompressionBombWarning)
        with Image.open(BytesIO(data)) as image:
            if image.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("僅接受 JPG、JPEG、PNG、WEBP 照片。")
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("請上傳靜態照片，不支援動畫圖片。")
            original_size = image.size
            orientation = image.getexif().get(274, 1)
            target = _size(*image.size, pixels, edge)
            if target != image.size:
                # JPEG 可在解碼時降採樣，減少大檔完整解碼的記憶體峰值。
                image.draft("RGB", target)
                image.thumbnail(target, Image.Resampling.LANCZOS)
            image.load()
            result = ImageOps.exif_transpose(image)
            if orientation in (5, 6, 7, 8):
                original_size = original_size[::-1]
            return result, original_size


def _jpeg(image, budget):
    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", image.size, "black")
        background.paste(rgba, mask=rgba.getchannel("A"))
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")
    for _ in range(12):
        for quality in (94, 88, 80):
            out = BytesIO()
            image.save(out, "JPEG", quality=quality, subsampling=0)
            if out.tell() <= budget:
                return out.getvalue(), image.size
        image.thumbnail(_size(*image.size, image.width * image.height * .64), Image.Resampling.LANCZOS)
    raise ValueError("此圖片無法完成自動縮小，請改用另一張照片。")


def read_upload(data):
    if not data:
        raise ValueError("照片不能為空。")
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("單檔傳輸上限為 200 MB，請使用較小副本。")
    try:
        image, original_size = _decode(data, WORKING_PIXELS)
        try:
            if image.size == original_size and len(data) <= WORKING_BYTES:
                return data, image.width, image.height, ""
            packed, size = _jpeg(image, WORKING_BYTES)
            note = f"原圖 {original_size[0]}×{original_size[1]}，已自動調整工作副本為 {size[0]}×{size[1]}。"
            return packed, *size, note
        finally:
            image.close()
    except MemoryError:
        # JPEG 先嘗試更小的解碼副本；PNG／WEBP 若仍無法解碼會清楚報錯。
        try:
            image, original_size = _decode(data, 2_000_000, 1920)
            try:
                packed, size = _jpeg(image, WORKING_BYTES)
                return packed, *size, f"記憶體不足，已自動使用 {size[0]}×{size[1]} 的較小工作副本。"
            finally:
                image.close()
        except (MemoryError, OSError, ValueError) as exc:
            raise ValueError("記憶體不足，無法解碼此照片；請使用較小副本再試。") from exc
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("無法安全讀取此圖片，可能損壞或解碼尺寸極端過大。") from exc


def fit_session(photos):
    """容量超標時回傳較小的新 Photo，保留 ID／構圖／標籤，不修改原交易。"""
    result = list(photos)
    for _ in range(8):
        pixels = sum(p.width * p.height for p in result)
        size = sum(len(p.original) for p in result)
        if pixels <= SESSION_PIXELS and size <= SESSION_BYTES:
            return result
        ratio = min(1, SESSION_PIXELS / max(1, pixels), SESSION_BYTES / max(1, size)) * .96
        updated = []
        for photo in result:
            image, _ = _decode(photo.original, max(1, math.floor(photo.width * photo.height * ratio)))
            try:
                packed, dimensions = _jpeg(image, WORKING_BYTES)
            finally:
                image.close()
            prior = getattr(photo, "optimization_note", "")
            note = f"為容納這批照片，已自動調整為 {dimensions[0]}×{dimensions[1]}。"
            updated.append(replace(photo, original=packed, width=dimensions[0], height=dimensions[1],
                                   optimization_note=(prior + " " + note).strip()))
        result = updated
    raise ValueError("目前無法完成照片自動最佳化，請稍後再試。")


def preview_data(photo):
    image, _ = _decode(photo.original, PREVIEW_PIXELS, PREVIEW_EDGE)
    try:
        data, _ = _jpeg(image, 2 * 1024 * 1024)
        return data
    finally:
        image.close()
