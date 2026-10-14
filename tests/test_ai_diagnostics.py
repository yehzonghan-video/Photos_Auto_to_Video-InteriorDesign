"""真正SDK＋HTTPX模擬傳輸；不呼叫Google、不冒充真實API成功。"""
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from google import genai
from google.genai import errors, types
import httpx

from studio.ai import AIError, analyze_photo, analyze_batch, unfinished_photos, DEFAULT_MODEL, client_for
from studio.ai_diagnostics import classify_error, retry_hint, retry_delay, LOGGER
from tests.test_ai import sample


def api_error(code, status, details=None, headers=None, message='test only'):
    response = httpx.Response(code, headers=headers or {})
    cls = errors.ServerError if code >= 500 else errors.ClientError
    return cls(code, {'error':{'status':status, 'message':message, 'details':details or []}}, response)


NO_BUDGET = SimpleNamespace(reserve=lambda key:None)


class AIDiagnosticTests(unittest.TestCase):
    def test_distinct_status_timeout_connection_and_no_unknown_retry(self):
        cases = [(api_error(429,'RESOURCE_EXHAUSTED'), 'rate',429,True),
                 (api_error(503,'UNAVAILABLE'), 'unavailable',503,True),
                 (api_error(504,'DEADLINE_EXCEEDED'), 'deadline',504,True),
                 (httpx.ReadTimeout('private URL and key'), 'timeout',None,True),
                 (httpx.ConnectTimeout('private URL'), 'timeout',None,True),
                 (httpx.ConnectError('private URL'), 'connection',None,True),
                 (RuntimeError('private key'), 'unknown',None,False),
                 (api_error(400,'INVALID_ARGUMENT'), 'http',400,False)]
        for exc,kind,code,retryable in cases:
            with self.subTest(kind=kind):
                info=classify_error(exc)
                self.assertEqual((info['kind'],info['code'],info['retryable']),(kind,code,retryable))
                self.assertNotIn('private',info['message'])

    def test_daily_quota_only_explicit_and_retry_after_not_daily_by_itself(self):
        details=[{'@type':'type.googleapis.com/google.rpc.QuotaFailure','violations':[
            {'quotaId':'GenerateRequestsPerDayPerProjectPerModel-FreeTier',
             'quotaMetric':'generativelanguage.googleapis.com/generate_content_free_tier_requests'}]}]
        daily=classify_error(api_error(429,'RESOURCE_EXHAUSTED',details))
        self.assertEqual(daily['kind'],'daily');self.assertFalse(daily['retryable'])
        minute=classify_error(api_error(429,'RESOURCE_EXHAUSTED',headers={'Retry-After':'60'}))
        self.assertEqual(minute['kind'],'rate');self.assertTrue(minute['retryable'])
        self.assertEqual(classify_error(api_error(429,'RESOURCE_EXHAUSTED',message='Quota exceeded: requests per day'))['kind'],'daily')

    def test_retry_after_seconds_date_and_google_retry_info(self):
        now=datetime(2026,10,14,tzinfo=timezone.utc)
        self.assertEqual(retry_hint(api_error(503,'UNAVAILABLE',headers={'Retry-After':'75'})),(75.,'retry_after_header'))
        date=format_datetime(now+timedelta(seconds=90),usegmt=True)
        self.assertEqual(retry_hint(api_error(503,'UNAVAILABLE',headers={'Retry-After':date}),now),(90.,'retry_after_header'))
        retry=[{'@type':'type.googleapis.com/google.rpc.RetryInfo','retryDelay':'1.5s'}]
        self.assertEqual(retry_hint(api_error(429,'RESOURCE_EXHAUSTED',retry)),(1.5,'google_retry_info'))
        self.assertEqual(retry_hint(api_error(429,'RESOURCE_EXHAUSTED',retry,{'retry-after':'12'})),(12.,'retry_after_header'))
        self.assertEqual(retry_hint(api_error(503,'UNAVAILABLE',headers={'Retry-After':'NaN'})),(None,None))
        with patch('studio.ai_diagnostics.random.uniform',return_value=0):
            error=AIError('test',code=503,retryable=True)
            self.assertEqual([retry_delay(error,n)[0] for n in (1,2)],[2,4])

    def test_real_sdk_response_hooks_status_elapsed_and_redacted_logs(self):
        for code, valid in ((200,True),(200,False),(503,False),(504,False),(429,False)):
            def respond(request):
                if code==200:
                    body={'candidates':[{'content':{'parts':[{'text':'{"items":[]}' if valid else '{}'}],'role':'model'},'finishReason':'STOP'}]}
                else:
                    body={'error':{'code':code,'status':{503:'UNAVAILABLE',504:'DEADLINE_EXCEEDED',429:'RESOURCE_EXHAUSTED'}[code],
                                   'message':'SECRET_API_KEY private-photo-name private-base64'}}
                return httpx.Response(code,json=body,headers={'Retry-After':'75'})
            transport=httpx.MockTransport(respond)
            real_client=genai.Client
            def factory(**kwargs):
                kwargs['http_options'].client_args['transport']=transport
                return real_client(**kwargs)
            with self.subTest(code=code,valid=valid),patch('studio.ai.genai.Client',side_effect=factory),self.assertLogs(LOGGER,level='INFO') as logs:
                diagnostic={}
                if code==200 and valid:
                    self.assertEqual(analyze_photo(sample(),'SECRET_API_KEY',diagnostics=diagnostic),[])
                else:
                    with self.assertRaises(AIError) as raised:
                        analyze_photo(sample(),'SECRET_API_KEY',diagnostics=diagnostic)
                    if code==200:
                        self.assertEqual(raised.exception.kind,'validation')
                        self.assertFalse(raised.exception.retryable)
                    else:
                        self.assertEqual(raised.exception.retry_after,75)
                        self.assertEqual(raised.exception.code,code)
                self.assertEqual(diagnostic['http_status'],code)
                self.assertGreaterEqual(diagnostic['elapsed_seconds'],0)
                logged='\n'.join(logs.output)
                for secret in ('SECRET_API_KEY','private-photo-name','private-base64','https://'):
                    self.assertNotIn(secret,logged)
                self.assertIn('request_end',logged)

    def test_client_timeout_logs_have_no_invented_http_code(self):
        def respond(request):raise httpx.ReadTimeout('SECRET_API_KEY private request',request=request)
        real_client=genai.Client
        def factory(**kwargs):
            kwargs['http_options'].client_args['transport']=httpx.MockTransport(respond)
            return real_client(**kwargs)
        with patch('studio.ai.genai.Client',side_effect=factory),self.assertLogs(LOGGER,level='INFO') as logs:
            with self.assertRaises(AIError) as raised:analyze_photo(sample(),'SECRET_API_KEY')
        self.assertEqual(raised.exception.kind,'timeout');self.assertIsNone(raised.exception.code)
        self.assertEqual(raised.exception.diagnostics['error_type'],'ReadTimeout')
        self.assertNotIn('SECRET_API_KEY','\n'.join(logs.output))
        class PartialStream(httpx.SyncByteStream):
            def __iter__(self):
                yield b'{"candidates":'
                raise httpx.ReadTimeout('private incomplete body')
        def partial_response(request):return httpx.Response(200,stream=PartialStream())
        def partial_factory(**kwargs):
            kwargs['http_options'].client_args['transport']=httpx.MockTransport(partial_response)
            return real_client(**kwargs)
        with patch('studio.ai.genai.Client',side_effect=partial_factory),self.assertLogs(LOGGER,level='INFO'):
            with self.assertRaises(AIError) as raised:analyze_photo(sample(),'SECRET_API_KEY')
        self.assertEqual(raised.exception.kind,'timeout')
        self.assertEqual(raised.exception.diagnostics['http_status'],200,'收到HTTP標頭後body逾時也保留真實狀態')

    def test_backoff_three_attempts_retry_after_respected_and_no_early_long_retry(self):
        waits=[];calls=[]
        def unavailable(*args):calls.append(1);raise AIError('503',code=503,retryable=True)
        with patch('studio.ai_diagnostics.random.uniform',return_value=0):
            reports=analyze_batch([sample()],'mock',DEFAULT_MODEL,{},analyzer=unavailable,
                                 budget=NO_BUDGET,sleeper=waits.append)
        self.assertEqual(len(calls),3);self.assertEqual(sum(waits),6)
        self.assertEqual(reports[0]['attempts'],3)
        calls.clear();waits.clear()
        def rate(*args):calls.append(1);raise AIError('429',code=429,retryable=True,retry_after=75)
        analyze_batch([sample()],'mock',DEFAULT_MODEL,{},analyzer=rate,budget=NO_BUDGET,sleeper=waits.append)
        self.assertEqual(len(calls),3);self.assertEqual(sum(waits),150,'不把75秒提示截為60秒')
        calls.clear();waits.clear()
        def longer(*args):calls.append(1);raise AIError('503',code=503,retryable=True,retry_after=180)
        reports=analyze_batch([sample(),sample()],'mock',DEFAULT_MODEL,{},analyzer=longer,budget=NO_BUDGET,sleeper=waits.append)
        self.assertEqual(len(calls),1);self.assertFalse(waits);self.assertEqual(reports[1]['attempts'],0)
        self.assertIn('120秒',reports[0]['error'])

    def test_daily_no_retry_halts_unsent_preserves_success_then_repairs_only_failed(self):
        photos=[sample() for _ in range(4)];state={};calls=[]
        for index,photo in enumerate(photos):photo.original+=str(index).encode()
        def provider(photo,*args):
            calls.append(photo.id)
            if photo is not photos[0]:raise AIError('每日耗盡',code=429,kind='daily',retryable=False)
            return []
        reports=analyze_batch(photos,'mock',DEFAULT_MODEL,state,analyzer=provider,budget=NO_BUDGET)
        self.assertEqual(calls,[p.id for p in photos[:2]]);self.assertEqual([r['attempts'] for r in reports],[1,1,0,0])
        original=state['ai_results'][photos[0].id]
        missing=unfinished_photos(photos,DEFAULT_MODEL,state);self.assertEqual(missing,photos[1:])
        calls.clear()
        analyze_batch(missing,'mock',DEFAULT_MODEL,state,force=True,analyzer=lambda p,*a:calls.append(p.id) or [],budget=NO_BUDGET)
        self.assertEqual(calls,[p.id for p in photos[1:]])
        self.assertIs(state['ai_results'][photos[0].id],original)

    def test_failed_refresh_with_old_cache_does_not_masquerade_as_success(self):
        photo=sample();state={}
        analyze_batch([photo],'mock',DEFAULT_MODEL,state,analyzer=lambda *a:[],budget=NO_BUDGET)
        old=state['ai_results'][photo.id]
        def fail(*args):raise AIError('503',code=503,retryable=False)
        analyze_batch([photo],'mock',DEFAULT_MODEL,state,force=True,analyzer=fail,budget=NO_BUDGET)
        self.assertIs(state['ai_results'][photo.id],old)
        self.assertEqual(unfinished_photos([photo],DEFAULT_MODEL,state),[photo])
        calls=[]
        analyze_batch([photo],'mock',DEFAULT_MODEL,state,analyzer=lambda p,*a:calls.append(p.id) or [],budget=NO_BUDGET)
        self.assertEqual(calls,[photo.id],'補查必須重新呼叫，不能把舊快取充作本次成功')


if __name__=='__main__':unittest.main()
