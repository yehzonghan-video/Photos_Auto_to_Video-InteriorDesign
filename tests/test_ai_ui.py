"""Streamlit 自動套用與排隊 UI 使用 Mock，不冒充真實 Gemini 呼叫。"""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from studio.ai import AIError, CallBudget, DEFAULT_MODEL, analyze_batch


class AIUITests(unittest.TestCase):
    def test_auto_import_four_photos_rerun_cache_models_and_quota(self):
        item=dict(label='木紋地板',description='可見木紋',category='地板',box_2d=[.5,0,1,1],
            anchor_x=.5,anchor_y=.75,suggested_label_x=.1,suggested_label_y=.6,
            confidence_level='中',needs_review=True)
        with patch('studio.ai_ui.settings',return_value=('mock-server-only','gemini-3.8-flash')), \
             patch('studio.ai.analyze_photo',return_value=[item]) as provider:
            with patch('studio.ai_ui.analyze_batch',side_effect=lambda *a,**kw:analyze_batch(*a,**kw,budget=CallBudget(),sleeper=lambda seconds:None)):
                app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=90).run()
                next(b for b in app.button if b.label=='載入 5 張測試示意圖').click().run()
                self.assertEqual(app.selectbox(key='ai_model').value,'gemini-3.1-flash-lite')
                self.assertIn('Gemini 3.1 Flash-Lite (建議)',app.selectbox(key='ai_model').options)
                before=copy.deepcopy([p.labels for p in app.session_state.photos])
                app.checkbox(key='ai_consent').check().run()
                ids=[p.id for p in app.session_state.photos[:4]]
                app.multiselect(key='ai_chosen').set_value(ids).run()
                next(b for b in app.button if b.label=='AI 分析並加入標籤').click().run()
                self.assertFalse(app.exception);self.assertEqual(provider.call_count,4)
                self.assertEqual(len(app.session_state.ai_imports),4)
                self.assertEqual([p.labels for p in app.session_state.photos],before,'等待前端整批草稿同步，保留人工內容')
                self.assertNotIn('mock-server-only',str(app.session_state.project_payload)+str(app.session_state.ai_imports))
                self.assertFalse(any(b.label in ('全部採用','套用所選標籤') for b in app.button))
                app.run();self.assertEqual(provider.call_count,4)
                next(b for b in app.button if b.label=='AI 分析並加入標籤').click().run()
                self.assertEqual(provider.call_count,4);self.assertEqual(len(app.session_state.ai_imports),4)
                self.assertTrue(any(b.label=='補查未完成照片（1 張）' for b in app.button))
                next(b for b in app.button if b.label=='補查未完成照片（1 張）').click().run()
                self.assertFalse(app.exception);self.assertEqual(provider.call_count,5)
                self.assertTrue(next(b for b in app.button if b.label=='補查未完成照片（0 張）').disabled)
                app.selectbox(key='ai_model').select('gemini-3.8-flash').run()
                app.run()
                self.assertEqual(app.selectbox(key='ai_model').value,'gemini-3.8-flash')
                self.assertTrue(any(b.label=='補查未完成照片（5 張）' for b in app.button))
                next(b for b in app.button if b.label=='AI 分析並加入標籤').click().run()
                self.assertEqual(provider.call_args.args[2],'gemini-3.8-flash')
                app.checkbox(key='ai_force').check().run()
                provider.side_effect=AIError('Gemini 額度不足（429），仍可手動製作影片。',code=429,retryable=True,retry_after=2)
                call_count=provider.call_count
                next(b for b in app.button if b.label=='AI 分析並加入標籤').click().run()
                self.assertFalse(app.exception);self.assertEqual(provider.call_count-call_count,2)
                self.assertTrue(any('429' in e.value for e in app.error))
                self.assertFalse(next(b for b in app.button if b.label=='輸出 H.264 MP4').disabled)


if __name__=='__main__':unittest.main()
