"""正文固定標題／LOGO；標題可連動封面，沿用同一套局部字色與描邊。"""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import json
from PIL import Image, ImageOps
from .cover import validate_title, title_tile
from .models import number

BGM_API_VERSION = 3
LAYOUT = json.loads((Path(__file__).resolve().parents[1]/'frontend'/'body-layout.json').read_text(encoding='utf-8'))
TEMPLATE = Path(__file__).resolve().parents[1]/'assets'/'covers'/'body-template.png'


def new_body():
    return dict(enabled=True, logo_enabled=True, follow_cover=True, title='室內設計案例',
                color='#ffffff', highlights=[], font_size=120, auto_timing=True, start=0., end=None, version=2)


def upgrade_body(body):
    """舊預設字級放大一次；保留已手動選擇的其他字級／樣式。"""
    if body.get('version') != 2:
        if body.get('font_size') == 88:body['font_size']=120
        for key in ('auto_timing','start','end'):body.setdefault(key,new_body()[key])
        body['version']=2
    return body


def title_span(body, prefix, length):
    """全片秒數，排除封面；縮短影片時限制於剩餘正文範圍。"""
    if length-prefix < 1/30-1e-8:return prefix,prefix
    if body.get('auto_timing',True):return prefix,length
    start=max(prefix,min(body['start'],length-1/30))
    end=max(start+1/30,min(body['end'],length))
    return start,end


def title_visible(body, time, prefix, length):
    start,end=title_span(body,prefix,length)
    return body['enabled'] and time+1e-8>=start and time<end-1e-8


def effective_title(cover):
    body = cover['body']
    source = cover if body['follow_cover'] else body
    return {key: source[key] for key in ('title', 'color', 'highlights')} | {'font_size': body['font_size']}


def validate_body(raw, cover):
    raw = new_body() if raw is None else raw
    if not isinstance(raw, dict) or any(type(raw.get(key)) is not bool for key in ('enabled', 'logo_enabled', 'follow_cover')):
        raise ValueError('正文標題與LOGO設定格式不正確。')
    body = {key: raw[key] for key in ('enabled', 'logo_enabled', 'follow_cover')}
    body.update(validate_title(raw, body['enabled'] and not body['follow_cover'], '正文',240))
    if body['enabled'] and body['follow_cover']:
        validate_title({**cover, 'font_size': body['font_size']}, True, '正文',240)
    auto=raw.get('auto_timing',True)
    if type(auto) is not bool:raise ValueError('正文標題時間設定格式不正確。')
    if type(raw.get('start',0)) not in (int,float) or (raw.get('end') is not None and type(raw.get('end')) not in (int,float)):
        raise ValueError('正文標題時間必須為數值。')
    start=number(raw.get('start',0),0,120)
    end=raw.get('end')
    if end is not None:end=number(end,0,120)
    if not auto and (end is None or end-start < 1/30-1e-8):raise ValueError('正文標題至少需顯示一影格，請確認開始與結束時間。')
    body.update(auto_timing=auto,start=start,end=end,version=2)
    return body


@lru_cache(maxsize=1)
def template_bytes():
    # 預覽直接使用輸出尺寸，避免瀏覽器解碼原稿1600萬畫素。
    canvas=Image.new('RGBA',(1080,1920))
    with Image.open(TEMPLATE) as image:
        fitted=ImageOps.contain(image.convert('RGBA'),canvas.size,Image.Resampling.LANCZOS)
        canvas.alpha_composite(fitted,((1080-fitted.width)//2,0))
    buffer=BytesIO();canvas.save(buffer,format='PNG');return buffer.getvalue()


def body_layer(cover, *, include_title=True, include_logo=True):
    """只製作透明前景，不改变照片尺寸或既有標籤／PNG排序。"""
    body = cover['body']
    layer = Image.new('RGBA', (1080, 1920))
    if body['logo_enabled'] and include_logo:
        with Image.open(BytesIO(template_bytes())) as image:
            layer.alpha_composite(image.convert('RGBA'))
    if body['enabled'] and include_title:
        layer.alpha_composite(title_tile(effective_title(cover), LAYOUT['title']),
                              (LAYOUT['title']['x'], LAYOUT['title']['y']))
    return layer
