"""專案開啟與下載；保存之前的前端快照由既有元件同步交易提供。"""
import streamlit as st
from .project_io import MAX_ARCHIVE_MB, build_archive, load_archive, install_project, archive_filename
from .versioning import refresh
from .protection import request

BGM_API_VERSION = 10


def prepare_download(state):
    job=state.pop('project_save_job', None)
    if not job:return
    state.setdefault('project_archive',None)
    completed=False
    try:
        version=refresh(state)
        if isinstance(job,dict) and job.get('version')!=version:
            raise ValueError('專案內容已更新，請重新儲存最新版本。')
        with st.spinner('正在打包專案設定、照片、PNG與BGM…'):
            data = build_archive(state)
        state['project_archive'] = dict(data=data, filename=archive_filename(state['cover']['title']), revision=state['revision'],content_version=version)
        state['zip_version']=version
        completed=True
    except ValueError as exc:
        state['notice'] = f'專案檔未完成：{exc} 目前編輯內容仍保留。'
        state['notice_error'] = True
    except (OSError, RuntimeError, MemoryError):
        state['notice'] = '專案檔未完成，請減少素材後重新儲存；目前編輯內容仍保留。'
        state['notice_error'] = True
    if not completed:
        # 打包失敗不能回覆前端「檔案已完成」；已套用的編輯仍保留。
        state['editor_response'] = {**(state.get('editor_response') or {}), 'ok':False,
                                    'message':state['notice']}


def import_panel(state):
    with st.expander('開啟舊專案（ZIP）', expanded=not state['photos']):
        st.caption('匯入會取代目前工作區；需要保留現有內容時，請先儲存專案。')
        source = st.file_uploader('選擇工作室專案檔', type=['zip'], max_upload_size=MAX_ARCHIVE_MB,
                                  key=f"project_import_{state['project_import_epoch']}")
        if st.button('匯入並開啟專案', disabled=source is None or state['editor_busy'] or state['pending_export'] is not None or bool(state.get('guard_request')),
                     use_container_width=True):
            try:
                with st.spinner('正在驗證並開啟專案…'):
                    project = load_archive(source.getvalue())
                state['guard_import_project']=project
                request(state,'import')
                st.rerun()
            except (ValueError, OSError, MemoryError) as exc:
                st.error(str(exc) or '記憶體不足，無法開啟此專案；原有工作區保留。')


def download_panel(state):
    saved = state.get('project_archive')
    if saved:
        version=saved.get('content_version')
        st.download_button('下載專案檔 ZIP（含素材）', data=saved['data'], file_name=saved['filename'],
                           mime='application/zip', type='primary', on_click=download_requested,args=(state,version),key='download_project')
        st.caption(f"專案檔 {len(saved['data'])/1024/1024:.2f} MB · 這是按下儲存時的快照，後續修改請再次儲存。未包含MP4、密碼或API金鑰。")
        st.caption(f"ZIP版本：{short(version)}。是否符合尚未套用的草稿，請看編輯器的即時版本狀態。")
        if version!=state.get('content_version'):st.warning('此ZIP是舊版本，不是目前已同步內容的備份。')
        if version and state.get('zip_download_requested_version')==version:
            st.caption('已提出此版本的下載請求；網站無法確認電腦是否已成功儲存。')
            if state.get('backup_confirmed_version')!=version:
                st.button('我已確認此版本ZIP已儲存',on_click=confirm_backup,args=(state,version),key='confirm_zip_backup')
            else:st.caption('你已確認此版本ZIP已儲存；後續修改仍需另存。')


def short(version):
    return version[4:16] if version else '來源版本未知，建議重新產生'


def download_requested(state, version):
    if version and (state.get('project_archive') or {}).get('content_version')==version:
        state['zip_download_requested_version']=version


def confirm_backup(state, version):
    if version and state.get('zip_download_requested_version')==version:
        state['backup_confirmed_version']=version
