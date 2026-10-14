"""Streamlit 工作階段與真實 FFmpeg 端到端基本測試。"""
import unittest
import copy
from pathlib import Path
from streamlit.testing.v1 import AppTest
from studio.models import new_label
from tests.app_helpers import authenticated_app


class AppTests(unittest.TestCase):
    def test_demo_session_export_and_clear(self):
        app = authenticated_app()
        self.assertFalse(app.exception)
        next(b for b in app.button if b.label == "載入 5 張測試示意圖").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state.photos), 5)
        rows=copy.deepcopy([photo.metadata() for photo in app.session_state.photos])
        for row in rows:
            row["duration"]=1
            for label in row["labels"]:label.update(start=0,end=1,enter=.2)
        rows[0]["labels"]=[new_label(1) for _ in range(10)]
        batch=dict(nonce="apply-batch",session=app.session_state.editor_session,
                   base_revision=app.session_state.revision,seq=10,action="apply",photos=rows)
        app.session_state["studio_editor"]=batch
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state.photos[0].labels),10)
        revision=app.session_state.revision
        app.run()
        self.assertEqual(app.session_state.revision,revision)
        self.assertEqual(len(app.session_state.photos[0].labels),10)
        next(s for s in app.selectbox if s.label == "影片解析度").select(360).run()
        next(b for b in app.button if b.label == "輸出 H.264 MP4").click().run()
        self.assertIsNone(app.session_state.output)
        request=app.session_state.pending_export
        latest=copy.deepcopy([photo.metadata() for photo in app.session_state.photos])
        latest[0]["labels"][0].update(text="輸出前最新文字",color="#ffcc00",font_size=60)
        source = next(iter(app.session_state.overlay_assets))
        layers = [dict(id="app-png", type="png", source=source, start=.5, duration=2,
                       x=.5, y=.6, width=.3, scale=1.4, rotation=25, opacity=.8,
                       layer=30, animation="left", exit_animation="fade", enter=.3, exit=.4)]
        app.session_state["studio_editor"]=dict(nonce="export-batch",session=app.session_state.editor_session,
            base_revision=app.session_state.revision,seq=11,action="export",request=request["id"],photos=latest,
            overlays=layers)
        app.run()
        self.assertFalse(app.exception)
        self.assertGreater(len(app.session_state.output), 1000)
        self.assertEqual(app.session_state.photos[0].labels[0]["text"],"輸出前最新文字")
        self.assertFalse(app.session_state.editor_busy)
        self.assertEqual(app.session_state.overlays[0]["rotation"],25)
        app.run()
        self.assertEqual(len(app.session_state.overlays),1)
        next(b for b in app.button if b.label == "清空目前工作階段").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.photos, [])
        self.assertIsNone(app.session_state.output)
        self.assertEqual(app.session_state.overlays, [])


if __name__ == "__main__":
    unittest.main()
