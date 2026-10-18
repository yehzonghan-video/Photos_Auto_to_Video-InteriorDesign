"""全部使用Mock，驗證模型來回切換及分析條件失效，不使用真實API。"""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from studio import ai
from tests.test_ai import sample
from tests.app_helpers import authenticated_app

BUDGET=SimpleNamespace(reserve=lambda key:None)


class AICacheVersionTests(unittest.TestCase):
    def test_a_b_a_uses_valid_cache_and_force_or_real_condition_changes_invalidate(self):
        photo=sample();state={};calls=[];a,b=list(ai.MODEL_CHOICES)[:2]
        def provider(p,key,model):calls.append(model);return []
        def analyze(model,**kwargs):return ai.analyze_batch([photo],'mock',model,state,analyzer=provider,budget=BUDGET,**kwargs)
        analyze(a);analyze(b)
        self.assertEqual(ai.unfinished_photos([photo],a,state),[])
        self.assertTrue(analyze(a)[0]['cached']);self.assertEqual(calls,[a,b])
        analyze(a,force=True);self.assertEqual(calls,[a,b,a])
        photo.original+=b'replacement';self.assertEqual(ai.unfinished_photos([photo],a,state),[photo])
        analyze(a);self.assertEqual(len(calls),4)
        with patch.object(ai,'PROMPT_VERSION','new-prompt-version'):
            self.assertEqual(ai.unfinished_photos([photo],a,state),[photo]);analyze(a)
        self.assertEqual(len(calls),5)
        with patch.object(ai,'PROMPT',ai.PROMPT+'\n其他分析條件'):
            self.assertEqual(ai.unfinished_photos([photo],a,state),[photo]);analyze(a)
        self.assertEqual(len(calls),6)
        with patch.dict(ai.GENERATION_OPTIONS,temperature=.4):
            self.assertEqual(ai.unfinished_photos([photo],a,state),[photo]);analyze(a)
        self.assertEqual(len(calls),7)
        with patch.object(ai,'IMAGE_EDGE',1200):
            self.assertEqual(ai.unfinished_photos([photo],a,state),[photo]);analyze(a)
        self.assertEqual(len(calls),8)

    def test_failed_explicit_refresh_stays_pending_even_when_other_model_succeeds(self):
        p=sample();state={};a,b=list(ai.MODEL_CHOICES)[:2]
        ai.analyze_batch([p],'mock',a,state,analyzer=lambda *args:[],budget=BUDGET)
        def failed(*args):raise ai.AIError('Mock失敗')
        ai.analyze_batch([p],'mock',a,state,force=True,analyzer=failed,budget=BUDGET)
        ai.analyze_batch([p],'mock',b,state,analyzer=lambda *args:[],budget=BUDGET)
        self.assertEqual(ai.unfinished_photos([p],a,state),[p])

    def test_ui_model_switch_does_not_call_api_and_explicit_refresh_remains_available(self):
        a,b=list(ai.MODEL_CHOICES)[:2]
        with patch('studio.ai_ui.settings',return_value=('mock-server-only',a)),patch('studio.ai.analyze_photo',return_value=[]) as provider, \
             patch('studio.ai_ui.analyze_batch',side_effect=lambda *args,**kwargs:ai.analyze_batch(*args,**kwargs,budget=BUDGET)):
            app=authenticated_app();next(x for x in app.button if x.label=='載入 5 張測試示意圖').click().run()
            app.checkbox(key='ai_consent').check().run()
            app.multiselect(key='ai_chosen').set_value([app.session_state.photos[0].id]).run()
            next(x for x in app.button if x.label=='AI 分析並加入標籤').click().run();self.assertEqual(provider.call_count,1)
            app.selectbox(key='ai_model').select(b).run();self.assertEqual(provider.call_count,1)
            next(x for x in app.button if x.label=='AI 分析並加入標籤').click().run();self.assertEqual(provider.call_count,2)
            app.selectbox(key='ai_model').select(a).run();app.run();self.assertEqual(provider.call_count,2)
            next(x for x in app.button if x.label=='AI 分析並加入標籤').click().run();self.assertEqual(provider.call_count,2)
            app.checkbox(key='ai_refresh_requested').check().run()
            next(x for x in app.button if x.label=='AI 分析並加入標籤').click().run();self.assertEqual(provider.call_count,3)
            self.assertFalse(app.exception)
