"""第一階段：手動編輯可操作的案例影片；無登入、無持久化照片。"""
from pathlib import Path
import time

import streamlit as st

from studio.component import editor, payload
from studio.export import capabilities, export_video
from studio.models import MAX_PHOTOS, MAX_SESSION_BYTES, load_photo, update_project
from studio.rendering import font_path, template_config

st.set_page_config(page_title="室內案例影片工作室", page_icon="◩", layout="wide")
st.markdown("""<style>
.block-container{max-width:1280px;padding-top:2rem;padding-bottom:2rem}
h1{font-size:2rem!important;letter-spacing:.025em}h2{font-size:1.3rem!important}
[data-testid="stMetricValue"]{font-size:1.6rem}
[data-testid="stSidebar"]{border-right:1px solid #ddd7ce}
.eyebrow{font-size:12px;letter-spacing:.2em;color:#a16e44;font-weight:600;margin-bottom:5px}
.intro{color:#73786c;font-size:15px;margin-bottom:22px}
.workflow{font-size:13px;padding:13px 18px;border:1px solid #ded8cb;border-radius:9px;margin:16px 0 20px;color:#58694e;background:#f0ece3}
</style>""", unsafe_allow_html=True)

defaults = dict(photos=[], uploader_epoch=0, ack=None, output=None, project_payload=None,
                revision=0, output_seconds=None, notice=None, notice_error=False)
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


def invalidate():
    st.session_state.output = None
    st.session_state.output_seconds = None
    st.session_state.project_payload = None
    st.session_state.revision += 1


def check_capacity(photos):
    if len(photos) > MAX_PHOTOS:
        raise ValueError("每個工作階段最多 12 張照片。")
    if sum(len(p.original) for p in photos) > MAX_SESSION_BYTES:
        raise ValueError("照片總容量不可超過 80 MB，請減少照片或縮小檔案。")
    if sum(p.width * p.height for p in photos) > 60_000_000:
        raise ValueError("照片總畫素不可超過 6000 萬，請減少照片或縮小尺寸。")


with st.sidebar:
    st.markdown("### 案例影片工作室")
    st.caption("第一階段 · 手動編輯 MVP")
    st.markdown("照片 → 標籤 → 預覽 → MP4")
    st.divider()
    config = template_config()
    st.selectbox("影片模板", [config["name"]])
    st.caption("AI 分析、其他模板、音樂與 LOGO 將在後續階段加入。")
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
        st.session_state.ack = None
        st.session_state.uploader_epoch += 1
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
upload_col, demo_col = st.columns([3, 1])
with upload_col:
    uploaded = st.file_uploader("加入照片（可一次多張）", type=["jpg", "jpeg", "png", "webp"],
                                accept_multiple_files=True, key=f"uploads_{st.session_state.uploader_epoch}")
    if st.button("加入已選照片", disabled=not uploaded, type="primary"):
        try:
            new = [load_photo(item.name, item.getvalue()) for item in uploaded]
            proposed = st.session_state.photos + new
            check_capacity(proposed)
            if sum(p.duration for p in proposed) > 120:
                raise ValueError("影片總長最多 120 秒，請先縮短現有照片秒數。")
            st.session_state.photos = proposed
            st.session_state.uploader_epoch += 1
            invalidate()
            st.session_state.notice = f"已加入 {len(new)} 張照片。"
            st.rerun()
        except (ValueError, OSError) as exc:
            st.error(str(exc))
with demo_col:
    st.caption("想先試操作？")
    if st.button("載入 5 張測試示意圖", use_container_width=True, disabled=bool(st.session_state.photos)):
        from scripts.verify_export import samples
        st.session_state.photos = samples()
        invalidate()
        st.session_state.notice = "已載入自行繪製的室內空間示意圖，供測試操作與輸出；並非真實案例或 AI 辨識。"
        st.rerun()
    st.caption("最多 12 張 · 每張 15 MB\n\nJPG / PNG / WEBP")

photos = st.session_state.photos
if not photos:
    st.info("先加入案例照片，或載入測試示意圖，即可開始編輯。")
    st.stop()

with st.expander("替換單張照片", expanded=False):
    target_id = st.selectbox("要替換的照片", [p.id for p in photos],
                            format_func=lambda ident: next(f"{i+1} · {p.name}" for i,p in enumerate(photos) if p.id == ident))
    replacement = st.file_uploader("選擇替換照片", type=["jpg", "jpeg", "png", "webp"], key=f"replacement_{st.session_state.uploader_epoch}")
    st.caption("保留此張照片的標籤、秒數與裁切設定；替換後請確認定位點與構圖。")
    if st.button("套用替換照片", disabled=replacement is None):
        try:
            fresh = load_photo(replacement.name, replacement.getvalue())
            target = next(p for p in photos if p.id == target_id)
            fresh.id = target.id
            fresh.duration, fresh.zoom, fresh.crop_x, fresh.crop_y = target.duration, target.zoom, target.crop_x, target.crop_y
            fresh.labels = target.labels
            proposed = [fresh if p.id == target_id else p for p in photos]
            check_capacity(proposed)
            st.session_state.photos = proposed
            st.session_state.uploader_epoch += 1
            invalidate()
            st.rerun()
        except (ValueError, OSError) as exc:
            st.error(str(exc))

st.subheader("02　編輯畫面與裝修標籤")
st.caption("點選縮圖切換照片。標籤與圓點可分開拖曳，進階設定可收合。")
try:
    if st.session_state.project_payload is None:
        st.session_state.project_payload = payload(photos)
    event = editor(project=st.session_state.project_payload, ack=st.session_state.ack,
                   revision=st.session_state.revision, key="studio_editor", default=None)
    if isinstance(event, dict) and event.get("nonce") and event["nonce"] != st.session_state.ack:
        st.session_state.ack = event["nonce"]
        try:
            if event.get("action") not in ("update", "delete_photo"):
                raise ValueError("此編輯操作不受支援。")
            updated = update_project(photos, event["photos"])
            if event["action"] == "delete_photo":
                updated = [p for p in updated if p.id != event.get("target")]
            st.session_state.photos = updated
            invalidate()
        except (ValueError, KeyError, TypeError) as exc:
            st.session_state.notice = "編輯未套用：" + str(exc)
            st.session_state.notice_error = True
        st.rerun()
except (RuntimeError, OSError) as exc:
    st.error(str(exc))
    st.stop()

st.subheader("03　輸出案例影片")
st.caption("先確認編輯器顯示「已同步」。可優先使用上方瀏覽器 MP4；下方 FFmpeg 提供固定 30 FPS 的 H.264 輸出。")
options, summary = st.columns([2, 3])
with options:
    size = st.selectbox("影片解析度", [1080, 720, 360],
                        format_func=lambda w: f"{w} × {w*16//9}" + (" · Full HD" if w == 1080 else " · 較快輸出"))
    render_clicked = st.button("輸出 H.264 MP4", type="primary", use_container_width=True)
with summary:
    st.markdown(f"**{len(photos)} 張照片 · {sum(p.duration for p in photos):.1f} 秒 · 9:16**")
    st.caption("免費本機／伺服器渲染。照片不寫入永久目錄；產生的壓縮影片暫存檔會在完成或失敗後清除。")

if render_clicked:
    st.session_state.output = None
    started = time.monotonic()
    bar = st.progress(0., text="正在準備影片素材…")
    try:
        data = export_video(photos, size, size*16//9,
                            progress=lambda value, message: bar.progress(value, text=message))
        st.session_state.output = data
        st.session_state.output_seconds = round(time.monotonic() - started, 1)
    except (RuntimeError, ValueError, OSError, TimeoutError) as exc:
        bar.empty()
        st.error(f"影片未完成：{exc}")
        st.info("可先減少照片或選擇 720p，亦可使用支援 MP4 的瀏覽器本機輸出。")

if st.session_state.output:
    st.success(f"影片已完成，輸出耗時 {st.session_state.output_seconds} 秒。")
    download, preview = st.columns([1, 2])
    with download:
        st.download_button("下載 MP4 影片", data=st.session_state.output, file_name="室內設計案例.mp4",
                           mime="video/mp4", type="primary", use_container_width=True, on_click="ignore")
        st.caption(f"檔案大小 {len(st.session_state.output)/1024/1024:.2f} MB")
    with preview:
        st.video(st.session_state.output)
