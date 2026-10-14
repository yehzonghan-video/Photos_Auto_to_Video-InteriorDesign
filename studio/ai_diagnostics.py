"""只記錄可公開的診斷欄位；不輸出金鑰、URL、照片或原始API訊息。"""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import math
import random
import re

import httpx
from pydantic import ValidationError

MAX_ATTEMPTS = 3  # 首次請求＋最多兩次補試，SDK內建重試另行關閉。
MAX_RETRY_WAIT = 120
LOGGER = logging.getLogger('interior_studio.gemini')
if not LOGGER.handlers:
    LOGGER.addHandler(logging.StreamHandler())
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False


def log_event(event, **fields):
    LOGGER.info('GEMINI_DIAGNOSTIC %s', json.dumps(
        dict(timestamp=datetime.now(timezone.utc).isoformat(), event=event, **fields),
        ensure_ascii=False, allow_nan=False))


def _seconds(value):
    try:
        seconds = float(value)
        return seconds if math.isfinite(seconds) and seconds >= 0 else None
    except (TypeError, ValueError):
        return None


def retry_hint(exc, now=None):
    headers = getattr(getattr(exc, 'response', None), 'headers', {}) or {}
    value = next((v for k, v in headers.items() if k.lower() == 'retry-after'), None)
    if value is not None:
        seconds = _seconds(value)
        if seconds is None:
            try:
                date = parsedate_to_datetime(value)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                seconds = max(0., (date - (now or datetime.now(timezone.utc))).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
        if seconds is not None:
            return seconds, 'retry_after_header'
    for detail in error_details(exc):
        if str(detail.get('@type', '')).endswith('/google.rpc.RetryInfo'):
            delay = detail.get('retryDelay')
            if isinstance(delay, str) and delay.endswith('s'):
                seconds = _seconds(delay[:-1])
            elif isinstance(delay, dict):
                base, nanos = _seconds(delay.get('seconds', 0)), _seconds(delay.get('nanos', 0))
                seconds = base + nanos / 1e9 if base is not None and nanos is not None else None
            else:
                seconds = None
            if seconds is not None:
                return seconds, 'google_retry_info'
    return None, None


def error_details(exc):
    body = getattr(exc, 'details', None)
    if not isinstance(body, dict):
        return []
    body = body.get('error', body)
    rows = body.get('details', []) if isinstance(body, dict) else []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def classify_error(exc):
    code = getattr(getattr(exc, 'response', None), 'status_code', None)
    if not isinstance(code, int):
        code = getattr(exc, 'code', None)
    code = code if type(code) is int else None
    quotas = []
    for detail in error_details(exc):
        if not str(detail.get('@type', '')).endswith('/google.rpc.QuotaFailure'):
            continue
        violations = detail.get('violations', [])
        for violation in violations if isinstance(violations, list) else []:
            if not isinstance(violation, dict):
                continue
            for field in ('quotaId', 'quotaMetric'):
                value = violation.get(field, '')
                if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}', value):
                    quotas.append(value)
    # 只在429且明確指向每日上限時停止，不能把所有RESOURCE_EXHAUSTED當成每日耗盡。
    daily = code == 429 and (any(re.search(r'per.?day|daily', v, re.I) for v in quotas) or
        bool(re.search(r'(daily|per[- ]day|per day|每日).{0,50}(quota|limit|額度)|'
                       r'(quota|limit).{0,50}(per[- ]day|per day|daily)', str(getattr(exc, 'message', '') or ''), re.I)))
    retry_after, retry_source = retry_hint(exc)
    api_status = getattr(exc, 'status', None)
    if not isinstance(api_status, str) or not re.fullmatch(r'[A-Z_]{1,60}', api_status):
        api_status = None
    if daily:
        kind, message = 'daily', 'Gemini 每日額度已耗盡（HTTP 429），本批次不再重試；請等額度重置，仍可手動製片。'
    elif code == 429:
        kind, message = 'rate', 'Gemini 速率或額度限制（HTTP 429）；未確認為每日耗盡，將依等待提示有限補試。'
    elif code == 503:
        kind, message = 'unavailable', 'Gemini 服務暫時不可用（HTTP 503 / UNAVAILABLE）。'
    elif code == 504:
        kind, message = 'deadline', 'Gemini 伺服器處理逾時（HTTP 504 / DEADLINE_EXCEEDED）。'
    elif code in (408, 500, 502):
        kind, message = 'server', f'Gemini 暫時性HTTP錯誤（HTTP {code}）。'
    elif code in (401, 403):
        kind, message = 'auth', f'Gemini 金鑰無效或沒有使用權限（HTTP {code}），請檢查伺服器設定。'
    elif code == 404:
        kind, message = 'model', '此帳號無法使用設定的Gemini模型（HTTP 404），請確認模型；不會自動換模型。'
    elif code is not None:
        kind, message = 'http', f'Gemini 請求失敗（HTTP {code}），請查看診斷代碼並檢查設定。'
    elif isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        kind, message = 'timeout', 'Gemini 用戶端等待逾時（未取得完整回覆），與HTTP 504不同。'
    elif isinstance(exc, httpx.TransportError):
        kind, message = 'connection', 'Gemini 網路連線失敗，未完成API回覆。'
    elif isinstance(exc, ValidationError):
        kind, message = 'validation', 'AI 回傳JSON缺漏欄位、座標無效或格式不符，未匯入標籤。'
    elif isinstance(exc, (ValueError, OSError)):
        kind, message = 'input', 'Gemini 分析資料或圖片處理失敗，請檢查照片格式與設定。'
    else:
        kind, message = 'unknown', 'Gemini 發生其他錯誤，請依診斷代碼查看Cloud Logs；仍可手動製片。'
    return dict(message=message, code=code, kind=kind,
        retryable=kind in ('rate', 'unavailable', 'deadline', 'server', 'timeout', 'connection'),
        retry_after=retry_after, retry_source=retry_source, api_status=api_status,
        error_type=type(exc).__name__, quota_ids=sorted(set(quotas)))


def retry_delay(error, attempt):
    """伺服器提示優先；無提示才指數退避＋jitter，不截短Retry-After。"""
    if error.retry_after is not None:
        return error.retry_after, error.retry_source or 'server_hint'
    base = 60 if error.code == 429 else 2
    return min(MAX_RETRY_WAIT, base * 2 ** (attempt - 1) + random.uniform(0, 1)), 'exponential_backoff'
