"""破壞性操作前一次性檢查前端草稿；不把暫存或下載請求當成已備份。"""
import re
import uuid
import streamlit as st
from .versioning import refresh

BGM_API_VERSION = 10
ACTIONS={'clear':'清空工作區','logout':'登出','import':'匯入取代目前專案'}


def has_project(state):
    from .cover import new_cover
    from .music import new_music
    return bool(state.get('photos') or state.get('music_asset') or state.get('comparisons') or
                state.get('overlays') or state.get('comparison_overlays') or
                state.get('cover') not in (None,new_cover()) or state.get('music') not in (None,new_music()) or
                any(not a.builtin for a in state.get('overlay_assets',{}).values()))


def request(state, action):
    if action not in ACTIONS:raise ValueError('不支援此工作區操作。')
    if state.get('guard_request'):return
    if not has_project(state):
        state['guard_approved']=action
    else:
        state['guard_request']=dict(id=uuid.uuid4().hex,action=action,status='checking')


def receive_probe(state, event):
    guard=state.get('guard_request')
    if not guard or event.get('session')!=state.get('editor_session') or event.get('request')!=guard['id']:return
    if event.get('base_revision')!=state.get('revision'):
        guard.update(id=uuid.uuid4().hex,status='checking')
        return
    version=event.get('content_version')
    if not isinstance(version,str) or not re.fullmatch(r'cv1-[0-9a-f]{64}',version):version=None
    state['frontend_version']=version
    state['frontend_seq']=event.get('seq')
    guard.update(version=version,server_version=refresh(state),status='confirm')
    # 前端已鎖定本次檢查的草稿；只有明確確認過的同版本ZIP才免再確認。
    if version and version==state.get('backup_confirmed_version') and not state.get('ai_imports'):
        state['guard_approved']=guard['action']
        state.pop('guard_request',None)


def cancel(state):
    state.pop('guard_request',None)
    state.pop('guard_approved',None)
    state.pop('guard_import_project',None)


def approve(state):
    guard=state.pop('guard_request',None)
    if guard:state['guard_approved']=guard['action']


def panel(state):
    guard=state.get('guard_request')
    if not guard:return
    action=ACTIONS[guard['action']]
    if guard['status']=='checking':
        st.info(f'正在檢查目前分頁的草稿與ZIP備份版本，再執行「{action}」。')
    else:
        st.warning(f'目前草稿尚無已確認的同版本ZIP備份。繼續「{action}」將放棄目前工作區；取消可保留全部內容。')
    st.caption('前端暫存、ZIP產生或下載已請求，都不代表檔案已成功儲存在電腦。')
    if st.button('取消操作',key='cancel_workspace_action',use_container_width=True):
        cancel(state);st.rerun()
    label=f'仍要{action}' if guard['status']=='confirm' else f'無法完成檢查時，仍要{action}（放棄未備份內容）'
    if st.button(label,key='confirm_workspace_action',use_container_width=True):
        approve(state);st.rerun()
