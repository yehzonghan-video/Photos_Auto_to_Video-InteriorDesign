"""室內案例影片：前端草稿編輯與選用的 Gemini 辨識；無持久化照片。"""
from pathlib import Path
import importlib
import time
import uuid

import streamlit as st

from studio import bootstrap
from studio.rendering import font_path, template_config
from studio.ai_ui import ai_panel
from studio.overlays import discover_assets, load_asset, MAX_ASSETS
from studio.access import require_password, logout

st.set_page_config(page_title="室內案例影片工作室", page_icon="◩", layout="wide")
require_password()
try:
    if bootstrap.BGM_API_VERSION != 10 or getattr(bootstrap, 'EDITOR_UI_VERSION', None) != 8:
        importlib.reload(bootstrap)  # Cloud可能連相容性載入器也留著上一版。
    component_api, export_api, sync_api = bootstrap.video_modules()
    from studio.rendering import font_path,template_config
    from studio.cover import new_cover, DURATION
    from studio.music import new_music, load_music, MAX_MUSIC_UPLOAD_MB
    from studio.project_ui import prepare_download, import_panel, download_panel
    from studio import versioning, protection
    from studio import output_jobs, output_ui
    from studio.downloads import delivery
    from studio.photo_intake import append_photos, replace_photo, batch_id
    from studio.ai_ui import ai_panel
except (RuntimeError, ImportError, OSError) as exc:
    st.error(str(exc))
    st.caption('重新啟動會清除目前工作階段的照片與草稿；請先下載仍可取得的成果。')
    st.stop()
editor, payload = component_api.editor, component_api.payload
capabilities, export_video = export_api.capabilities, export_api.export_video
consume_editor_event = sync_api.consume_editor_event
st.markdown("""<style>
.block-container{max-width:1280px;padding-top:2rem;padding-bottom:2rem}
h1{font-size:2rem!important;letter-spacing:.025em}h2{font-size:1.3rem!important}
[data-testid="stMetricValue"]{font-size:1.6rem}
[data-testid="stSidebar"]{border-right:1px solid #ddd7ce}
.eyebrow{font-size:12px;letter-spacing:.2em;color:#a16e44;font-weight:600;margin-bottom:5px}
.intro{color:#73786c;font-size:15px;margin-bottom:22px}
.workflow{font-size:13px;padding:13px 18px;border:1px solid #ded8cb;border-radius:9px;margin:16px 0 20px;color:#58694e;background:#f0ece3}
</style>""", unsafe_allow_html=True)

cover_added='cover' not in st.session_state
defaults = dict(photos=[], uploader_epoch=0, output=None, project_payload=None,
                revision=0, output_seconds=None, notice=None, notice_error=False,
                editor_session=uuid.uuid4().hex, editor_seen=[], editor_response=None,
                editor_assets={}, pending_export=None, editor_busy=False,
                ai_cache={}, ai_results={}, ai_reports=[], ai_imports=[], ai_calls=0,
                ai_queue=[], ai_delivered={}, ai_pending={}, overlays=[], png_epoch=0,
                comparisons=[], comparison_overlays=[], template_mode="items", last_template="items",
                photo_upload_epochs={"general":0,"before":0,"after":0},cover=new_cover(),
                music=new_music(),music_asset=None,music_epoch=0,
                project_archive=None,project_import_epoch=0,video_width=1080,edit_mode="full")
from studio.tour import new_tour
defaults.update(tour=new_tour(),floor_plan=None,video_assets={})
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value
prior_cover_duration=0 if cover_added else st.session_state.get('cover_duration', .5 if st.session_state.get('cover_version')==1 else DURATION)
if prior_cover_duration!=DURATION and st.session_state.photos and st.session_state.cover['enabled']:
    for slot in (st.session_state.overlays,st.session_state.comparison_overlays):
        for overlay in slot:overlay['start']=max(0,overlay['start']+DURATION-prior_cover_duration)
st.session_state.cover_duration=DURATION
if st.session_state.get('cover_version')!=4:
    st.session_state.cover_version=4;st.session_state.project_payload=None
    st.session_state.editor_assets={}
if st.session_state.get('music_version')!=1:
    st.session_state.music_version=1;st.session_state.project_payload=None
if st.session_state.get('body_title_version')!=5:
    from studio.body import new_body, upgrade_body
    st.session_state.cover.setdefault('body',new_body())
    upgrade_body(st.session_state.cover['body'])
    st.session_state.body_title_version=5;st.session_state.project_payload=None
if "overlay_assets" not in st.session_state:
    st.session_state.overlay_assets, st.session_state.asset_warnings = discover_assets()
if st.session_state.get("photo_preview_version") != 1:
    st.session_state.photo_preview_version = 1
    st.session_state.project_payload = None
    st.session_state.editor_assets = {}

# 升級元件協定時保留照片，只清除舊版素材 payload 與舊 widget 事件。
if st.session_state.get("editor_protocol") != 4:
    st.session_state.editor_protocol = 4
    st.session_state.project_payload = None
    st.session_state.editor_assets = {}
    st.session_state.editor_response = None
    st.session_state.pop("studio_editor", None)

# 新的元件值已在 rerun 前寫入 widget Session State，在回傳元件參數前完成交易。
versioning.refresh(st.session_state)
consume_editor_event(st.session_state, st.session_state.get("studio_editor"))
output_jobs.collect(st.session_state,st.get_option('server.enableStaticServing'),st.get_option('server.baseUrlPath'))
output_ui.operation_status(st.session_state)

# 舊照片與前端草稿各自只升級一次；手動調整過新時間後不再自動延後。
from studio.models import delay_label
timing_changed=False
for item in [*st.session_state.photos,*st.session_state.comparisons]:
    labels,duration=(item['labels'],item['duration']) if isinstance(item,dict) else (item.labels,item.duration)
    for label in labels:
        if delay_label(label,duration):timing_changed=True
if timing_changed:
    st.session_state.project_payload=None;versioning.refresh(st.session_state)


def invalidate():
    st.session_state.project_payload = None
    versioning.refresh(st.session_state)


def workspace_guarded():
    return bool(st.session_state.editor_busy or st.session_state.pending_export is not None
                or st.session_state.get('prepared_output') or st.session_state.get('guard_request'))


def clear_workspace():
    """僅在資料保護流程核准後清空；取消確認不會呼叫。"""
    state=st.session_state
    output_jobs.release(state)
    versioning.reset_versions(state)
    state.update(photos=[],editor_session=uuid.uuid4().hex,editor_assets={},editor_response=None,
                 editor_seen=[],pending_export=None,editor_busy=False,output=None,output_seconds=None,
                 project_archive=None,overlays=[],comparisons=[],comparison_overlays=[],cover=new_cover(),
                 music=new_music(),music_asset=None,tour=new_tour(),floor_plan=None,video_assets={})
    for key in ('tour_plan_receipt','tour_video_receipts'):state.pop(key,None)
    for key in ('tour_video_epoch','tour_plan_epoch'):state[key]=state.get(key,0)+1
    for key in ('_quick_original','_quick_frames','_quick_preview_error'):state.pop(key,None)
    state.overlay_assets,state.asset_warnings=discover_assets()
    for key in ('music_epoch','png_epoch','uploader_epoch'):state[key]+=1
    state.photo_upload_epochs={role:epoch+1 for role,epoch in state.photo_upload_epochs.items()}
    for key,value in dict(ai_cache={},ai_results={},ai_reports=[],ai_imports=[],ai_calls=0,
                          ai_queue=[],ai_delivered={},ai_pending={}).items():state[key]=value
    for key in ('ai_chosen','ai_consent','ai_force','ai_refresh_requested','render_job','project_save_job','studio_editor','replacement_request','photo_receipts'):state.pop(key,None)
    invalidate()


approved=st.session_state.pop('guard_approved',None)
if approved:
    if approved=='logout':
        output_jobs.release(st.session_state);logout()
    elif approved=='clear':clear_workspace()
    elif approved=='import':
        from studio.project_io import install_project
        project=st.session_state.pop('guard_import_project')
        install_project(st.session_state,project)
        st.session_state.notice=f"已開啟專案，含{len(project['photos'])}張照片，可繼續編輯及輸出。"
        st.session_state.notice_error=False
    st.rerun()


def optimization_notice(photos, previous):
    original = {p.id: p.original for p in previous}
    return " ".join(f"{p.name}：{p.optimization_note}" for p in photos
                    if p.optimization_note and p.original is not original.get(p.id))


def add_uploaded(uploaded, role="general"):
    state=st.session_state
    event_id=batch_id(state.editor_session,role,state.photo_upload_epochs[role],uploaded)
    previous=state.photos
    result=append_photos(state,uploaded,role,event_id)
    if result['replayed']:return False
    note=optimization_notice(state.photos,previous)
    st.session_state.photo_upload_epochs[role]+=1
    state.notice=f"已加入 {len(result['added'])} 張，未加入 {len(result['errors'])} 張。 "+note
    if result['errors']:state.notice+='\n\n'+'\n\n'.join(result['errors'])
    state.notice_error=bool(result['errors'])
    return True


prepare_download(st.session_state)

with st.sidebar:
    st.markdown("### 案例影片工作室")
    if st.button("登出",use_container_width=True,disabled=workspace_guarded()):
        protection.request(st.session_state,'logout');st.rerun()
    st.caption("登出會清除目前工作階段，請先下載影片或專案檔。")
    st.radio("操作模式",["full","quick"],format_func=lambda mode:"完整編輯" if mode=="full" else "快速修改標題",key="edit_mode",horizontal=True,disabled=bool(st.session_state.get("guard_request")))
    if st.session_state.edit_mode!="quick":import_panel(st.session_state)
    protection.panel(st.session_state)
    st.caption("第六階段 · 快速修改標題")
    st.markdown("照片 → 標籤 → 預覽 → MP4")
    st.divider()
    if st.session_state.edit_mode!="quick":
        st.selectbox("影片模板", ["items","compare","tour"], key="template_mode",
                     format_func=lambda key:template_config(key)["name"],
                     disabled=workspace_guarded())
        if st.session_state.last_template!=st.session_state.template_mode:
            st.session_state.last_template=st.session_state.template_mode;invalidate()
        st.caption("可切換裝修介紹或前後對比；各模板保留自己的片段、標籤與 PNG 草稿。")
    with st.expander("執行環境檢查", expanded=False):
        try:
            info = capabilities()
            st.success("FFmpeg / libx264 可用")
            st.caption(Path(info["binary"]).name)
        except (RuntimeError, OSError) as exc:
            st.error(str(exc))
        try:
            st.success("中文字型可用") if font_path() else None
        except RuntimeError as exc:
            st.error(str(exc))
        st.caption("此處只確認目前執行環境，Cloud 部署後仍需重新驗證。")
    st.divider()
    st.caption("照片僅存在目前工作階段記憶體，請儲存專案檔以便下次編輯。使用雲端時，照片會傳至 Streamlit 伺服器。")
    if st.button("清空目前工作階段", use_container_width=True,disabled=workspace_guarded()):
        protection.request(st.session_state,'clear');st.rerun()

quick_mode=st.session_state.edit_mode=="quick"
if quick_mode:
    st.title("快速修改標題")
    st.caption("匯入ZIP → 修改一次影片標題 → 分別檢查封面與正文 → 輸出MP4與ZIP。")
    import_panel(st.session_state,expanded=True)
else:
    st.markdown('<div class="eyebrow">INTERIOR FILM STUDIO</div>', unsafe_allow_html=True)
    st.title("讓每個空間，說出它的設計。")
    st.markdown('<div class="intro">上傳案例照片，放上裝修重點，製作一支直式案例影片。</div>', unsafe_allow_html=True)
    st.markdown('<div class="workflow">01　上傳照片　　→　　02　拖曳與編輯標籤　　→　　03　預覽並下載影片</div>', unsafe_allow_html=True)

if st.session_state.notice:
    if st.session_state.notice_error:
        st.error(st.session_state.notice)
    else:
        st.success(st.session_state.notice)
    st.session_state.notice = None
    st.session_state.notice_error = False

workspace_locked=workspace_guarded()
compare_mode=st.session_state.template_mode=="compare"
if not quick_mode:
    st.subheader("01　準備案例照片")
    compare_mode=st.session_state.template_mode=="compare"
    workspace_locked=workspace_guarded()
    sources=[("before","施工前照片（可一次多張）"),("after","施工後照片（可一次多張）")] if compare_mode else [("general","加入照片（可一次多張）")]
    columns=st.columns([3]*len(sources)+[1])
    for col,(role,title) in zip(columns,sources):
        with col:
            uploaded=st.file_uploader(title,type=["jpg","jpeg","png","webp"],accept_multiple_files=True,
                                     max_upload_size=200,key=f"uploads_{role}_{st.session_state.photo_upload_epochs[role]}",disabled=workspace_locked)
            st.caption("選檔後自動追加；再次選擇同一張照片也可加入。大照片自動等比例最佳化。")
            if uploaded and not workspace_locked:
                with st.spinner("正在準備照片；大照片會自動最佳化…"):added=add_uploaded(uploaded,role)
                if added:st.rerun()
    with columns[-1]:
        st.caption("想先試操作？")
        if st.button("載入前後對比測試圖" if compare_mode else "載入 5 張測試示意圖", use_container_width=True, disabled=bool(st.session_state.photos) or workspace_locked):
            from scripts.verify_export import samples
            demo=samples()[:4] if compare_mode else samples()
            if compare_mode:
                for i,p in enumerate(demo):p.role="before" if i<2 else "after"
            st.session_state.photos=demo
            invalidate()
            st.session_state.notice = "已載入自行繪製的室內空間示意圖，供測試操作與輸出；並非真實案例或 AI 辨識。"
            st.rerun()
        st.caption("最多 12 張 · 大照片自動最佳化\n\nJPG / PNG / WEBP")

photos = st.session_state.photos
from studio.tour_ui import panel as tour_panel
if not quick_mode:tour_panel(st.session_state,workspace_locked)
if not photos and not st.session_state.video_assets and not st.session_state.floor_plan:
    st.info("請在上方匯入ZIP專案。" if quick_mode else "先加入案例照片、載入測試示意圖，或從左側匯入專案檔，即可開始編輯。")
    st.stop()

def dismiss_replacement():
    st.session_state.pop('replacement_request',None)


@st.dialog('替換目前選取的照片',on_dismiss=dismiss_replacement)
def replacement_dialog(request):
    target=next((p for p in photos if p.id==request['photo_id']),None)
    if target is None:
        st.warning('照片已不存在，請關閉視窗重新選取。');return
    st.caption(f'目前照片：{target.name}。選檔後直接替換；保留順序、時長、標籤、構圖與配對引用。')
    st.caption('新圖構圖可能不同，請檢查裁切與定位點；AI標籤會標記待確認，不會移動人工定位。')
    replacement=st.file_uploader('選擇替換照片',type=['jpg','jpeg','png','webp'],max_upload_size=200,
                                 key=f"replacement_{request['id']}",disabled=workspace_locked)
    if replacement is not None and not workspace_locked:
        try:
            ident=batch_id(st.session_state.editor_session,'replace:'+target.id,request['id'],[replacement])
            replace_photo(st.session_state,target.id,replacement,ident)
            dismiss_replacement()
            st.session_state.notice='已替換照片；請確認裁切、標籤與定位點。未套用的編輯仍保留。'
            st.rerun()
        except (ValueError, OSError, MemoryError) as exc:
            st.error(str(exc) or '無法替換，原照片與設定已保留。')
    if st.button('取消替換'):
        dismiss_replacement();st.rerun()


if not quick_mode and st.session_state.get('replacement_request') and not workspace_locked:
    replacement_dialog(st.session_state.replacement_request)

if not quick_mode:
    with st.expander("上傳 PNG 素材（透明 LOGO、箭頭、價格框）", expanded=False):
        st.caption("素材僅保存在目前工作階段；單張最多5 MB／800萬畫素。上傳後到編輯器的 PNG 素材庫點選加入。請使用有權使用的素材。")
        png_files = st.file_uploader("選擇 PNG 素材", type=["png"], accept_multiple_files=True,
                                     max_upload_size=5, key=f"png_uploads_{st.session_state.png_epoch}")
        if st.button("加入 PNG 素材庫", disabled=not png_files or workspace_locked):
            try:
                proposed = dict(st.session_state.overlay_assets)
                for file in png_files:
                    asset = load_asset(file.name, file.getvalue())
                    proposed[asset.id] = asset
                if len(proposed) > MAX_ASSETS or sum(len(asset.original) for asset in proposed.values()) > 40*1024*1024:
                    raise ValueError("素材庫最多24個 PNG、總容量40 MB，請減少素材或縮小圖片。")
                st.session_state.overlay_assets = proposed
                st.session_state.png_epoch += 1
                invalidate()
                st.rerun()
            except (ValueError, OSError) as exc:
                st.error(str(exc))
        for warning in st.session_state.get("asset_warnings", []):
            st.warning(warning)

    with st.expander('背景音樂 BGM（預設1秒淡出）', expanded=False):
        st.caption(f'請上傳有權使用的音樂；只保存在目前工作階段。單檔最多{MAX_MUSIC_UPLOAD_MB} MB，較長音樂自動截取前120秒。音量與淡出在下方編輯器設定。')
        music_file=st.file_uploader('選擇BGM',type=['mp3','wav','m4a','ogg','flac'],max_upload_size=MAX_MUSIC_UPLOAD_MB,
                                  key=f'music_upload_{st.session_state.music_epoch}')
        add_music,remove_music=st.columns(2)
        music_locked=st.session_state.editor_busy or st.session_state.pending_export is not None or bool(st.session_state.get('guard_request'))
        if add_music.button('加入／替換BGM',disabled=not music_file or music_locked):
            try:
                with st.spinner('正在處理音樂…'):asset=load_music(music_file.name,music_file.getvalue())
                st.session_state.music_asset=asset;st.session_state.music={**st.session_state.music,'source':asset.id}
                st.session_state.music_epoch+=1;invalidate();st.rerun()
            except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
        if remove_music.button('移除BGM',disabled=st.session_state.music_asset is None or music_locked):
            st.session_state.music_asset=None;st.session_state.music={**st.session_state.music,'source':None}
            st.session_state.music_epoch+=1;invalidate();st.rerun()
        if st.session_state.music_asset:
            asset=st.session_state.music_asset
            st.caption(f'目前：{asset.name} · {asset.duration:.1f}秒'+('（已取前120秒）' if asset.truncated else ''))

    st.subheader("02　編輯畫面、PNG 與時間軸")
    ai_panel(photos, st.session_state)
else:
    st.subheader("02　修改標題與檢查排版")
    if st.session_state.get('_quick_original') is None:
        from studio.quick_preview import capture
        capture(st.session_state)
st.caption("草稿先暫存在目前分頁；下載ZIP或輸出影片會自動準備，無須先套用。工作階段重啟會失去伺服器素材，請用ZIP備份。")
try:
    if st.session_state.project_payload is None:
        st.session_state.project_payload = payload(photos, cache=st.session_state.editor_assets,
                 assets=st.session_state.overlay_assets, overlays=st.session_state.overlays,
                 comparisons=st.session_state.comparisons, template=st.session_state.template_mode,
                 comparison_overlays=st.session_state.comparison_overlays, cover=st.session_state.cover,
                 music=st.session_state.music, music_asset=st.session_state.music_asset,tour=st.session_state.tour,
                 floor_plan=st.session_state.floor_plan,videos=st.session_state.video_assets)
    from studio.photo_history import preview as undo_preview
    request = st.session_state.pending_export
    from studio.quick_preview import scenes as original_scenes
    editor(project=st.session_state.project_payload, session=st.session_state.editor_session,
           ui_mode=st.session_state.edit_mode,quick_frames=st.session_state.get('_quick_frames',{}) if quick_mode else {},
           quick_scenes=original_scenes(st.session_state['_quick_original']) if quick_mode and st.session_state.get('_quick_original') else [],
           quick_error=st.session_state.get('_quick_preview_error') if quick_mode else None,
           response=st.session_state.editor_response, revision=st.session_state.revision,
           export_request=request["id"] if request else None, busy=st.session_state.editor_busy,
           ai_imports=st.session_state.ai_imports,undo_photo=undo_preview(st.session_state),
           versions=versioning.status(st.session_state),guard_request=st.session_state.get('guard_request'),
           output_status=st.session_state.get('output_status'),zip_delivery=delivery(st.session_state.get('project_archive'),st.session_state.get('zip_download_request_id')),
           mp4_delivery=delivery(st.session_state.get('mp4_download'),st.session_state.get('mp4_download_request_id')),
           key="studio_editor", default=None)
except (RuntimeError, OSError) as exc:
    st.error(str(exc))
    st.stop()

st.subheader("03　輸出案例影片")
st.caption("按一次即可固定當下最新草稿並自動準備；處理期間可繼續編輯，新的修改不會混入本次成果。")
options, summary = st.columns([2, 3])
with options:
    size = st.selectbox("影片解析度", [1080, 720, 360],
                        format_func=lambda w: f"{w} × {w*16//9}" + (" · Full HD" if w == 1080 else " · 較快輸出"),key='video_width',disabled=workspace_locked)
    output_ui.actions(session=st.session_state.editor_session,width=size,
                      locked=bool(st.session_state.get('guard_request')),key='output_actions',default=None)
with summary:
    st.markdown(f"**{len(photos)} 張來源照片 · 9:16**")
    st.caption("影片長度以編輯器時間軸為準；輸出前自動套用最新變更。")
    st.caption("免費本機／伺服器渲染。照片不寫入永久目錄；產生的壓縮影片暫存檔會在完成或失敗後清除。")

output_ui.progress_panel(st.session_state)
download_panel(st.session_state)

job = st.session_state.pop("render_job", None)
if job:
    started = time.monotonic()
    bar = st.progress(0., text="正在準備影片素材…")
    try:
        if job['content_version']!=versioning.project_version(st.session_state,width=job['width']):
            raise ValueError('輸出請求後專案內容已變更，請重新輸出；上一個成功影片仍保留。')
        data = export_video(photos, job["width"], job["width"]*16//9,
                            progress=lambda value, message: bar.progress(value, text=message),
                            overlays=st.session_state.comparison_overlays if compare_mode else st.session_state.overlays,
                            assets=st.session_state.overlay_assets,template=st.session_state.template_mode,
                            comparisons=st.session_state.comparisons,cover=st.session_state.cover,
                            music=st.session_state.music,music_asset=st.session_state.music_asset)
        versioning.complete_export(st.session_state,data,round(time.monotonic()-started,1),job['content_version'])
    except (RuntimeError, ValueError, OSError, TimeoutError,MemoryError) as exc:
        bar.empty()
        st.session_state.notice = f"影片未完成：{exc}。可選擇 720p 或減少照片重試。"
        st.session_state.notice_error = True
    finally:
        st.session_state.editor_busy = False
    st.rerun()

if st.session_state.output:
    version=st.session_state.get('mp4_version')
    st.success(f"最近成功影片已保留，輸出耗時 {st.session_state.output_seconds} 秒。")
    st.caption(f"MP4版本：{version[4:16] if version else '來源版本未知'}。是否包含最新修改，請看編輯器即時狀態。")
    if version!=st.session_state.content_version:st.warning('這是較舊或來源版本未知的MP4，不包含目前所有修改；重新輸出成功後才會替換。')
    download, preview = st.columns([1, 2])
    with download:
        st.download_button("下載 MP4 影片", data=st.session_state.output, file_name=(st.session_state.get("mp4_download") or {}).get("filename",f"室內設計案例_{version[4:16] if version else '來源版本未知'}.mp4"),
                           mime="video/mp4", type="primary", use_container_width=True, on_click="ignore")
        st.caption(f"檔案大小 {len(st.session_state.output)/1024/1024:.2f} MB")
        if (st.session_state.get('mp4_download') or {}).get('download_warning'):st.info(st.session_state.mp4_download['download_warning'])
    with preview:
        st.video(st.session_state.output)
