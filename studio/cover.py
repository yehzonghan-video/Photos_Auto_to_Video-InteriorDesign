"""固定0.3秒封面：共用照片來源與影片管線，局部字色使用Unicode字元索引。"""
from functools import lru_cache
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont, ImageOps
from .models import number, color
from .rendering import font_path

LAYOUT = json.loads((Path(__file__).resolve().parents[1]/'frontend'/'cover-layout.json').read_text(encoding='utf-8'))
TEMPLATE = Path(__file__).resolve().parents[1]/'assets'/'covers'/'opening-template.png'
DURATION = LAYOUT['duration']
BGM_API_VERSION = 7


def new_cover():
    from .body import new_body
    return dict(enabled=True, title='室內設計案例', photo_id='', color='#ffffff', font_size=120, highlights=[], body=new_body())


def validate_cover(raw, photos):
    if raw is None:
        raw = {**new_cover(), 'enabled':False}
        raw['body'].update(enabled=False, logo_enabled=False)
    if not isinstance(raw,dict) or not isinstance(raw.get('enabled'),bool):
        raise ValueError('片頭設定格式不正確。')
    style=validate_title(raw,raw['enabled'],'封面')
    source=raw.get('photo_id','')
    if not isinstance(source,str):raise ValueError('封面照片格式不正確。')
    if source and source not in {p.id for p in photos}:
        if raw['enabled'] and photos:raise ValueError('封面照片已刪除，請重新選擇。')
        source=''
    if not source:
        source=next((p.id for p in photos if p.role=='after'),photos[0].id if photos else '')
    result=dict(enabled=raw['enabled'],photo_id=source,**style)
    from .body import validate_body
    result['body']=validate_body(raw.get('body'),result)
    return result


def validate_title(raw, required, context, max_font_size=160):
    title=raw.get('title','')
    if not isinstance(title,str) or (required and not title.strip()) or len(title)>80 or title.count('\n')>5:
        raise ValueError(f'{context}標題需為1～80字，最多6行。')
    ranges=raw.get('highlights',[])
    if not isinstance(ranges,list) or len(ranges)>80:raise ValueError(f'{context}局部字色過多。')
    highlights=[]
    for r in ranges:
        if not isinstance(r,dict) or type(r.get('start')) is not int or type(r.get('end')) is not int or not 0<=r['start']<r['end']<=len(title):
            raise ValueError('請重新選取要改色的標題文字。')
        highlights.append(dict(start=r['start'],end=r['end'],color=color(r.get('color'))))
    return dict(title=title,color=color(raw.get('color','#ffffff')),
                font_size=int(number(raw.get('font_size',120),36,max_font_size)),highlights=highlights)


def title_colors(cover):
    result=[cover['color']]*len(cover['title'])
    for r in cover['highlights']:
        result[r['start']:r['end']]=[r['color']]*(r['end']-r['start'])
    return result


def _lines(text,font,maximum):
    lines=[];line=[]
    for index,char in enumerate(text):
        if char=='\n':lines.append(line);line=[];continue
        if line and font.getlength(''.join(c for c,_ in line)+char)>maximum:
            lines.append(line);line=[]
        line.append((char,index))
    lines.append(line)
    return lines


def title_tile(cover, box=None):
    box=LAYOUT['title'] if box is None else box
    w,h=box['width'],box['height'];size=cover['font_size']
    while True:
        font=ImageFont.truetype(font_path(),size);lines=_lines(cover['title'],font,w-24);step=int(size*1.35)
        if len(lines)*step<=h-24:break
        size-=1
        if size<12:raise ValueError('標題無法放入安全區，請減少文字或分行。')
    tile=Image.new('RGBA',(w,h));draw=ImageDraw.Draw(tile);colors=title_colors(cover)
    top=(h-len(lines)*step)/2;ascent=font.getmetrics()[0]
    for row,line in enumerate(lines):
        text=''.join(c for c,_ in line);left=(w-font.getlength(text))/2;prefix=''
        for char,index in line:
            draw.text((left+font.getlength(prefix),top+row*step+ascent),char,font=font,
                      fill=colors[index],stroke_width=2,stroke_fill='#000000',anchor='ls')
            prefix+=char
    return tile


@lru_cache(maxsize=1)
def template_bytes():
    return TEMPLATE.read_bytes()


def cover_frame(cover,photos):
    canvas=Image.new('RGBA',(1080,1920),'black')
    frame=Image.new('RGBA',(LAYOUT['width'],LAYOUT['height']),'black')
    # 先完成整張3:4構圖，再整體置中；LOGO、文字與照片共用相同偏移。
    with Image.open(TEMPLATE) as image:
        template=ImageOps.contain(image.convert('RGBA'),(LAYOUT['width'],LAYOUT['height']))
        frame.alpha_composite(template,((LAYOUT['width']-template.width)//2,0))
    photo=next((p for p in photos if p.id==cover['photo_id']),None)
    if photo is None:raise ValueError('請選擇封面照片。')
    box=LAYOUT['photo']
    from io import BytesIO
    with Image.open(BytesIO(photo.original)) as image:
        working=ImageOps.exif_transpose(image).convert('RGBA')
        fitted=ImageOps.contain(working,(box['width'],box['height']),Image.Resampling.LANCZOS)
        frame.alpha_composite(fitted,(box['x']+(box['width']-fitted.width)//2,box['y']+(box['height']-fitted.height)//2))
    frame.alpha_composite(title_tile(cover),(LAYOUT['title']['x'],LAYOUT['title']['y']))
    canvas.alpha_composite(frame,(LAYOUT['origin']['x'],LAYOUT['origin']['y']))
    return canvas
