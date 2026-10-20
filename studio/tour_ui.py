"""平面圖／MP4入口；成功後交換素材，失敗保留現有專案。"""
from copy import deepcopy
from hashlib import sha256
import streamlit as st
from .tour import load_plan,new_tour
from .tour_video import load_video,MAX_VIDEO_BYTES,MAX_VIDEOS,MAX_VIDEO_TOTAL
from .versioning import refresh
BGM_API_VERSION=10


def media_size(state):
    return (sum(len(p.original) for p in state.get('photos',[]))+sum(len(a.original) for a in state.get('overlay_assets',{}).values())+
            sum(len(v.data) for v in state.get('video_assets',{}).values())+len(state['floor_plan'].original if state.get('floor_plan') else b'')+
            len(state['music_asset'].data if state.get('music_asset') else b''))


def changed(state):state['project_payload']=None;refresh(state)


def panel(state,locked):
    if state['template_mode']!='tour':return
    with st.expander('空間導覽：平面圖與MP4素材',expanded=True):
        st.caption('平面圖PNG／JPG最多8 MB／1200萬畫素。影片最多3個來源，單檔20 MB／1～60秒，工作副本總量40 MB；自動轉為最高720p／30 FPS H.264＋AAC。原音預設靜音，可在片段開啟。')
        plan=st.file_uploader('上傳／更換平面圖',type=['png','jpg','jpeg'],max_upload_size=8,key=f"tour_plan_upload_{state.get('tour_plan_epoch',0)}",disabled=locked)
        if plan and not locked:
            ident=sha256(plan.getvalue()).hexdigest()
            if state.get('tour_plan_receipt')!=ident:
                try:
                    fresh=load_plan(plan.name,plan.getvalue())
                    if media_size(state)-len(state['floor_plan'].original if state.get('floor_plan') else b'')+len(fresh.original)>145*1024*1024:raise ValueError('專案素材總量需保留在145 MB內，以預留ZIP與渲染空間。')
                    tour=deepcopy(state.get('tour') or new_tour())
                    if state.get('floor_plan') and state['floor_plan'].id!=fresh.id:
                        for room in tour['rooms']:room['needs_review']=True
                    tour['plan_id']=fresh.id;state.update(floor_plan=fresh,tour=tour,tour_plan_receipt=ident);changed(state)
                    st.success('平面圖已更新；更換後請在下方逐一點選房間重新定位，待確認位置不顯示紅點。')
                except (ValueError,OSError,MemoryError) as exc:st.error(str(exc) or '記憶體不足，原平面圖保留。');state['tour_plan_receipt']=ident
        if state.get('floor_plan'):
            if st.button('移除平面圖（保留房名與片段）',disabled=locked):
                state['floor_plan']=None
                for room in state['tour']['rooms']:room['needs_review']=True
                state['tour_plan_receipt']=None;state['tour_plan_epoch']=state.get('tour_plan_epoch',0)+1;changed(state);st.rerun()
        files=st.file_uploader('加入MP4影片（自動追加導覽片段）',type=['mp4'],accept_multiple_files=True,max_upload_size=20,key=f"tour_videos_{state.get('tour_video_epoch',0)}",disabled=locked)
        receipts=state.setdefault('tour_video_receipts',[])
        for file in files or []:
            ident=sha256(file.getvalue()).hexdigest()
            if locked or ident in receipts:continue
            try:
                if len(state['video_assets'])>=MAX_VIDEOS:raise ValueError('最多3個影片來源，可在時間軸重用現有來源。')
                with st.spinner('正在驗證並轉碼MP4工作副本…'):v=load_video(file.name,file.getvalue())
                if sum(len(a.data) for a in state['video_assets'].values())+len(v.data)>MAX_VIDEO_TOTAL or media_size(state)+len(v.data)>145*1024*1024:raise ValueError('影片總量超過40 MB或專案素材超過145 MB，原資料保留。')
                state['video_assets']={**state['video_assets'],v.id:v};changed(state);st.success(f'{v.name}已加入；使用正規化工作副本，原大檔不保留。')
            except (ValueError,OSError,MemoryError) as exc:st.error(str(exc) or '影片處理記憶體不足，現有資料保留。')
            receipts.append(ident)
        state['tour_video_receipts']=receipts[-30:]
        if st.button('重設影片選檔（可重試）',disabled=locked):state['tour_video_receipts']=[];state['tour_video_epoch']=state.get('tour_video_epoch',0)+1;st.rerun()
        if st.button('重新整理素材連結',disabled=locked):changed(state);st.rerun()
        st.caption('影片預覽使用兩小時短效、不經登入驗證的隨機素材網址，請勿轉傳；閒置過久可重新整理素材連結。Cloud效能仍需實測，建議先用360p短片。')
