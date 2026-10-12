"""AI 邏輯使用 Mock，不代表真實 Google 呼叫成功。"""
import copy
from io import BytesIO
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock
from PIL import Image
from pydantic import ValidationError
from studio.ai import (AIError, Analysis, CallBudget, DEFAULT_MODEL, analyze_batch,
    analyze_photo, content_hash, image_part, queue_import, safe_error, settings)
from studio.models import load_photo, new_label, validate_label
from studio.sync import consume_editor_event


def sample():
    out=BytesIO();Image.new('RGB',(200,100),'tan').save(out,format='PNG')
    return load_photo('測試.png',out.getvalue())


def raw_item():
    return dict(label='木紋地板',description='可見木紋外觀',category='地板',box_2d=[500,100,950,900],
        anchor_x=.5,anchor_y=.75,suggested_label_x=.1,suggested_label_y=.6,confidence_level='中',needs_review=False)


class AITests(unittest.TestCase):
    def test_schema_rejects_missing_invalid_coordinates_and_box_order(self):
        self.assertEqual(Analysis.model_validate({'items':[raw_item()]}).items[0].label,'木紋地板')
        for update in ({'anchor_x':1.2},{'anchor_y':float('nan')},{'box_2d':[100,500,90,900]},
                       {'box_2d':[100,0,800,1001]},{'box_2d':[.1,0,.8,1]},{'anchor_x':.99}):
            with self.assertRaises(ValidationError):Analysis.model_validate({'items':[{**raw_item(),**update}]})
        item=raw_item();del item['description']
        with self.assertRaises(ValidationError):Analysis.model_validate({'items':[item]})

    def test_mock_sdk_structured_json_and_normalization(self):
        client=MagicMock();client.__enter__.return_value=client
        client.models.generate_content.return_value=SimpleNamespace(text=json.dumps({'items':[raw_item()]}))
        rows=analyze_photo(sample(),'mock-test',client_factory=lambda key:client)
        self.assertEqual(rows[0]['box_2d'],[.5,.1,.95,.9]);self.assertTrue(rows[0]['needs_review'])
        config=client.models.generate_content.call_args.kwargs['config']
        self.assertEqual(config.response_mime_type,'application/json');self.assertIn('items',config.response_json_schema['properties'])
        client.models.generate_content.return_value=SimpleNamespace(text='{}')
        with self.assertRaises(AIError):analyze_photo(sample(),'mock-test',client_factory=lambda key:client)

    def test_missing_key_and_paid_model_blocked(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(AIError):settings()
        with self.assertRaises(AIError):settings({'GEMINI_API_KEY':'mock','GEMINI_MODEL':'gemini-paid'})
        with self.assertRaises(AIError):analyze_photo(sample(),'')

    def test_batch_cache_force_and_independent_failures(self):
        first,second=sample(),sample();second.original+=b'changed';state={};calls=[]
        def mock(photo,key,model):
            calls.append(photo.id)
            if photo is second:raise AIError('單張失敗')
            return []
        reports=analyze_batch([first,second],'mock',DEFAULT_MODEL,state,analyzer=mock,budget=CallBudget())
        self.assertEqual([r['ok'] for r in reports],[True,False])
        analyze_batch([first],'mock',DEFAULT_MODEL,state,analyzer=mock,budget=CallBudget())
        self.assertEqual(len(calls),2)
        analyze_batch([first],'mock',DEFAULT_MODEL,state,force=True,analyzer=mock,budget=CallBudget())
        self.assertEqual(len(calls),3)
        with self.assertRaises(AIError):analyze_batch([first]*4,'mock',DEFAULT_MODEL,state)

    def test_quota_limits_and_safe_errors(self):
        budget=CallBudget()
        for _ in range(5):budget.reserve('mock',100)
        with self.assertRaises(AIError):budget.reserve('mock',100)
        budget.reserve('mock',161)
        self.assertIn('429',safe_error(SimpleNamespace(code=429)))
        state={'ai_calls':20};analyzer=MagicMock()
        report=analyze_batch([sample()],'mock',DEFAULT_MODEL,state,analyzer=analyzer,budget=CallBudget())
        self.assertFalse(report[0]['ok']);analyzer.assert_not_called()

    def test_queue_append_only_and_metadata_survives_sync(self):
        photo=sample();photo.labels=[new_label()]
        item={**raw_item(),'box_2d':[.5,.1,.95,.9]}
        result={'id':'result','items':[item],'content_hash':content_hash(photo)}
        state={'photos':[photo],'editor_session':'session','revision':1}
        batch=queue_import(state,photo,result,[(0,{'label':'修改名稱','description':'修改說明'})])
        self.assertEqual(len(photo.labels),1)
        ai={**new_label(),**{key:item[key] for key in ('description','category','confidence_level','needs_review')},
            'source':'gemini','ai_item_id':batch['items'][0]['ai_item_id'],'text':'修改名稱'}
        rows=[photo.metadata()];rows[0]['labels']=copy.deepcopy(photo.labels)+[ai]
        event={'nonce':'apply','session':'session','base_revision':1,'action':'apply','photos':rows,'imported_batches':[batch['id']]}
        consume_editor_event(state,event)
        self.assertEqual(len(photo.labels),2);self.assertEqual(state['ai_imports'],[])
        self.assertEqual(photo.labels[1]['source'],'gemini')
        consume_editor_event(state,event);self.assertEqual(len(photo.labels),2)
        changed={**result,'content_hash':'replaced'}
        with self.assertRaises(AIError):queue_import(state,photo,changed,[(0,{'label':'a','description':'b'})])

    def test_exif_correct_analysis_copy(self):
        out=BytesIO();image=Image.new('RGB',(2000,1000));exif=Image.Exif();exif[274]=6
        image.save(out,format='JPEG',exif=exif)
        photo=load_photo('旋轉.jpg',out.getvalue());part=image_part(photo)
        with Image.open(BytesIO(part.inline_data.data)) as corrected:self.assertEqual(corrected.size,(800,1600))
        self.assertEqual(photo.original,out.getvalue())


if __name__=='__main__':unittest.main()
