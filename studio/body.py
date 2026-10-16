"""正文固定標題／LOGO；標題可連動封面，沿用同一套局部字色與描邊。"""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import json
from PIL import Image, ImageOps
from .cover import validate_title, title_tile
from .models import number

BGM_API_VERSION = 5
LAYOUT = json.loads((Path(__file__).resolve().parents[1]/'frontend'/'body-layout.json').read_text(encoding='utf-8'))
TEMPLATE = Path(__file__).resolve().parents[1]/'assets'/'covers'/'body-template.png'


def new_body():
    return dict(enabled=True, logo_enabled=True, follow_cover=True, title='室內設計案例',
                color='#ffffff', highlights=[], **LAYOUT['defaults'], auto_timing=True, start=0., end=None, version=4)


def upgrade_body(body):
    """更新舊預設一次；保留人工設定的其他字級、位置與時間。"""
    if body.get('version', 0) < 4:
        if body.get('font_size') == 120 or (body.get('version',0)<2 and body.get('font_size') == 88):
            body['font_size']=LAYOUT['defaults']['font_size']
        if body.get('x',.5) == .5 and body.get('y') in ((350+180)/1920, (410+180)/1920):
            body['y']=LAYOUT['defaults']['y']
        defaults=new_body()
        for key in ('font_size','auto_timing','start','end','x','y'):body.setdefault(key,defaults[key])
        body['version']=4
    return body


def title_box(body):
    """位置以標題區中心的相對比例儲存；字型光柵與位置分開快取。"""
    box=LAYOUT['title']
    return dict(x=round(body.get('x',.5)*1080-box['width']/2),
                y=round(body.get('y',new_body()['y'])*1920-box['height']/2),
                width=box['width'],height=box['height'])


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
    raw=upgrade_body(dict(raw))
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
    for key in ('x','y'):
        if type(raw.get(key,new_body()[key])) not in (int,float):raise ValueError('正文標題位置必須為數值。')
        body[key]=number(raw.get(key,new_body()[key]),0,1)
    body.update(auto_timing=auto,start=start,end=end,version=4)
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
        box=title_box(body)
        layer.alpha_composite(title_tile(effective_title(cover), LAYOUT['title']),
                              (box['x'],box['y']))
    return layer
