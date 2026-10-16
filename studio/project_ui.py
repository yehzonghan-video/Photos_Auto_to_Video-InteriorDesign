"""專案開啟與下載；保存之前的前端快照由既有元件同步交易提供。"""
import streamlit as st
from .project_io import MAX_ARCHIVE_MB, build_archive, load_archive, install_project, archive_filename

BGM_API_VERSION = 8


def prepare_download(state):
    if not state.pop('project_save_job', None):return
    state['project_archive'] = None
    try:
        with st.spinner('正在打包專案設定、照片、PNG與BGM…'):
            data = build_archive(state)
        state['project_archive'] = dict(data=data, filename=archive_filename(state['cover']['title']), revision=state['revision'])
    except ValueError as exc:
        state['notice'] = f'專案檔未完成：{exc} 目前編輯內容仍保留。'
        state['notice_error'] = True
    except (OSError, RuntimeError, MemoryError):
        state['notice'] = '專案檔未完成，請減少素材後重新儲存；目前編輯內容仍保留。'
        state['notice_error'] = True
    if state.get('project_archive') is None:
        # 打包失敗不能回覆前端「檔案已完成」；已套用的編輯仍保留。
        state['editor_response'] = {**(state.get('editor_response') or {}), 'ok':False,
                                    'message':state['notice']}


def import_panel(state):
    with st.expander('開啟舊專案（ZIP）', expanded=not state['photos']):
        st.caption('匯入會取代目前工作區；需要保留現有內容時，請先儲存專案。')
        source = st.file_uploader('選擇工作室專案檔', type=['zip'], max_upload_size=MAX_ARCHIVE_MB,
                                  key=f"project_import_{state['project_import_epoch']}")
        if st.button('匯入並開啟專案', disabled=source is None or state['editor_busy'] or state['pending_export'] is not None,
                     use_container_width=True):
            try:
                with st.spinner('正在驗證並開啟專案…'):
                    project = load_archive(source.getvalue())
                install_project(state, project)
                state['notice'] = f"已開啟專案，含{len(project['photos'])}張照片，可繼續編輯及輸出。"
                state['notice_error'] = False
                st.rerun()
            except (ValueError, OSError, MemoryError) as exc:
                st.error(str(exc) or '記憶體不足，無法開啟此專案；原有工作區保留。')


def download_panel(state):
    saved = state.get('project_archive')
    if saved:
        st.download_button('下載專案檔 ZIP（含素材）', data=saved['data'], file_name=saved['filename'],
                           mime='application/zip', type='primary', on_click='ignore', key='download_project')
        st.caption(f"專案檔 {len(saved['data'])/1024/1024:.2f} MB · 這是按下儲存時的快照，後續修改請再次儲存。未包含MP4、密碼或API金鑰。")
