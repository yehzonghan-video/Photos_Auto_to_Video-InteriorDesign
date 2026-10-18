"""模擬Cloud保留舊Python模組，驗證相容性修復不清除工作階段。"""
import copy
import inspect
import unittest
from unittest.mock import patch

from studio import component, export, sync, music, bootstrap
from studio.bootstrap import video_modules, BGM_API_VERSION
from tests.app_helpers import authenticated_app


def old_payload(photos, cache=None, assets=None, overlays=None, comparisons=None,
                template='items', comparison_overlays=None, cover=None):
    raise AssertionError('不應呼叫不相容的舊payload')


def old_export(photos, width=1080, height=1920, fps=30, progress=None, timeout=300,
               overlays=None, assets=None, template='items', comparisons=None, cover=None):
    raise AssertionError('不應呼叫不相容的舊export')


class BootstrapTests(unittest.TestCase):
    def test_current_api_does_not_reload_on_normal_reruns(self):
        with patch('studio.bootstrap.importlib.reload') as reload:
            self.assertEqual(video_modules(), (component, export, sync))
            self.assertEqual(video_modules(), (component, export, sync))
            reload.assert_not_called()

    def test_old_payload_export_and_sync_reloaded_without_replacing_render_lock(self):
        lock=export.RENDER_LOCK;lock.acquire()
        try:
            with patch.object(component,'payload',old_payload),patch.object(export,'export_video',old_export), \
                 patch.object(sync,'BGM_API_VERSION',0):
                a,b,c=video_modules()
                self.assertIn('music_asset',inspect.signature(a.payload).parameters)
                self.assertIn('music_asset',inspect.signature(b.export_video).parameters)
                self.assertEqual(c.BGM_API_VERSION,BGM_API_VERSION)
                self.assertIs(b.RENDER_LOCK,lock);self.assertTrue(lock.locked())
        finally:
            lock.release()

    def test_incomplete_deployment_is_explicit_not_silent_audio_fallback(self):
        with patch.object(component,'payload',old_payload),patch('studio.bootstrap.importlib.reload',side_effect=lambda module:module):
            with self.assertRaisesRegex(RuntimeError,'部署檔案版本不一致'):
                video_modules()

    def test_old_twenty_mb_music_module_is_reloaded(self):
        with patch.object(music,'BGM_API_VERSION',0),patch.object(music,'MAX_MUSIC_BYTES',20*1024*1024):
            video_modules()
            self.assertEqual(music.MAX_MUSIC_UPLOAD_MB,200)
            self.assertEqual(music.MAX_MUSIC_BYTES,200*1024*1024)

    def test_old_sync_without_replacement_event_is_reloaded(self):
        with patch.object(sync,'EDITOR_UI_VERSION',0):
            video_modules()
            self.assertEqual(sync.EDITOR_UI_VERSION,bootstrap.EDITOR_UI_VERSION)

    def test_live_streamlit_old_payload_preserves_photos_labels_and_music(self):
        app=authenticated_app()
        next(b for b in app.button if b.label=='載入 5 張測試示意圖').click().run()
        photo_ids=[p.id for p in app.session_state.photos]
        app.session_state.photos[0].labels[0]['text']='保留人工標籤'
        app.session_state.music['fade_out']=2
        prior_music=copy.deepcopy(app.session_state.music)
        app.session_state.project_payload=None
        with patch.object(component,'payload',old_payload):
            app.run()
            self.assertFalse(app.exception)
        self.assertEqual([p.id for p in app.session_state.photos],photo_ids)
        self.assertEqual(app.session_state.photos[0].labels[0]['text'],'保留人工標籤')
        self.assertEqual(app.session_state.music,prior_music)
        self.assertEqual(app.session_state.project_payload['music']['fade_out'],2)
        app.run();self.assertFalse(app.exception)

    def test_streamlit_also_refreshes_cached_old_bootstrap(self):
        app=authenticated_app()
        next(b for b in app.button if b.label=='載入 5 張測試示意圖').click().run()
        ids=[p.id for p in app.session_state.photos]
        with patch.object(bootstrap,'BGM_API_VERSION',1),patch.object(bootstrap,'video_modules',side_effect=AssertionError('不應使用舊載入器')):
            app.run();self.assertFalse(app.exception)
            self.assertIn('body',app.session_state.cover)
        self.assertEqual([p.id for p in app.session_state.photos],ids)


if __name__=='__main__':unittest.main()
