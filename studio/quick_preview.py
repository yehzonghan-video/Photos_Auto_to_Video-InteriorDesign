"""匯入時唯讀快照的單影格比較；共用既有構圖、動畫與圖層合成器。"""
from dataclasses import replace
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from .rendering import crop_photo,fit_image,label_tile,render_frame,data_url
from .cover import cover_frame,DURATION
from .body import title_span,title_visible,logo_visible,body_layer

BGM_API_VERSION=10


def capture(state):
    from .output_jobs import snapshot
    state['_quick_original']=snapshot(state)
    state['_quick_frames']={}
    state.pop('_quick_preview_error',None)


def scenes(source):
    cover=source['cover'];prefix=DURATION if cover['enabled'] and source['photos'] else 0
    mode=source['template_mode'];clips=source['tour']['clips'] if mode=='tour' else source['comparisons'] if mode=='compare' else source['photos']
    total=prefix+sum(c['duration'] if isinstance(c,dict) else c.duration for c in clips)
    span=title_span(cover['body'],prefix,total);result=[];offset=prefix
    if prefix:result.append(dict(id='project-cover',name='封面',time=0.,visible=True))
    for c in clips:
        ident,name,length=(c['id'],c['name'],c['duration']) if isinstance(c,dict) else (c.id,c.name,c.duration)
        left=max(offset,span[0]);right=min(offset+length,span[1]);visible=cover['body']['enabled'] and right>left
        t=(left+right)/2 if visible else offset+min(.5,length/2)
        t=max(offset,min(offset+length-1/30,round(t*30)/30))
        result.append(dict(id=ident,name=name,time=t,visible=visible));offset+=length
    return result


def frame(source,ident):
    row=next((s for s in scenes(source) if s['id']==ident),None)
    if row is None:raise ValueError('找不到原始片段，請重新匯入ZIP。')
    cover=source['cover'];mode=source['template_mode'];photos=source['photos'];prefix=DURATION if cover['enabled'] and photos else 0
    clips=source['tour']['clips'] if mode=='tour' else source['comparisons'] if mode=='compare' else photos
    length=prefix+sum(c['duration'] if isinstance(c,dict) else c.duration for c in clips)
    overlays=source['tour']['overlays'] if mode=='tour' else source['comparison_overlays'] if mode=='compare' else source['overlays']
    from .overlays import prepare_overlays
    prepared=prepare_overlays(overlays,source['overlay_assets']);t=row['time']
    if ident=='project-cover':return render_frame(cover_frame(cover,photos),[],[],t,prepared,t),row
    offset=prefix
    for c in clips:
        cid,seconds=(c['id'],c['duration']) if isinstance(c,dict) else (c.id,c.duration)
        if cid==ident:break
        offset+=seconds
    local=t-offset
    if mode=='compare':
        from .comparison import prepare_comparison,comparison_frame
        base=comparison_frame(c,prepare_comparison(c,photos),local);labels=c['labels']
    elif mode=='tour':
        labels=c['labels']
        if c['kind']=='photo':base=crop_photo(replace(next(p for p in photos if p.id==c['source']),**c['crop']))
        else:
            from .tour_video import decoder
            with TemporaryDirectory(prefix='title-preview-') as folder:
                reader=decoder(source['video_assets'][c['source']],{**c,'in':c['in']+local,'duration':1/30},folder)
                try:base=fit_image(next(reader),SimpleNamespace(**c['crop']))
                finally:reader.close()
    else:base=crop_photo(c);labels=c.labels
    if logo_visible(cover['body'],t,prefix,length):base.alpha_composite(body_layer(cover,include_title=False))
    if title_visible(cover['body'],t,prefix,length):base.alpha_composite(body_layer(cover,include_logo=False))
    image=render_frame(base,labels,[label_tile(l) for l in labels],local,prepared,t)
    if mode=='tour':
        from .tour import plan_layer
        image=image.convert('RGBA');image.alpha_composite(plan_layer(source['floor_plan'],source['tour'],c['room_id']))
    return image,row


def receive(state,event):
    source=state.get('_quick_original')
    if source is None:raise ValueError('尚未建立原始比較快照，請先匯入ZIP。')
    ident=event.get('scene_id');cache=state.setdefault('_quick_frames',{})
    if not isinstance(ident,str) or not ident or len(ident)>64:raise ValueError('原始預覽片段不正確。')
    if ident in cache:return
    image,row=frame(source,ident);image=image.convert('RGB');image.thumbnail((540,960))
    cache[ident]=dict(**row,image=data_url(image,'JPEG'))
    state.pop('_quick_preview_error',None)
