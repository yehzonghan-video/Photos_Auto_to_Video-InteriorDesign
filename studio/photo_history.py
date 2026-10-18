"""只保留最近一張已刪來源，供既有批次同步恢復；不放入ZIP或內容版本。"""
import hashlib
from .models import MAX_PHOTOS
from .photo_processing import SESSION_BYTES, SESSION_PIXELS
BGM_API_VERSION = 10


def sources(state,event):
    photos=list(state['photos']);ident=event.get('restore_photo')
    if ident and ident not in {p.id for p in photos}:
        old=state.get('photo_undo')
        if old is None or old.id!=ident:raise ValueError('復原照片來源已失效，請由ZIP還原。')
        photos.append(old)
    rows=event.get('photos',[])
    if len(rows)>MAX_PHOTOS:raise ValueError('最多12張來源照片，無法復原。')
    ids={r.get('id') for r in rows if isinstance(r,dict)}
    selected=[p for p in photos if p.id in ids]
    if sum(len(p.original) for p in selected)>SESSION_BYTES or sum(p.width*p.height for p in selected)>SESSION_PIXELS:
        raise ValueError('復原會超過照片工作階段容量，請先減少來源；原資料保留。')
    return photos


def commit(state,before,after,last_id=None):
    removed=[p for p in before if p.id not in {p.id for p in after}]
    if removed:
        state['photo_undo']=next((p for p in removed if p.id==last_id),removed[-1])
        state.pop('photo_undo_preview',None)
    elif state.get('photo_undo') and state['photo_undo'].id in {p.id for p in after}:
        state.pop('photo_undo',None);state.pop('photo_undo_preview',None)


def preview(state):
    p=state.get('photo_undo')
    if p is None:return None
    cached=state.get('photo_undo_preview')
    if not cached or cached['id']!=p.id:
        from .photo_processing import preview_data
        import base64
        cached={**p.metadata(),'content_hash':hashlib.sha256(p.original).hexdigest(),
                'image':'data:image/jpeg;base64,'+base64.b64encode(preview_data(p)).decode('ascii'),'tiles':{}}
        state['photo_undo_preview']=cached
    return cached
