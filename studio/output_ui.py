"""既有輸出區的相鄰入口與背景進度；只使用公開Streamlit元件／fragment API。"""
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from . import output_jobs

BGM_API_VERSION = 10
actions=components.declare_component('interior_output_actions',path=str(Path(__file__).resolve().parents[1]/'frontend'/'actions'))


@st.fragment(run_every=1)
def progress_panel(state):
    current=output_jobs.progress(state)
    if current:
        st.progress(current['progress'],text=current['message'])
        if current['done']:
            output_jobs.collect(state,st.get_option('server.enableStaticServing'),st.get_option('server.baseUrlPath'))
            st.rerun(scope='app')


def operation_status(state):
    prepared=state.get('prepared_output')
    if prepared:
        import time
        if time.monotonic()-prepared['created']>300:
            state.pop('prepared_output',None)
            state['output_status']=dict(id=prepared['id'],phase='error',message='同步確認逾時；草稿保留，請重試。')
    return state.get('output_status')
