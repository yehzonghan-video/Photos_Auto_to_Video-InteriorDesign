"""正文固定標題／LOGO；標題可連動封面，沿用同一套局部字色與描邊。"""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import json
from PIL import Image, ImageOps
from .cover import validate_title, title_tile

BGM_API_VERSION = 2
LAYOUT = json.loads((Path(__file__).resolve().parents[1]/'frontend'/'body-layout.json').read_text(encoding='utf-8'))
TEMPLATE = Path(__file__).resolve().parents[1]/'assets'/'covers'/'body-template.png'


def new_body():
    return dict(enabled=True, logo_enabled=True, follow_cover=True, title='室內設計案例',
                color='#ffffff', highlights=[], font_size=88)


def effective_title(cover):
    body = cover['body']
    source = cover if body['follow_cover'] else body
    return {key: source[key] for key in ('title', 'color', 'highlights')} | {'font_size': body['font_size']}


def validate_body(raw, cover):
    raw = new_body() if raw is None else raw
    if not isinstance(raw, dict) or any(type(raw.get(key)) is not bool for key in ('enabled', 'logo_enabled', 'follow_cover')):
        raise ValueError('正文標題與LOGO設定格式不正確。')
    body = {key: raw[key] for key in ('enabled', 'logo_enabled', 'follow_cover')}
    body.update(validate_title(raw, body['enabled'] and not body['follow_cover'], '正文'))
    if body['enabled'] and body['follow_cover']:
        validate_title({**cover, 'font_size': body['font_size']}, True, '正文')
    return body


@lru_cache(maxsize=1)
def template_bytes():
    # 預覽直接使用輸出尺寸，避免瀏覽器解碼原稿1600萬畫素。
    canvas=Image.new('RGBA',(1080,1920))
    with Image.open(TEMPLATE) as image:
        fitted=ImageOps.contain(image.convert('RGBA'),canvas.size,Image.Resampling.LANCZOS)
        canvas.alpha_composite(fitted,((1080-fitted.width)//2,0))
    buffer=BytesIO();canvas.save(buffer,format='PNG');return buffer.getvalue()


def body_layer(cover):
    """只製作透明前景，不改变照片尺寸或既有標籤／PNG排序。"""
    body = cover['body']
    layer = Image.new('RGBA', (1080, 1920))
    if body['logo_enabled']:
        with Image.open(BytesIO(template_bytes())) as image:
            layer.alpha_composite(image.convert('RGBA'))
    if body['enabled']:
        layer.alpha_composite(title_tile(effective_title(cover), LAYOUT['title']),
                              (LAYOUT['title']['x'], LAYOUT['title']['y']))
    return layer
