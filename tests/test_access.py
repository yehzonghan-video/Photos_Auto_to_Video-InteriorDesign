"""真實 Streamlit 密碼表單與權限入口測試，不使用認證繞過。"""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from tests.app_helpers import TEST_PASSWORD, authenticated_app

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def submit(app, value):
    app.text_input(key="_access_password").input(value)
    next(b for b in app.button if b.label == "進入工作室").click().run()


class AccessTests(unittest.TestCase):
    def assert_closed(self, app):
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("file_uploader")), 0)
        self.assertFalse(any(b.label == "輸出 H.264 MP4" for b in app.button))
        self.assertFalse(any(s.label == "影片模板" for s in app.selectbox))

    def test_missing_invalid_and_placeholder_config_fail_closed(self):
        with patch.dict(os.environ, {"APP_PASSWORD": ""}), patch('studio.sync.consume_editor_event') as sync, \
             patch('studio.ai_ui.ai_panel') as ai, patch('studio.export.export_video') as export:
            for value in (None, "", "YOUR_PASSWORD_HERE", "CHANGE_ME", True):
                with self.subTest(value=value):
                    app = AppTest.from_file(APP)
                    if value is not None:
                        app.secrets['APP_PASSWORD'] = value
                    app.session_state['_access_verified'] = True  # 舊的布林值不能冒充登入。
                    app.session_state['studio_editor'] = dict(action='export')
                    app.run()
                    self.assert_closed(app)
                    self.assertTrue(any('APP_PASSWORD' in error.value for error in app.error))
            sync.assert_not_called();ai.assert_not_called();export.assert_not_called()

    def test_wrong_password_and_cleared_input(self):
        app = AppTest.from_file(APP);app.secrets['APP_PASSWORD'] = TEST_PASSWORD;app.run()
        submit(app, 'wrong-password')
        self.assert_closed(app)
        self.assertTrue(any('密碼不正確' in error.value for error in app.error))
        self.assertEqual(app.text_input(key='_access_password').value, '')
        self.assertNotIn('_access_verified', app.session_state)
        self.assertNotIn(TEST_PASSWORD, str(app.markdown) + str(app.code))

    def test_success_rerun_and_clear_project_keep_authorization(self):
        app = authenticated_app();self.assertFalse(app.exception)
        self.assertNotIn('_access_password', app.session_state)
        self.assertNotEqual(app.session_state['_access_verified'], TEST_PASSWORD)
        next(b for b in app.button if b.label == '載入 5 張測試示意圖').click().run()
        app.run();self.assertEqual(len(app.session_state.photos), 5)
        self.assertNotIn(TEST_PASSWORD, str(app.session_state.project_payload))
        next(b for b in app.button if b.label == '清空目前工作階段').click().run()
        from tests.app_helpers import approve_workspace_action
        approve_workspace_action(app)
        self.assertEqual(app.session_state.photos, [])
        self.assertTrue(any(b.label == '載入 5 張測試示意圖' for b in app.button))

    def test_logout_clears_private_session(self):
        app = authenticated_app()
        next(b for b in app.button if b.label == '載入 5 張測試示意圖').click().run()
        self.assertEqual(len(app.session_state.photos), 5)
        next(b for b in app.button if b.label == '登出').click().run()
        from tests.app_helpers import approve_workspace_action
        approve_workspace_action(app)
        self.assert_closed(app)
        for key in ('_access_verified', 'photos', 'ai_cache', 'output', 'pending_export', 'project_payload'):
            self.assertNotIn(key, app.session_state)
        submit(app, TEST_PASSWORD);self.assertEqual(app.session_state.photos, [])

    def test_password_change_invalidates_login_and_requires_new_password(self):
        app = authenticated_app();app.secrets['APP_PASSWORD'] = 'new-test-only-password';app.run()
        self.assert_closed(app)
        submit(app, TEST_PASSWORD);self.assert_closed(app)
        submit(app, 'new-test-only-password')
        self.assertTrue(any(b.label == '載入 5 張測試示意圖' for b in app.button))

    def test_five_failures_pause_this_session_then_allow_retry(self):
        with patch('studio.access.monotonic', return_value=100) as clock:
            app = AppTest.from_file(APP);app.secrets['APP_PASSWORD'] = TEST_PASSWORD;app.run()
            for _ in range(5):submit(app, 'wrong')
            self.assert_closed(app)
            self.assertTrue(next(b for b in app.button if b.label == '進入工作室').disabled)
            self.assertEqual(app.session_state['_access_retry_after'], 160)
            clock.return_value = 161
            next(b for b in app.button if b.label == '重新檢查等待時間').click().run()
            submit(app, TEST_PASSWORD)
            self.assertTrue(any(b.label == '載入 5 張測試示意圖' for b in app.button))
            self.assertNotIn('_access_failures', app.session_state)

    def test_environment_fallback_and_secrets_precedence(self):
        with patch.dict(os.environ, {'APP_PASSWORD': 'env-test-only-password'}):
            app = AppTest.from_file(APP).run();submit(app, 'env-test-only-password')
            self.assertTrue(any(b.label == '載入 5 張測試示意圖' for b in app.button))
            app = AppTest.from_file(APP);app.secrets['APP_PASSWORD'] = TEST_PASSWORD;app.run()
            submit(app, 'env-test-only-password');self.assert_closed(app)
            submit(app, TEST_PASSWORD)
            self.assertTrue(any(b.label == '載入 5 張測試示意圖' for b in app.button))


if __name__ == '__main__':unittest.main()
