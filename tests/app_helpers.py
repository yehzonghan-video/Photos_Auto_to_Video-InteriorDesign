"""使用實際密碼表單登入後進行既有製片回歸；這個密碼只存在測試中。"""
from pathlib import Path
from streamlit.testing.v1 import AppTest

TEST_PASSWORD = "test-only-access-password-測試"


def request_legacy_export(app):
    """保留舊客戶端輸出握手的回歸；新雙按鈕流程另由test_output_flow與瀏覽器測試。"""
    import uuid
    app.session_state.pending_export=dict(id=uuid.uuid4().hex,width=app.session_state.video_width)
    app.run()


def output_controls(app):
    import json
    return next(json.loads(item.proto.json_args) for item in app.get('component_instance')
                if item.proto.component_name=='studio.output_ui.interior_output_actions')


def authenticated_app():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=90)
    app.secrets["APP_PASSWORD"] = TEST_PASSWORD
    app.run()
    app.text_input(key="_access_password").input(TEST_PASSWORD)
    next(b for b in app.button if b.label == "進入工作室").click().run()
    return app


def approve_workspace_action(app):
    """AppTest無法執行iframe，模擬其一次性版本檢查，再走真正確認按鈕。"""
    guard=app.session_state.guard_request
    app.session_state['studio_editor']=dict(action='inspect_guard',nonce=guard['id'],request=guard['id'],
        session=app.session_state.editor_session,base_revision=app.session_state.revision,
        content_version=app.session_state.content_version)
    app.run()
    confirmations=[b for b in app.button if b.key=='confirm_workspace_action']
    if confirmations:confirmations[0].click().run()
    return app
