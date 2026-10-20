"""內容版本與成果來源；雜湊不包含時間、登入、API或介面選取狀態。"""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import json
import math
import struct

BGM_API_VERSION = 10
ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT/'frontend'/'content-schema.json').read_text(encoding='utf-8'))


def canonical(value):
    """跨Python/JS規格：數字採IEEE754，1與1.0／負零相同，不受JSON格式影響。"""
    if value is None:return 'null'
    if isinstance(value,bool):return 'true' if value else 'false'
    if isinstance(value,(int,float)):
        number=float(value)
        return 'N'+(struct.pack('>d',number if number else 0.).hex() if math.isfinite(number) else 'invalid')
    if isinstance(value,str):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
    if isinstance(value,list):return '['+','.join(canonical(v) for v in value)+']'
    if isinstance(value,dict):return '{'+','.join(canonical(k)+':'+canonical(value[k]) for k in sorted(value))+'}'
    raise TypeError('內容版本含不支援的資料格式。')


def digest(value):
    return 'cv1-'+sha256(canonical(value).encode('utf-8')).hexdigest()


def normalize(raw, name):
    raw=raw or {}
    result={k:raw.get(k,v) for k,v in SCHEMA[name].items()}
    for key in ('color','background'):
        if isinstance(result.get(key),str):result[key]=result[key].lower()
    return result


def labels(rows):
    result=[]
    for raw in rows or []:
        label=normalize(raw,'label')
        if isinstance(label['text'],str):label['text']=label['text'].strip()
        if raw.get('source')=='gemini':label.update(normalize(raw,'gemini'))
        if raw.get('comparison_side') in ('before','after'):label.update(normalize(raw,'comparison_label'))
        if isinstance(raw.get('origin_label_id'),str):label['origin_label_id']=raw['origin_label_id']
        result.append(label)
    return result


def document(data, context):
    photos=[]
    for row in data.get('photos',[]):
        photo=normalize(row,'photo');photo['labels']=labels(row.get('labels'))
        photo['content_hash']=context.get('photos',{}).get(photo['id'],'unknown')
        photos.append(photo)
    clips=[]
    for row in data.get('comparisons',[]):
        clip=normalize(row,'clip');clip['name']=clip['name'].strip()
        for side in ('before','after'):clip[side+'_crop']=normalize(row.get(side+'_crop'),'crop')
        clip['labels']=labels(row.get('labels'));clips.append(clip)
    raw_cover=data.get('cover');cover=normalize(raw_cover,'cover')
    cover['highlights']=[{**r,'color':r['color'].lower()} for r in (raw_cover or {}).get('highlights',[])]
    if not any(p['id']==cover['photo_id'] for p in photos):
        cover['photo_id']=next((p['id'] for p in photos if p['role']=='after'),photos[0]['id'] if photos else '')
    body=normalize((raw_cover or {}).get('body'),'body')
    if raw_cover is None:body.update(enabled=False,logo_enabled=False)
    body['highlights']=[{**r,'color':r['color'].lower()} for r in ((raw_cover or {}).get('body') or {}).get('highlights',[])]
    cover['body']=body
    names={a['id']:a['name'] for a in context.get('assets',[])}
    def overlays(rows):return [{**normalize(o,'overlay'),'name':names.get(o.get('source'),o.get('name',''))} for o in rows]
    result=dict(schema='interior-content-v1',photos=photos,comparisons=clips,cover=cover,
        overlays=overlays(data.get('overlays',[])),
        comparison_overlays=overlays(data.get('comparison_overlays',[])),
        music=normalize(data.get('music'),'music'),template_id=data.get('template_id','items'),
        assets=sorted(context.get('assets',[]),key=lambda a:a['id']),music_asset=context.get('music'),
        video=dict(width=context.get('width',1080),fps=30),engine=context.get('engine','unknown'))
    tour=data.get('tour') or {}
    if data.get('template_id')=='tour' or tour.get('rooms') or tour.get('clips') or context.get('floor_plan') or context.get('videos'):
        result['tour']={**normalize(tour,'tour'),'rooms':[normalize(r,'room') for r in tour.get('rooms',[])],
            'clips':[{**normalize(c,'tour_clip'),'crop':normalize(c.get('crop'),'crop'),'labels':labels(c.get('labels'))} for c in tour.get('clips',[])],
            'overlays':overlays(tour.get('overlays',[])),'plan':context.get('floor_plan'),'videos':context.get('videos',[]),'layout':context.get('tour_layout')}
    return result


@lru_cache(maxsize=1)
def engine_signature():
    from .rendering import font_path
    files=['frontend/cover-layout.json','frontend/body-layout.json','frontend/safe-area.json',
           'assets/covers/opening-template.png','assets/covers/body-template.png',
           'templates/items.json','templates/compare.json']
    hashes={name:(digest(json.loads((ROOT/name).read_text(encoding='utf-8'))) if name.endswith('.json')
                  else sha256((ROOT/name).read_bytes()).hexdigest()) for name in files}
    hashes['pipeline']='pillow-ffmpeg-v1'  # 只有實際渲染規則變更才升級，不因註解或傳輸版本改變。
    hashes['font']=sha256(Path(font_path()).read_bytes()).hexdigest()
    return digest(hashes)


def context(state, width=None):
    cache=state.setdefault('_version_media_cache',{})
    live=set()
    def hashed(ident,data):
        live.add(ident);prior=cache.get(ident)
        if prior is None or prior[0] is not data:cache[ident]=(data,sha256(data).hexdigest())
        return cache[ident][1]
    photos={p.id:hashed('photo:'+p.id,p.original) for p in state.get('photos',[])}
    undo=state.get('photo_undo')
    if undo and undo.id not in photos:photos[undo.id]=hashed('photo:'+undo.id,undo.original)
    assets=[dict(id=a.id,name=a.name,builtin=a.builtin,width=a.width,height=a.height,
                 content_hash=hashed('png:'+a.id,a.original)) for a in state.get('overlay_assets',{}).values()]
    music=state.get('music_asset')
    music_data=dict(id=music.id,name=music.name,duration=music.duration,truncated=music.truncated,
                    content_hash=hashed('music:'+music.id,music.data)) if music else None
    from .tour import LAYOUT
    plan=state.get('floor_plan')
    plan_data=dict(id=plan.id,name=plan.name,width=plan.width,height=plan.height,content_hash=hashed('plan:'+plan.id,plan.original)) if plan else None
    videos=[dict(id=v.id,name=v.name,width=v.width,height=v.height,duration=v.duration,has_audio=v.has_audio,content_hash=hashed('video:'+v.id,v.data)) for v in state.get('video_assets',{}).values()]
    for key in list(cache):
        if key not in live:del cache[key]
    return dict(photos=photos,assets=assets,music=music_data,width=state.get('video_width',1080) if width is None else width,
                floor_plan=plan_data,videos=sorted(videos,key=lambda v:v['id']),tour_layout=LAYOUT,engine=engine_signature(),schema=SCHEMA)


def project_version(state, width=None):
    data=dict(photos=[p.metadata() for p in state.get('photos',[])],
              template_id=state.get('template_mode','items'),
              **{k:state.get(k,[] if k in ('overlays','comparisons','comparison_overlays') else None)
                 for k in ('overlays','comparisons','comparison_overlays','cover','music')},tour=state.get('tour'))
    return digest(document(data,context(state,width)))


def refresh(state):
    version=project_version(state);previous=state.get('content_version')
    if previous is not None and previous!=version:
        state['revision']=state.get('revision',0)+1
        state['project_payload']=None
    state['content_version']=version
    return version


def status(state):
    return dict(synced=state.get('content_version'),zip=state.get('zip_version'),
                mp4=state.get('mp4_version'),backup=state.get('backup_confirmed_version'),
                download_requested=state.get('zip_download_requested_version'),context=context(state))


def complete_export(state, data, seconds, version):
    """只在新成品成功後替換主要結果；失敗不呼叫此函式。"""
    state.update(output=data,output_seconds=seconds,mp4_version=version)


def reset_versions(state):
    for key in ('content_version','zip_version','mp4_version','backup_confirmed_version',
                'zip_download_requested_version','zip_download_request_id','frontend_version','frontend_seq','_version_media_cache',
                'guard_request','guard_approved','guard_import_project','photo_undo','photo_undo_preview'):
        state.pop(key,None)
