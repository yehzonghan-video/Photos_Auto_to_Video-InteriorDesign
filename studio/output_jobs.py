"""固定快照的背景輸出；worker 不讀寫 Streamlit Session State。"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import threading
import time
import uuid

from .versioning import project_version, complete_export

BGM_API_VERSION = 10
OUTPUT_API_VERSION = 3
_LOCK = globals().get('_LOCK',threading.RLock())
_POOL = globals().get('_POOL',ThreadPoolExecutor(max_workers=2,thread_name_prefix='studio-output'))
_TASKS = globals().get('_TASKS',{})
_JANITOR = globals().get('_JANITOR',None)


def _expire_results():
    while True:
        time.sleep(30)
        with _LOCK:
            for key,task in list(_TASKS.items()):
                if task['future'].done() and time.monotonic()-task['created']>900:del _TASKS[key]


def snapshot(state):
    """只複製製片資料；不可變的媒體 bytes 共用，不複製Secrets或整個Session State。"""
    return dict(photos=[replace(p,labels=deepcopy(p.labels)) for p in state['photos']],
                tour=deepcopy(state.get('tour')),floor_plan=replace(state['floor_plan']) if state.get('floor_plan') else None,
                video_assets={k:replace(v) for k,v in state.get('video_assets',{}).items()},
                overlay_assets={k:replace(a) for k,a in state.get('overlay_assets',{}).items()},
                music_asset=replace(state['music_asset']) if state.get('music_asset') else None,
                template_mode=state.get('template_mode','items'),video_width=state.get('video_width',1080),
                **{k:deepcopy(state.get(k,[] if k in ('overlays','comparisons','comparison_overlays') else None))
                   for k in ('overlays','comparisons','comparison_overlays','cover','music')})


def _run(source, kind, version, progress):
    if project_version(source)!=version:raise ValueError('輸出快照版本不符，請重試。')
    started=time.monotonic()
    if kind=='zip':
        from .project_io import build_archive, archive_filename
        progress(.1,'正在產生ZIP…')
        data=build_archive(source)
        return dict(data=data,filename=archive_filename(source['cover']['title']))
    from .export import export_video
    width=source['video_width'];compare=source['template_mode']=='compare'
    data=export_video(source['photos'],width,width*16//9,progress=progress,
        overlays=source['tour']['overlays'] if source['template_mode']=='tour' else source['comparison_overlays'] if compare else source['overlays'],
        assets=source['overlay_assets'],template=source['template_mode'],comparisons=source['comparisons'],
        cover=source['cover'],music=source['music'],music_asset=source['music_asset'],
        **(dict(tour=source['tour'],floor_plan=source['floor_plan'],videos=source['video_assets']) if source['template_mode']=='tour' else {}))
    return dict(data=data,seconds=round(time.monotonic()-started,1))


def start(state,event):
    global _JANITOR
    prepared=state.get('prepared_output')
    if (not prepared or event.get('operation_id')!=prepared['id'] or event.get('content_version')!=prepared['version']
            or event.get('session')!=state.get('editor_session')):
        raise ValueError('輸出確認已失效，草稿保留，請重試。')
    if time.monotonic()-prepared['created']>300:raise ValueError('輸出確認逾時，請重新按輸出或下載ZIP。')
    with _LOCK:
        for key,item in list(_TASKS.items()):
            if item['future'].done() and time.monotonic()-item['created']>900:del _TASKS[key]
        if len(_TASKS)>=2:
            raise RuntimeError('目前已有輸出工作，請稍候再試。')
        ident=uuid.uuid4().hex
        task=dict(created=time.monotonic(),progress=0.,message='正在準備固定版本素材…')
        def progress(value,message):
            with _LOCK:task.update(progress=max(0.,min(1.,float(value))),message=message)
        future=_POOL.submit(_run,prepared['snapshot'],prepared['kind'],prepared['version'],progress)
        task['future']=future;_TASKS[ident]=task
        if _JANITOR is None or not _JANITOR.is_alive():
            _JANITOR=threading.Thread(target=_expire_results,daemon=True,name='output-expiry');_JANITOR.start()
    state['output_task']=dict(id=prepared['id'],task=ident,kind=prepared['kind'],version=prepared['version'],revision=prepared['revision'])
    state['output_status']={**state['output_task'],'phase':'working'}
    state.pop('prepared_output',None);state['editor_busy']=True


def progress(state):
    job=state.get('output_task')
    if not job:return None
    with _LOCK:
        task=_TASKS.get(job['task'])
        if task is None:return dict(done=True,progress=0,message='工作階段或輸出程序已中斷，請重試。')
        return dict(done=task['future'].done(),progress=task['progress'],message=task['message'])


def collect(state,static_enabled=False,base=''):
    job=state.get('output_task');status=progress(state)
    if not job or not status['done']:return False
    with _LOCK:task=_TASKS.pop(job['task'],None)
    try:
        if task is None:raise RuntimeError('工作階段或輸出程序已中斷，請重試。')
        result=task['future'].result()
        if job['kind']=='zip':
            from .downloads import publish,revoke
            archive=dict(**result,request_id=job['id'],content_version=job['version'],revision=job['revision'])
            if static_enabled:
                try:archive.update(publish(result['data'],base))
                except OSError:archive['download_warning']='無法建立短效網址，請使用備用下載。'
            else:archive['download_warning']='此環境尚未啟用static serving，請使用備用下載；部署設定更新後可能需要重啟。'
            revoke(state.get('project_archive'))
            state['project_archive']=archive;state['zip_version']=job['version']
        else:complete_export(state,result['data'],result['seconds'],job['version'])
        state['output_status']=dict(id=job['id'],kind=job['kind'],version=job['version'],phase='done')
    except Exception as exc:
        reason=str(exc) if isinstance(exc,(ValueError,RuntimeError,OSError,TimeoutError,MemoryError)) else '處理發生未預期錯誤'
        message=f"{'ZIP' if job['kind']=='zip' else 'MP4'}未完成：{reason}；草稿及上一個成功檔案仍保留，可重新按原按鈕。"
        state['output_status']=dict(id=job['id'],kind=job['kind'],version=job['version'],phase='error',message=message)
        state['notice']=message;state['notice_error']=True
    finally:
        state.pop('output_task',None);state['editor_busy']=False
    return True


def prepare(state,event,version):
    if state.get('prepared_output') or state.get('output_task'):raise ValueError('上一個輸出請求尚未完成，請稍候。')
    source=snapshot(state)
    if project_version(source)!=version:raise ValueError('快照版本不符，請重新下載或輸出。')
    state['prepared_output']=dict(id=event['nonce'],kind='zip' if event['action']=='save_project' else 'mp4',
        version=version,revision=state.get('revision'),snapshot=source,created=time.monotonic())
    state['output_status']=dict(id=event['nonce'],kind=state['prepared_output']['kind'],version=version,phase='prepared')


def release(state):
    """工作區核准重設後撤銷短效下載；進行中的工作由既有保護阻擋。"""
    from .downloads import revoke
    revoke(state.get('project_archive'))
    for key in ('prepared_output','output_task','output_status'):state.pop(key,None)
