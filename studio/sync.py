"""元件批次同步交易：驗證版本、去重、以整份草稿替換，而非附加標籤。"""
from .models import update_project
from .overlays import validate_overlays
from dataclasses import replace
from .comparison import validate_comparisons
from .cover import validate_cover, DURATION
from .music import validate_music

BGM_API_VERSION = 7


def apply_editor_event(photos, event, session, revision, request=None):
    if event.get("session") != session:
        raise ValueError("此草稿屬於另一個工作階段，請重新載入。")
    if event.get("base_revision") != revision:
        raise ValueError("專案已更新，草稿已保留；請再次套用變更。")
    action = event.get("action")
    if action not in ("apply", "export"):
        raise ValueError("此編輯操作不受支援。")
    if action == "export" and (not request or event.get("request") != request):
        raise ValueError("輸出請求已過期，請重新按輸出影片。")
    rows = event.get("photos")
    if not isinstance(rows, list):
        raise ValueError("照片清單格式不正確。")
    known = {photo.id: photo for photo in photos}
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    if len(ids) != len(rows) or len(set(ids)) != len(ids) or not set(ids) <= set(known):
        raise ValueError("照片識別碼不正確。")
    # update_project 會先完整驗證所有欄位，成功後才一次套用。
    updated = update_project([known[ident] for ident in ids], rows)
    if action == "export" and not updated:
        raise ValueError("請保留至少一張照片再輸出。")
    return updated


def consume_editor_event(state, event):
    """在建立元件前讀取新事件，同一 nonce 僅處理一次；不額外 rerun。"""
    if not isinstance(event, dict):
        return
    nonce = event.get("nonce")
    if not isinstance(nonce, str) or not nonce or len(nonce) > 64:
        return
    seen = state.get("editor_seen", [])
    if nonce in seen:
        return
    state["editor_seen"] = (seen + [nonce])[-100:]
    request = state.get("pending_export")
    if (event.get("action") == "cancel_export" and event.get("session") == state["editor_session"]
            and request and event.get("request") == request["id"]):
        state["pending_export"] = None
        state["editor_response"] = dict(nonce=nonce, ok=False, message="請先修正編輯器欄位，再重新輸出。")
        return
    try:
        # 用輕量 Photo 複本先驗證全部設定，原始 bytes 共用；成功才一起提交。
        template=state.get("template_mode","items")
        if event.get("template_id",template)!=template:
            raise ValueError("模板已切換，草稿保留；請再次套用。")
        staged=apply_editor_event([replace(p) for p in state["photos"]],event,state["editor_session"],
                                  state["revision"],request["id"] if request else None)
        clips=validate_comparisons(event.get("comparisons",state.get("comparisons",[])),staged)
        raw_cover=event.get('cover',state.get('cover'))
        if isinstance(raw_cover,dict) and 'body' not in raw_cover and isinstance(state.get('cover'),dict):
            raw_cover={**raw_cover,'body':state['cover'].get('body')}  # 舊頁面事件不清除新的正文設定。
        elif isinstance(raw_cover,dict) and isinstance(raw_cover.get('body'),dict) and not any(key in raw_cover['body'] for key in ('auto_timing','start','end')):
            previous=state.get('cover',{}).get('body',{})
            raw_cover={**raw_cover,'body':{**raw_cover['body'],**{key:previous[key] for key in ('auto_timing','start','end') if key in previous}}}
        if isinstance(raw_cover,dict) and isinstance(raw_cover.get('body'),dict) and not any(key in raw_cover['body'] for key in ('x','y')):
            previous=(state.get('cover') or {}).get('body',{})
            raw_cover={**raw_cover,'body':{**raw_cover['body'],**{key:previous[key] for key in ('x','y') if key in previous}}}
        if 'cover' not in event and isinstance(raw_cover,dict) and raw_cover.get('photo_id') not in {p.id for p in staged}:
            raw_cover={**raw_cover,'photo_id':''}  # 舊版事件刪除來源時，自動改選可用照片。
        cover=validate_cover(raw_cover,staged)
        music=validate_music(event.get('music',state.get('music')),state.get('music_asset'))
        prefix=DURATION if cover['enabled'] and staged else 0
        duration=sum(p.duration for p in staged)+prefix
        if (sum(c['duration'] for c in clips) if template=='compare' else sum(p.duration for p in staged))+prefix>120:
            raise ValueError('影片含片頭最長120秒，請縮短片段。')
        overlays = validate_overlays(event.get("overlays", state.get("overlays", [])),
                                     state.get("overlay_assets", {}), duration)
        comparison_overlays=validate_overlays(event.get("comparison_overlays",state.get("comparison_overlays",[])),
                                      state.get("overlay_assets",{}),sum(c["duration"] for c in clips)+prefix)
        if template=="compare" and event.get("action")=="export" and not clips:
            raise ValueError("請先新增一組前後配對再輸出。")
        photos = apply_editor_event(state["photos"], event, state["editor_session"],
                                    state["revision"], request["id"] if request else None)
        state["photos"] = photos
        state["overlays"] = overlays
        state["comparisons"]=clips
        state["comparison_overlays"]=comparison_overlays
        state['cover']=cover
        state['music']=music
        acknowledgements = event.get("imported_batches", [])
        if isinstance(acknowledgements, list):
            state["ai_imports"] = [batch for batch in state.get("ai_imports", [])
                                   if batch["id"] not in acknowledgements]
        state["revision"] += 1
        state["project_payload"] = None
        if not photos:
            state["editor_assets"] = {}
        state["output"] = None
        state["output_seconds"] = None
        state["editor_response"] = dict(nonce=nonce, ok=True, seq=event.get("seq"))
        if event["action"] == "export":
            state["render_job"] = dict(width=request["width"], nonce=nonce)
            state["editor_busy"] = True
            state["pending_export"] = None
    except (ValueError, KeyError, TypeError) as exc:
        state["editor_response"] = dict(nonce=nonce, ok=False, message=str(exc))
        if event.get("action") == "export":
            state["pending_export"] = None
