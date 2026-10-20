"""空間導覽資料及共用幾何；照片／影片片段仍交由同一輸出器合成。"""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import uuid
from PIL import Image,ImageOps,ImageDraw
from .models import number,validate_label
from .comparison import crop_settings

BGM_API_VERSION=10
LAYOUT=json.loads((Path(__file__).resolve().parents[1]/'frontend/tour-layout.json').read_text(encoding='utf-8'))


@dataclass
class FloorPlan:
    id:str
    name:str
    original:bytes
    width:int
    height:int


def load_plan(name,data):
    if Path(name).suffix.lower() not in ('.png','.jpg','.jpeg') or not isinstance(data,bytes) or not 0<len(data)<=8*1024*1024:
        raise ValueError('平面圖請使用PNG／JPG，單檔最多8 MB。')
    try:
        with Image.open(BytesIO(data)) as im:
            if im.format not in ('PNG','JPEG') or im.width*im.height>12_000_000 or getattr(im,'n_frames',1)!=1:
                raise ValueError('平面圖需為靜態PNG／JPG，最多1200萬畫素。')
            corrected=ImageOps.exif_transpose(im);corrected.load();w,h=corrected.size
    except (OSError,Image.DecompressionBombError) as exc:raise ValueError('無法讀取平面圖，原專案保留。') from exc
    return FloorPlan('plan-'+sha256(data).hexdigest()[:32],str(name)[:180],data,w,h)


def new_tour():
    return dict(visible=True,size=.30,opacity=1.,dot_size=12.,rooms=[],clips=[],overlays=[],seen_sources=[],plan_id=None)


def validate_tour(raw,photos,videos,plan):
    raw=new_tour() if raw is None else raw
    if not isinstance(raw,dict) or type(raw.get('visible')) is not bool:raise ValueError('空間導覽設定不正確。')
    result=dict(visible=raw['visible'],size=number(raw.get('size',.3),.15,.5),opacity=number(raw.get('opacity',1),0,1),dot_size=number(raw.get('dot_size',12),6,24),rooms=[],clips=[],overlays=deepcopy(raw.get('overlays',[])),seen_sources=[])
    rooms=raw.get('rooms',[]);clips=raw.get('clips',[])
    if not isinstance(rooms,list) or len(rooms)>30 or not isinstance(clips,list) or len(clips)>40:raise ValueError('最多30個房間、40個導覽片段。')
    room_ids=set();ids=set()
    for r in rooms:
        if not isinstance(r,dict):raise ValueError('房間資料不正確。')
        ident=r.get('id');name=r.get('name')
        if not isinstance(ident,str) or not 1<=len(ident)<=64 or ident in room_ids or not isinstance(name,str) or not name.strip() or len(name)>40:
            raise ValueError('房間ID不可重複，名稱需為1～40字。')
        room_ids.add(ident);result['rooms'].append(dict(id=ident,name=name.strip(),x=number(r.get('x'),0,1),y=number(r.get('y'),0,1),needs_review=bool(r.get('needs_review',False))))
    bank={p.id:p for p in photos};video_ids=set(videos)
    seen=raw.get('seen_sources',[])
    if not isinstance(seen,list) or len(seen)>100 or any(not isinstance(s,str) or len(s)>64 for s in seen):raise ValueError('導覽來源記錄不正確。')
    result['seen_sources']=list(dict.fromkeys(seen))
    result['plan_id']=plan.id if plan else None
    for c in clips:
        if not isinstance(c,dict):raise ValueError('導覽片段格式不正確。')
        ident=c.get('id');kind=c.get('kind');source=c.get('source');room=c.get('room_id')
        if not isinstance(ident,str) or not 1<=len(ident)<=64 or ident in ids or c.get('type')!='tour_clip' or kind not in ('photo','video'):
            raise ValueError('導覽片段格式不正確。')
        if source not in (bank if kind=='photo' else videos) or room is not None and room not in room_ids:raise ValueError('導覽片段的來源或房間已失效。')
        ids.add(ident);duration=number(c.get('duration'),1,20)
        start=number(c.get('in',0),0,60);end=number(c.get('out',duration),0,60)
        if kind=='video' and (end>videos[source].duration+1e-6 or abs(end-start-duration)>1e-6 or abs(start*30-round(start*30))>1e-6):
            raise ValueError('影片起訖需在來源內，長度為1～20秒，並對齊30 FPS影格。')
        labels=c.get('labels',[])
        if not isinstance(labels,list) or len(labels)>12:raise ValueError('每個導覽片段最多12個文字標籤。')
        labels=[validate_label(l,duration) for l in labels]
        if len({l['id'] for l in labels})!=len(labels):raise ValueError('導覽文字ID不可重複。')
        result['clips'].append(dict(id=ident,type='tour_clip',kind=kind,source=source,name=str(c.get('name','導覽片段'))[:180],room_id=room,
            duration=duration,**{'in':start,'out':end},muted=bool(c.get('muted',True)),volume=number(c.get('volume',1),0,1),crop=crop_settings(c.get('crop',{})),labels=labels))
    if sum(c['duration'] for c in result['clips'])>120:raise ValueError('導覽影片最多120秒（含封面）。')
    return result


def box(plan,tour):
    import math
    safe=LAYOUT['safe'];pad=max(LAYOUT['padding'],math.ceil(tour['dot_size']+2));w=math.floor(1080*tour['size']+.5);h=math.floor(w*plan.height/plan.width+.5)
    if h>LAYOUT['max_height']:h=LAYOUT['max_height'];w=math.floor(h*plan.width/plan.height+.5)
    w=max(1,w);h=max(1,h)
    return dict(x=safe['right']-pad-w,y=safe['top']+pad,w=w,h=h,pad=pad)


def plan_layer(plan,tour,room_id=None):
    canvas=Image.new('RGBA',(1080,1920))
    if plan is None or not tour['visible']:return canvas
    b=box(plan,tour);draw=ImageDraw.Draw(canvas);p=b['pad']
    draw.rounded_rectangle((b['x']-p,b['y']-p,b['x']+b['w']+p,b['y']+b['h']+p),radius=12,fill=(255,255,255,215))
    with Image.open(BytesIO(plan.original)) as im:canvas.alpha_composite(ImageOps.exif_transpose(im).convert('RGBA').resize((b['w'],b['h']),Image.Resampling.LANCZOS),(b['x'],b['y']))
    room=next((r for r in tour['rooms'] if r['id']==room_id and not r['needs_review']),None)
    if room:
        x=b['x']+room['x']*b['w'];y=b['y']+room['y']*b['h'];r=tour['dot_size'];ImageDraw.Draw(canvas).ellipse((x-r,y-r,x+r,y+r),fill='#e43f35',outline='white',width=3)
    if tour['opacity']!=1:canvas.putalpha(canvas.getchannel('A').point(lambda a:round(a*tour['opacity'])))
    return canvas
