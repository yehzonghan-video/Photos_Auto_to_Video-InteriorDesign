"""室內案例影片：前端草稿編輯與選用的 Gemini 辨識；無持久化照片。"""
from pathlib import Path
import time
import uuid

import streamlit as st

from studio.bootstrap import video_modules
from studio.models import MAX_PHOTOS, load_photo
from studio.rendering import font_path, template_config
from studio.ai_ui import ai_panel
from studio.overlays import discover_assets, load_asset, MAX_ASSETS
from studio.photo_processing import fit_session
from studio.access import require_password, logout
from studio.cover import new_cover, DURATION
from studio.music import new_music, load_music

st.set_page_config(page_title="室內案例影片工作室", page_icon="◩", layout="wide")
require_password()
try:
    component_api, export_api, sync_api = video_modules()
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
                music=new_music(),music_asset=None,music_epoch=0)
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value
prior_cover_duration=0 if cover_added else st.session_state.get('cover_duration', .5 if st.session_state.get('cover_version')==1 else DURATION)
if prior_cover_duration!=DURATION and st.session_state.photos and st.session_state.cover['enabled']:
    for slot in (st.session_state.overlays,st.session_state.comparison_overlays):
        for overlay in slot:overlay['start']=max(0,overlay['start']+DURATION-prior_cover_duration)
st.session_state.cover_duration=DURATION
if st.session_state.get('cover_version')!=2:
    st.session_state.cover_version=2;st.session_state.project_payload=None
    st.session_state.editor_assets={};st.session_state.output=None
if st.session_state.get('music_version')!=1:
    st.session_state.music_version=1;st.session_state.project_payload=None
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
consume_editor_event(st.session_state, st.session_state.get("studio_editor"))


def invalidate():
    st.session_state.output = None
    st.session_state.output_seconds = None
    st.session_state.project_payload = None
    st.session_state.revision += 1


def check_capacity(photos):
    if len(photos) > MAX_PHOTOS:
        raise ValueError("每個工作階段最多 12 張照片。")
    return fit_session(photos)


def optimization_notice(photos, previous):
    original = {p.id: p.original for p in previous}
    return " ".join(f"{p.name}：{p.optimization_note}" for p in photos
                    if p.optimization_note and p.original is not original.get(p.id))


def add_uploaded(uploaded, role="general"):
    if len(st.session_state.photos)+len(uploaded)>MAX_PHOTOS:
        raise ValueError("每個工作階段最多12張來源照片；配對可重複使用同一張。")
    new=[load_photo(item.name,item.getvalue()) for item in uploaded]
    for photo in new:photo.role=role
    proposed=check_capacity(st.session_state.photos+new)
    if sum(p.duration for p in proposed)>120:
        raise ValueError("照片總長最多120秒，請先縮短現有照片秒數。")
    note=optimization_notice(proposed,st.session_state.photos)
    st.session_state.photos=proposed;st.session_state.uploader_epoch+=1
    st.session_state.photo_upload_epochs[role]+=1
    invalidate();st.session_state.notice=f"已加入 {len(new)} 張照片。 "+note


with st.sidebar:
    st.markdown("### 案例影片工作室")
    st.button("登出", on_click=logout, use_container_width=True)
    st.caption("登出會清除目前工作階段的照片與影片，請先下載成果。")
    st.caption("第四階段 · 裝修前後對比")
    st.markdown("照片 → 標籤 → 預覽 → MP4")
    st.divider()
    st.selectbox("影片模板", ["items","compare"], key="template_mode",
                 format_func=lambda key:template_config(key)["name"],
                 disabled=st.session_state.editor_busy or st.session_state.pending_export is not None)
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
    st.caption("照片僅存在目前工作階段記憶體，重新整理可能遺失。使用雲端時，照片會傳至 Streamlit 伺服器。")
    if st.button("清空目前工作階段", use_container_width=True):
        st.session_state.photos = []
        st.session_state.editor_session = uuid.uuid4().hex
        st.session_state.editor_assets = {}
        st.session_state.editor_response = None
        st.session_state.pending_export = None
        st.session_state.editor_busy = False
        st.session_state.overlays = []
        st.session_state.comparisons=[];st.session_state.comparison_overlays=[]
        st.session_state.cover=new_cover()
        st.session_state.music=new_music();st.session_state.music_asset=None;st.session_state.music_epoch+=1
        st.session_state.overlay_assets, st.session_state.asset_warnings = discover_assets()
        st.session_state.png_epoch += 1
        for key, value in dict(ai_cache={}, ai_results={}, ai_reports=[], ai_imports=[], ai_calls=0,
                               ai_queue=[], ai_delivered={}, ai_pending={}).items():
            st.session_state[key] = value
        st.session_state.pop("ai_chosen", None)
        st.session_state.pop("ai_consent", None)
        st.session_state.pop("render_job", None)
        st.session_state.uploader_epoch += 1
        st.session_state.photo_upload_epochs={role:epoch+1 for role,epoch in st.session_state.photo_upload_epochs.items()}
        invalidate()
        st.rerun()

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

st.subheader("01　準備案例照片")
compare_mode=st.session_state.template_mode=="compare"
sources=[("before","施工前照片（可一次多張）","加入施工前照片"),("after","施工後照片（可一次多張）","加入施工後照片")] if compare_mode else [("general","加入照片（可一次多張）","加入已選照片")]
columns=st.columns([3]*len(sources)+[1])
for col,(role,title,button_name) in zip(columns,sources):
    with col:
        uploaded=st.file_uploader(title,type=["jpg","jpeg","png","webp"],accept_multiple_files=True,
                                 max_upload_size=200,key=f"uploads_{role}_{st.session_state.photo_upload_epochs[role]}")
        st.caption("一般照片保留原檔；大照片或整批負荷較高時自動等比例最佳化。")
        if st.button(button_name,disabled=not uploaded,type="primary"):
            try:
                with st.spinner("正在準備照片；大照片會自動最佳化…"):add_uploaded(uploaded,role)
                st.rerun()
            except (ValueError,OSError,MemoryError) as exc:
                st.error(str(exc) or "記憶體不足，請稍後重試。")
with columns[-1]:
    st.caption("想先試操作？")
    if st.button("載入前後對比測試圖" if compare_mode else "載入 5 張測試示意圖", use_container_width=True, disabled=bool(st.session_state.photos)):
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
if not photos:
    st.info("先加入案例照片，或載入測試示意圖，即可開始編輯。")
    st.stop()

with st.expander("替換單張照片", expanded=False):
    target_id = st.selectbox("要替換的照片", [p.id for p in photos],
                            format_func=lambda ident: next(f"{i+1} · {p.name}" for i,p in enumerate(photos) if p.id == ident))
    replacement = st.file_uploader("選擇替換照片", type=["jpg", "jpeg", "png", "webp"], max_upload_size=200,
                                   key=f"replacement_{st.session_state.uploader_epoch}")
    st.caption("替換後保留此張照片的標籤與構圖設定，請重新確認定位點。")
    if st.button("套用替換照片", disabled=replacement is None):
        try:
            fresh = load_photo(replacement.name, replacement.getvalue())
            target = next(p for p in photos if p.id == target_id)
            fresh.id = target.id
            fresh.duration, fresh.zoom, fresh.crop_x, fresh.crop_y = target.duration, target.zoom, target.crop_x, target.crop_y
            fresh.fit = getattr(target, "fit", "contain")
            fresh.role=target.role
            fresh.labels = target.labels
            proposed = [fresh if p.id == target_id else p for p in photos]
            proposed = check_capacity(proposed)
            note = optimization_notice(proposed, photos)
            st.session_state.photos = proposed
            st.session_state.uploader_epoch += 1
            invalidate()
            st.session_state.notice = "已替換照片。 " + note
            st.rerun()
        except (ValueError, OSError, MemoryError) as exc:
            st.error(str(exc) or "記憶體不足，無法完成此照片的自動最佳化，請稍後重試。")

with st.expander("上傳 PNG 素材（透明 LOGO、箭頭、價格框）", expanded=False):
    st.caption("素材僅保存在目前工作階段；單張最多5 MB／800萬畫素。上傳後到編輯器的 PNG 素材庫點選加入。請使用有權使用的素材。")
    png_files = st.file_uploader("選擇 PNG 素材", type=["png"], accept_multiple_files=True,
                                 max_upload_size=5, key=f"png_uploads_{st.session_state.png_epoch}")
    if st.button("加入 PNG 素材庫", disabled=not png_files):
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
    st.caption('請上傳有權使用的音樂；只保存在目前工作階段。單檔20 MB，最長保留前120秒。音量與淡出在下方編輯器設定。')
    music_file=st.file_uploader('選擇BGM',type=['mp3','wav','m4a','ogg','flac'],max_upload_size=20,
                              key=f'music_upload_{st.session_state.music_epoch}')
    add_music,remove_music=st.columns(2)
    music_locked=st.session_state.editor_busy or st.session_state.pending_export is not None
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
st.caption("所有編輯先保留在此頁，切換照片不會遺失。完成後按「套用變更」；輸出前會自動套用最新設定。")
try:
    if st.session_state.project_payload is None:
        st.session_state.project_payload = payload(photos, cache=st.session_state.editor_assets,
                 assets=st.session_state.overlay_assets, overlays=st.session_state.overlays,
                 comparisons=st.session_state.comparisons, template=st.session_state.template_mode,
                 comparison_overlays=st.session_state.comparison_overlays, cover=st.session_state.cover,
                 music=st.session_state.music, music_asset=st.session_state.music_asset)
    request = st.session_state.pending_export
    editor(project=st.session_state.project_payload, session=st.session_state.editor_session,
           response=st.session_state.editor_response, revision=st.session_state.revision,
           export_request=request["id"] if request else None, busy=st.session_state.editor_busy,
           ai_imports=st.session_state.ai_imports,
           key="studio_editor", default=None)
except (RuntimeError, OSError) as exc:
    st.error(str(exc))
    st.stop()

st.subheader("03　輸出案例影片")
st.caption("按輸出後會先套用此頁的最新編輯，再以固定 30 FPS 生成 H.264 MP4。")
options, summary = st.columns([2, 3])
with options:
    size = st.selectbox("影片解析度", [1080, 720, 360],
                        format_func=lambda w: f"{w} × {w*16//9}" + (" · Full HD" if w == 1080 else " · 較快輸出"))
    render_clicked = st.button("輸出 H.264 MP4", type="primary", use_container_width=True,
                               disabled=st.session_state.editor_busy or st.session_state.pending_export is not None)
with summary:
    st.markdown(f"**{len(photos)} 張來源照片 · 9:16**")
    st.caption("影片長度以編輯器時間軸為準；輸出前自動套用最新變更。")
    st.caption("免費本機／伺服器渲染。照片不寫入永久目錄；產生的壓縮影片暫存檔會在完成或失敗後清除。")

if render_clicked:
    st.session_state.pending_export = dict(id=uuid.uuid4().hex, width=size)
    st.rerun()

job = st.session_state.pop("render_job", None)
if job:
    st.session_state.output = None
    started = time.monotonic()
    bar = st.progress(0., text="正在準備影片素材…")
    try:
        data = export_video(photos, job["width"], job["width"]*16//9,
                            progress=lambda value, message: bar.progress(value, text=message),
                            overlays=st.session_state.comparison_overlays if compare_mode else st.session_state.overlays,
                            assets=st.session_state.overlay_assets,template=st.session_state.template_mode,
                            comparisons=st.session_state.comparisons,cover=st.session_state.cover,
                            music=st.session_state.music,music_asset=st.session_state.music_asset)
        st.session_state.output = data
        st.session_state.output_seconds = round(time.monotonic() - started, 1)
    except (RuntimeError, ValueError, OSError, TimeoutError) as exc:
        bar.empty()
        st.session_state.notice = f"影片未完成：{exc}。可選擇 720p 或減少照片重試。"
        st.session_state.notice_error = True
    finally:
        st.session_state.editor_busy = False
    st.rerun()

if st.session_state.output:
    st.success(f"影片已完成，輸出耗時 {st.session_state.output_seconds} 秒。")
    download, preview = st.columns([1, 2])
    with download:
        st.download_button("下載 MP4 影片", data=st.session_state.output, file_name="室內設計案例.mp4",
                           mime="video/mp4", type="primary", use_container_width=True, on_click="ignore")
        st.caption(f"檔案大小 {len(st.session_state.output)/1024/1024:.2f} MB")
    with preview:
        st.video(st.session_state.output)
