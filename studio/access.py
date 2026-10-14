"""共用密碼入口：只在伺服器驗證，不建立帳號或永久儲存登入資料。"""
import hashlib
import hmac
import math
import os
import secrets
from time import monotonic

import streamlit as st

_PROCESS_SALT = secrets.token_bytes(32)
MAX_FAILURES = 5
COOLDOWN_SECONDS = 60


def configured_password():
    try:
        value = st.secrets.get("APP_PASSWORD")
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        value = None
    if value is None:
        value = os.getenv("APP_PASSWORD", "")
    if not isinstance(value, str) or not value.strip() or value in ("YOUR_PASSWORD_HERE", "CHANGE_ME"):
        return None
    return value


def _fingerprint(value):
    # Session State 只留程序加鹽的驗證摘要；修改密碼或重啟程序會使登入失效。
    return hmac.new(_PROCESS_SALT, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _login():
    candidate = st.session_state.pop("_access_password", "")
    now = monotonic()
    until = st.session_state.get("_access_retry_after", 0)
    if now < until:
        return
    if until:
        st.session_state["_access_failures"] = 0
        st.session_state.pop("_access_retry_after", None)
    password = configured_password()
    if password and isinstance(candidate, str) and hmac.compare_digest(_fingerprint(candidate), _fingerprint(password)):
        st.session_state["_access_verified"] = _fingerprint(password)
        for key in ("_access_error", "_access_failures", "_access_retry_after"):
            st.session_state.pop(key, None)
        return
    st.session_state.pop("_access_verified", None)
    st.session_state["_access_error"] = True
    failures = st.session_state.get("_access_failures", 0) + 1
    st.session_state["_access_failures"] = failures
    if failures >= MAX_FAILURES:
        st.session_state["_access_retry_after"] = now + COOLDOWN_SECONDS


def require_password():
    password = configured_password()
    verified = st.session_state.get("_access_verified")
    if password and isinstance(verified, str) and hmac.compare_digest(verified, _fingerprint(password)):
        return
    st.session_state.pop("_access_verified", None)
    st.title("案例影片工作室")
    if password is None:
        st.error("尚未設定有效的 APP_PASSWORD。請在 Streamlit Secrets 或伺服器環境變數設定共用密碼。")
        st.code('APP_PASSWORD = "YOUR_PASSWORD_HERE"', language="toml")
        st.caption("請將範例文字換成自己的密碼；未設定前不開放製片功能。")
        st.stop()
    st.caption("請輸入共用密碼，進入照片編輯與影片製作工作室。")
    remaining = math.ceil(max(0, st.session_state.get("_access_retry_after", 0) - monotonic()))
    with st.form("access_login", clear_on_submit=True):
        st.text_input("共用密碼", type="password", key="_access_password", disabled=remaining > 0)
        st.form_submit_button("進入工作室", on_click=_login, disabled=remaining > 0, use_container_width=True)
    if remaining:
        st.warning(f"此工作階段連續輸入錯誤，請等候約 {remaining} 秒再試。")
        st.button("重新檢查等待時間", key="_access_retry")
    elif st.session_state.get("_access_error"):
        st.error("密碼不正確，請再試一次。")
    st.stop()


def logout():
    # 登出清除本工作階段的照片、AI 結果、影片及驗證摘要。
    st.session_state.clear()
