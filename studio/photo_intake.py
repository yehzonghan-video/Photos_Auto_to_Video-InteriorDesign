"""照片選檔事件的冪等交易；媒體準備成功後才交換工作階段資料。"""
from copy import deepcopy
from dataclasses import replace
import hashlib

from .models import MAX_PHOTOS, MAX_TOTAL_SECONDS, load_photo
from .photo_processing import fit_session
from .versioning import refresh

BGM_API_VERSION = 10


def batch_id(session, role, epoch, files):
    # epoch 隔開使用者刻意再次選檔；file_id 隔開同一 widget 的不同選檔事件。
    identities = [str(getattr(f, 'file_id', None) or
                      hashlib.sha256(f.getvalue()).hexdigest()) for f in files]
    return hashlib.sha256(repr((session, role, epoch, identities)).encode()).hexdigest()


def _remember(state, key, result):
    receipts = dict(state.get('photo_receipts', {}))
    receipts[key] = result
    state['photo_receipts'] = dict(list(receipts.items())[-100:])
    return result


def append_photos(state, files, role, event_id):
    """同批部分成功；不以照片內容永久去重，不改既有 ID 與編輯資料。"""
    if event_id in state.get('photo_receipts', {}):
        return {**state['photo_receipts'][event_id], 'replayed': True}
    proposed = list(state['photos'])
    added, errors = [], []
    for file in files:
        try:
            if len(proposed) >= MAX_PHOTOS:
                raise ValueError(f'最多 {MAX_PHOTOS} 張來源照片（工作階段處理上限）。若剛刪除照片，請在「進階／同步恢復」按「同步草稿」釋放名額，再選檔。')
            fresh = load_photo(file.name, file.getvalue())
            fresh.role = role
            if sum(p.duration for p in proposed) + fresh.duration > MAX_TOTAL_SECONDS:
                raise ValueError('照片總長最多120秒，請先縮短現有照片秒數。')
            candidate = fit_session(proposed + [fresh])
            proposed = candidate
            added.append(fresh.id)
        except (ValueError, OSError, MemoryError) as exc:
            errors.append(f'{file.name}：{str(exc) or "記憶體不足，請稍後重試。"}')
    if added:
        state['photos'] = proposed
        refresh(state)
    return _remember(state, event_id, dict(added=added, errors=errors, replayed=False))


def replace_photo(state, target_id, file, event_id):
    if event_id in state.get('photo_receipts', {}):
        return {**state['photo_receipts'][event_id], 'replayed': True}
    target = next((p for p in state['photos'] if p.id == target_id), None)
    if target is None:
        raise ValueError('這張照片已不存在，請重新選取。')
    # 解析、最佳化都使用候選複本；失敗不動原檔、標籤與配對。
    loaded = load_photo(file.name, file.getvalue())
    fresh = replace(target, name=loaded.name, original=loaded.original,
                    width=loaded.width, height=loaded.height,
                    optimization_note=loaded.optimization_note, labels=deepcopy(target.labels))
    changed_image = fresh.original != target.original
    clips = deepcopy(state.get('comparisons', []))
    if changed_image:
        for label in fresh.labels:
            if label.get('source') == 'gemini':
                label['needs_review'] = True
        for clip in clips:
            if target_id in (clip['before_id'], clip['after_id']):
                for label in clip['labels']:
                    if label.get('source') == 'gemini':
                        label['needs_review'] = True
    proposed = fit_session([fresh if p.id == target_id else p for p in state['photos']])
    state['photos'], state['comparisons'] = proposed, clips
    refresh(state)
    return _remember(state, event_id, dict(added=[], errors=[], replayed=False))
