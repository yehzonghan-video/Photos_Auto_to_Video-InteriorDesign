from pathlib import Path
import base64
import hashlib
import streamlit.components.v1 as components

from .rendering import data_url, label_tile, template_config
from .photo_processing import preview_data
from .safe_area import SAFE_AREA
from .cover import validate_cover, template_bytes, title_tile, LAYOUT
from .music import validate_music
from .body import LAYOUT as BODY_LAYOUT, effective_title, template_bytes as body_template_bytes

BGM_API_VERSION = 7

editor = components.declare_component("interior_studio_editor", path=str(Path(__file__).resolve().parents[1] / "frontend"))


def payload(photos, cache=None, assets=None, overlays=None, comparisons=None, template="items", comparison_overlays=None, cover=None,
            music=None, music_asset=None):
    cache = {} if cache is None else cache
    live_ids = {photo.id for photo in photos} | {"clip:"+c["id"] for c in comparisons or []}
    live_ids.add('__cover__')
    live_ids.add('__body__')
    if music_asset:live_ids.add('__music__')
    for ident in list(cache):
        if ident not in live_ids:
            del cache[ident]
    rows = []
    for photo in photos:
        row = photo.metadata()
        photo_assets = cache.setdefault(photo.id, {"tiles": {}})
        # 編輯器只收較小預覽；原始／最佳化工作副本保留給 AI 與 FFmpeg。
        digest = hashlib.sha256(photo.original).hexdigest()
        if photo_assets.get("digest") != digest:
            photo_assets["image"] = "data:image/jpeg;base64," + base64.b64encode(preview_data(photo)).decode("ascii")
            photo_assets["digest"] = digest
        row["image"] = photo_assets["image"]
        row["content_hash"] = digest
        row["tiles"] = {}
        for label in photo.labels:
            style = {key: label[key] for key in ("text", "font_size", "color", "background", "opacity", "radius")}
            style['stroke_width']=2
            previous = photo_assets["tiles"].get(label["id"])
            if previous is None or previous["style"] != style:
                tile = label_tile(label)
                previous = dict(src=data_url(tile), width=tile.width, height=tile.height, style=style)
                photo_assets["tiles"][label["id"]] = previous
            row["tiles"][label["id"]] = previous
        photo_assets["tiles"] = dict(row["tiles"])
        rows.append(row)
    clips=[]
    for clip in comparisons or []:
        row=dict(clip);row["tiles"]={}
        cached=cache.setdefault("clip:"+clip["id"],{"tiles":{}})
        for label in clip["labels"]:
            style={key:label[key] for key in ("text","font_size","color","background","opacity","radius")}
            style['stroke_width']=2
            tile=cached["tiles"].get(label["id"])
            if tile is None or tile["style"]!=style:
                image=label_tile(label);tile=dict(src=data_url(image),width=image.width,height=image.height,style=style)
            row["tiles"][label["id"]]=tile
        cached["tiles"]=dict(row["tiles"]);clips.append(row)
    cover=validate_cover(cover,photos);cover_assets={'layout':LAYOUT}
    if photos:
        cached=cache.setdefault('__cover__',{})
        style={k:cover[k] for k in ('title','color','font_size','highlights')}
        signature={**style,'layout':LAYOUT['title']}
        if cached.get('style')!=signature:
            cached.update(style=signature,title=data_url(title_tile(cover)))
        cover_assets.update(title=cached['title'],template='data:image/png;base64,'+base64.b64encode(template_bytes()).decode('ascii'))
    body_assets={'layout':BODY_LAYOUT}
    if photos:
        cached=cache.setdefault('__body__',{})
        style=effective_title(cover)
        signature={**style,'layout':BODY_LAYOUT['title']}
        if cached.get('style')!=signature or 'bounds' not in cached:
            tile=title_tile(style,BODY_LAYOUT['title'])
            cached.update(style=signature,title=data_url(tile),bounds=tile.getbbox())
        body_assets.update(title=cached['title'],bounds=cached['bounds'],template='data:image/png;base64,'+base64.b64encode(body_template_bytes()).decode('ascii'))
    music=validate_music(music,music_asset)
    music_data=None
    if music_asset:
        cached=cache.setdefault('__music__',{})
        if cached.get('id')!=music_asset.id:cached.update(id=music_asset.id,data=music_asset.metadata())
        elif cached['data']['name']!=music_asset.name or cached['data']['truncated']!=music_asset.truncated:
            cached['data']={**cached['data'],'name':music_asset.name,'truncated':music_asset.truncated}
        music_data=cached['data']
    return dict(photos=rows, template=template_config(template), template_id=template, schema_version=4, safe_area=SAFE_AREA,
                music=music,music_asset=music_data,
                cover=cover,cover_assets=cover_assets,body_assets=body_assets,
                assets=[asset.metadata() for asset in (assets or {}).values()], overlays=overlays or [],
                comparisons=clips, comparison_overlays=comparison_overlays or [])
