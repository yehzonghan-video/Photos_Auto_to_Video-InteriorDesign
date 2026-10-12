"""Streamlit AI 確認流程使用 Mock；真實 API 結果另記錄於 docs/AI.md。"""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from studio.ai import AIError, CallBudget, DEFAULT_MODEL


class AIUITests(unittest.TestCase):
    def test_mock_batch_review_no_rerun_calls_no_label_overwrite_and_quota(self):
        item=dict(label='木紋地板',description='可見木紋',category='地板',box_2d=[.5,0,1,1],
            anchor_x=.5,anchor_y=.75,suggested_label_x=.1,suggested_label_y=.6,
            confidence_level='中',needs_review=True)
        with patch('studio.ai_ui.settings',return_value=('mock-server-only',DEFAULT_MODEL)), \
             patch('studio.ai.analyze_photo',return_value=[item]) as provider:
            # analyze_batch 的預設 analyzer 是定義時綁定；透過 UI 入口明確注入 Mock。
            from studio.ai import analyze_batch
            with patch('studio.ai_ui.analyze_batch',side_effect=lambda *a,**kw:analyze_batch(*a,**kw,analyzer=provider,budget=CallBudget())):
                app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=90).run()
                next(b for b in app.button if b.label=='載入 5 張測試示意圖').click().run()
                before=copy.deepcopy([p.labels for p in app.session_state.photos])
                app.checkbox(key='ai_consent').check().run()
                ids=[p.id for p in app.session_state.photos[:2]]
                app.multiselect(key='ai_chosen').set_value(ids).run()
                next(b for b in app.button if b.label=='AI 分析裝修項目').click().run()
                self.assertFalse(app.exception);self.assertEqual(provider.call_count,2)
                app.run();self.assertEqual(provider.call_count,2)
                next(b for b in app.button if b.label=='AI 分析裝修項目').click().run()
                self.assertEqual(provider.call_count,2,'工作階段快取不重複呼叫')
                next(t for t in app.text_input if t.label=='標籤名稱').set_value('人工確認名稱')
                next(t for t in app.text_input if t.label=='簡短說明').set_value('人工確認說明')
                next(b for b in app.button if b.label=='套用所選標籤').click().run()
                self.assertFalse(app.exception)
                self.assertEqual([p.labels for p in app.session_state.photos],before)
                batch=app.session_state.ai_imports[0]
                self.assertEqual(batch['items'][0]['label'],'人工確認名稱')
                self.assertNotIn('mock-server-only',str(app.session_state.project_payload)+str(app.session_state.ai_imports))
                app.run();self.assertEqual(len(app.session_state.ai_imports),1)
                next(b for b in app.button if b.label=='刪除建議 1').click().run()
                self.assertFalse(app.exception);self.assertEqual(len(app.session_state.ai_removed),1)
                self.assertEqual(provider.call_count,2)
                app.checkbox(key='ai_force').check().run()
                provider.side_effect=AIError('Gemini 額度不足（429），仍可手動製作影片。')
                next(b for b in app.button if b.label=='AI 分析裝修項目').click().run()
                self.assertFalse(app.exception)
                self.assertTrue(any('429' in e.value for e in app.error))
                self.assertFalse(next(b for b in app.button if b.label=='輸出 H.264 MP4').disabled)


if __name__=='__main__':unittest.main()
