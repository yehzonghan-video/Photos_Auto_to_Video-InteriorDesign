"""元件批次同步交易：驗證版本、去重、以整份草稿替換，而非附加標籤。"""
from .models import update_project
from .overlays import validate_overlays
from dataclasses import replace
from .comparison import validate_comparisons
from .cover import validate_cover, DURATION
from .music import validate_music
from .versioning import refresh, project_version

BGM_API_VERSION = 10
EDITOR_UI_VERSION = 8


def apply_editor_event(photos, event, session, revision, request=None):
    if event.get("session") != session:
        raise ValueError("此草稿屬於另一個工作階段，請重新載入。")
    if event.get("base_revision") != revision:
        raise ValueError("專案已更新，草稿已保留；請再次套用變更。")
    action = event.get("action")
    if action not in ("apply", "export", "save_project"):
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
    if action in ("export", "save_project") and not updated and event.get('template_id')!='tour':
        raise ValueError("請保留至少一張照片再輸出或儲存專案。")
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
    if event.get('action') in ('set_edit_mode','quick_original'):
        if event.get('session')!=state.get('editor_session') or state.get('guard_request'):return
        if event['action']=='set_edit_mode':
            if event.get('mode') in ('full','quick'):state['edit_mode']=event['mode']
        else:
            from .quick_preview import receive
            try:receive(state,event)
            except Exception as exc:
                state['_quick_preview_error']=(str(exc) if isinstance(exc,(ValueError,RuntimeError,OSError,TimeoutError)) else '') or '原始預覽無法產生，專案未修改。'
        return
    if event.get('action')=='inspect_guard':
        from .protection import receive_probe
        receive_probe(state,event)
        return
    if event.get('action') in ('start_output','zip_download_requested','downloads_requested','retry_output_zip','cancel_output'):
        if event.get('session')!=state['editor_session'] or state.get('guard_request'):return
        if event['action']=='retry_output_zip':
            from .output_jobs import retry_zip
            try:retry_zip(state,event)
            except (ValueError,RuntimeError) as exc:state['output_status']=dict(id=event['nonce'],phase='error',message=str(exc))
            return
        if event['action']=='downloads_requested':
            requests=event.get('downloads',[])
            for item in requests if isinstance(requests,list) and len(requests)<=2 else []:
                if not isinstance(item,dict):continue
                saved=state.get('project_archive' if item.get('kind')=='zip' else 'mp4_download' if item.get('kind')=='mp4' else '') or {}
                if not saved or item.get('kind') not in ('zip','mp4') or item.get('operation_id')!=saved.get('request_id') or item.get('content_version')!=saved.get('content_version'):continue
                if item['kind']=='zip':
                    from .project_ui import download_requested
                    download_requested(state,saved['content_version'])
                else:state['mp4_download_request_id']=saved['request_id']
            return
        if event['action']=='cancel_output':
            prepared=state.get('prepared_output')
            if prepared and prepared['id']==event.get('operation_id'):
                state.pop('prepared_output',None)
                state['output_status']=dict(id=prepared['id'],phase='error',message='同步確認未完成，草稿保留，請重新按原按鈕。')
            return
        if event['action']=='zip_download_requested':
            saved=state.get('project_archive') or {}
            if event.get('operation_id')==saved.get('request_id') and event.get('content_version')==saved.get('content_version'):
                from .project_ui import download_requested
                download_requested(state,saved['content_version'])
            return
        if state.get('output_task') or (state.get('output_status') or {}).get('id')==event.get('operation_id') and (state.get('output_status') or {}).get('phase')=='done':return
        from .output_jobs import start
        try:start(state,event)
        except (ValueError,RuntimeError) as exc:
            # 重送已啟動請求不覆蓋進度；其他失敗保留草稿與先前成果。
            if (state.get('output_task') or {}).get('id')!=event.get('operation_id'):
                prepared=state.get('prepared_output')
                if prepared and prepared['id']==event.get('operation_id'):state.pop('prepared_output',None)
                state['output_status']=dict(id=event.get('operation_id'),phase='error',message=str(exc))
        return
    if event.get('action') == 'replace_photo':
        # 只請求開啟目前來源照片的原生選檔視窗；選取本身不是內容變更。
        if (event.get('session') == state['editor_session']
                and event.get('base_revision') == state['revision']
                and not state.get('guard_request') and not state.get('editor_busy')
                and not state.get('pending_export') and not state.get('prepared_output')
                and event.get('photo_id') in {p.id for p in state['photos']}):
            state['replacement_request'] = dict(id=nonce, photo_id=event['photo_id'])
        elif event.get('session') == state['editor_session']:
            state['notice'] = '照片替換請求已過期或專案正在處理中，草稿保留；請稍後重新選取照片。'
            state['notice_error'] = True
        return
    request = state.get("pending_export")
    protocol=event.get('output_protocol')==3 and event.get('action') in ('export','save_project')
    if event.get('action') in ('export','save_project') and (state.get('prepared_output') or state.get('output_task') or state.get('editor_busy')):
        state['editor_response']=dict(nonce=nonce,ok=False,message='上一個輸出請求尚未完成，請稍候。');return
    if protocol:
        if (event.get('request')!=nonce or event.get('width')!=state.get('video_width',1080)
                or event.get('width') not in (360,720,1080) or not isinstance(event.get('content_version'),str)
                or ('zip_backup' in event and type(event['zip_backup']) is not bool)):
            state['editor_response']=dict(nonce=nonce,ok=False,message='輸出設定尚未更新，草稿保留，請重新按原按鈕。');return
        request=dict(id=nonce,width=event['width'])
    if (event.get("action") == "cancel_export" and event.get("session") == state["editor_session"]
            and request and event.get("request") == request["id"]):
        state["pending_export"] = None
        state["editor_response"] = dict(nonce=nonce, ok=False, message="請先修正編輯器欄位，再重新輸出。")
        return
    try:
        if 'content_version' not in state:refresh(state)
        # 用輕量 Photo 複本先驗證全部設定，原始 bytes 共用；成功才一起提交。
        template=state.get("template_mode","items")
        if event.get("template_id",template)!=template:
            raise ValueError("模板已切換，草稿保留；請再次套用。")
        from .photo_history import sources,commit
        bank=sources(state,event)
        staged=apply_editor_event([replace(p) for p in bank],event,state["editor_session"],
                                  state["revision"],request["id"] if request else None)
        clips=validate_comparisons(event.get("comparisons",state.get("comparisons",[])),staged)
        from .tour import validate_tour
        tour=validate_tour(event.get('tour',state.get('tour')),staged,state.get('video_assets',{}),state.get('floor_plan'))
        raw_cover=event.get('cover',state.get('cover'))
        if isinstance(raw_cover,dict) and 'body' not in raw_cover and isinstance(state.get('cover'),dict):
            raw_cover={**raw_cover,'body':state['cover'].get('body')}  # 舊頁面事件不清除新的正文設定。
        elif isinstance(raw_cover,dict) and isinstance(raw_cover.get('body'),dict) and not any(key in raw_cover['body'] for key in ('auto_timing','start','end')):
            previous=state.get('cover',{}).get('body',{})
            raw_cover={**raw_cover,'body':{**raw_cover['body'],**{key:previous[key] for key in ('auto_timing','start','end') if key in previous}}}
        if isinstance(raw_cover,dict) and isinstance(raw_cover.get('body'),dict) and not any(key in raw_cover['body'] for key in ('x','y')):
            previous=(state.get('cover') or {}).get('body',{})
            raw_cover={**raw_cover,'body':{**raw_cover['body'],**{key:previous[key] for key in ('x','y') if key in previous}}}
        if isinstance(raw_cover,dict) and isinstance(raw_cover.get('body'),dict):
            previous=(state.get('cover') or {}).get('body',{})
            raw_cover={**raw_cover,'body':{**raw_cover['body'],**{key:previous[key] for key in ('logo_auto_timing','logo_start','logo_end')
                                                             if key not in raw_cover['body'] and key in previous}}}
        if 'cover' not in event and isinstance(raw_cover,dict) and raw_cover.get('photo_id') not in {p.id for p in staged}:
            raw_cover={**raw_cover,'photo_id':''}  # 舊版事件刪除來源時，自動改選可用照片。
        cover=validate_cover(raw_cover,staged)
        music=validate_music(event.get('music',state.get('music')),state.get('music_asset'))
        prefix=DURATION if cover['enabled'] and staged else 0
        duration=sum(p.duration for p in staged)+prefix
        if (sum(c['duration'] for c in (tour['clips'] if template=='tour' else clips)) if template in ('tour','compare') else sum(p.duration for p in staged))+prefix>120:
            raise ValueError('影片含片頭最長120秒，請縮短片段。')
        tour['overlays']=validate_overlays(tour['overlays'],state.get('overlay_assets',{}),sum(c['duration'] for c in tour['clips'])+prefix)
        overlays = validate_overlays(event.get("overlays", state.get("overlays", [])),
                                     state.get("overlay_assets", {}), duration)
        comparison_overlays=validate_overlays(event.get("comparison_overlays",state.get("comparison_overlays",[])),
                                      state.get("overlay_assets",{}),sum(c["duration"] for c in clips)+prefix)
        if template=="compare" and event.get("action")=="export" and not clips:
            raise ValueError("請先新增一組前後配對再輸出。")
        if template=='tour' and event.get('action')=='export' and not tour['clips']:raise ValueError('請先加入導覽片段。')
        proposal={**state,'photos':staged,'comparisons':clips,'cover':cover,'music':music,
                  'overlays':overlays,'comparison_overlays':comparison_overlays,'tour':tour}
        accepted_version=project_version(proposal)
        if event.get('content_version') is not None and event['content_version']!=accepted_version:
            raise ValueError('草稿版本與伺服器資料不一致，內容已保留，請等待畫面更新後再次套用。')
        before=list(state['photos'])
        photos = apply_editor_event(bank, event, state["editor_session"],
                                    state["revision"], request["id"] if request else None)
        commit(state,before,photos,event.get('deleted_photo'))
        state["photos"] = photos
        state["overlays"] = overlays
        state["comparisons"]=clips
        state["comparison_overlays"]=comparison_overlays
        state['cover']=cover
        state['music']=music
        state['tour']=tour
        acknowledgements = event.get("imported_batches", [])
        if isinstance(acknowledgements, list):
            state["ai_imports"] = [batch for batch in state.get("ai_imports", [])
                                   if batch["id"] not in acknowledgements]
        refresh(state)
        state['frontend_version']=accepted_version
        state['frontend_seq']=event.get('seq')
        if not photos:
            state["editor_assets"] = {}
        state["editor_response"] = dict(nonce=nonce, ok=True, seq=event.get("seq"),content_version=accepted_version)
        if protocol:
            from .output_jobs import prepare
            prepare(state,event,accepted_version)
            state['editor_response']['operation_id']=nonce
        elif event['action'] == 'save_project':
            state['project_save_job'] = dict(version=accepted_version,nonce=nonce)
        if event["action"] == "export" and not protocol:
            state["render_job"] = dict(width=request["width"], nonce=nonce,
                                       content_version=project_version(state,width=request['width']))
            state["editor_busy"] = True
            state["pending_export"] = None
    except (ValueError, KeyError, TypeError) as exc:
        state["editor_response"] = dict(nonce=nonce, ok=False, message=str(exc))
        if event.get("action") == "export":
            state["pending_export"] = None
