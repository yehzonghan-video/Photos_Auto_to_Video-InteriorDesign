"""Streamlit 工作階段與真實 FFmpeg 端到端基本測試。"""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest


class AppTests(unittest.TestCase):
    def test_demo_session_export_and_clear(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=90).run()
        self.assertFalse(app.exception)
        next(b for b in app.button if b.label == "載入 5 張測試示意圖").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state.photos), 5)
        next(s for s in app.selectbox if s.label == "影片解析度").select(360).run()
        next(b for b in app.button if b.label == "輸出 H.264 MP4").click().run()
        self.assertFalse(app.exception)
        self.assertGreater(len(app.session_state.output), 1000)
        next(b for b in app.button if b.label == "清空目前工作階段").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.photos, [])
        self.assertIsNone(app.session_state.output)


if __name__ == "__main__":
    unittest.main()
