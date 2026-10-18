"""公開 static serving 的短效 ZIP；只回傳不可猜測的網址，不傳 Base64。"""
from pathlib import Path
import os
import re
import secrets
import threading
import time

ROOT = Path(__file__).resolve().parents[1] / 'static' / 'downloads'
TTL = 15 * 60
MAX_DISK = 320 * 1024 * 1024
_LOCK = globals().get('_LOCK', threading.RLock())
_JANITOR = globals().get('_JANITOR', None)
_NAME = re.compile(r'[0-9a-f]{64}\.(zip|part)')


def cleanup(now=None):
    now = time.time() if now is None else now
    with _LOCK:
        if not ROOT.exists():return
        for path in ROOT.iterdir():
            if _NAME.fullmatch(path.name) and not path.is_symlink():
                try:
                    if now-path.stat().st_mtime >= TTL:path.unlink()
                except OSError:pass  # Windows 下載中的檔案下次再清。


def revoke(archive):
    name = (archive or {}).get('artifact')
    if isinstance(name,str) and _NAME.fullmatch(name):
        with _LOCK:
            path=ROOT/name
            if path.parent.resolve()==ROOT.resolve():
                try:path.unlink(missing_ok=True)
                except OSError:pass


def _sweep():
    while True:
        time.sleep(30)
        cleanup()


def publish(data, base=''):
    global _JANITOR
    with _LOCK:
        ROOT.mkdir(parents=True,exist_ok=True)
        cleanup()
        used=sum(p.stat().st_size for p in ROOT.iterdir() if _NAME.fullmatch(p.name) and p.is_file())
        if used+len(data)>MAX_DISK:raise OSError('暫存下載空間不足')
        token=secrets.token_hex(32);part=ROOT/(token+'.part');ready=ROOT/(token+'.zip')
        try:
            with part.open('xb') as out:out.write(data)
            os.replace(part,ready)  # 完整寫入後才公開可下載名稱。
        finally:part.unlink(missing_ok=True)
        if _JANITOR is None or not _JANITOR.is_alive():
            _JANITOR=threading.Thread(target=_sweep,daemon=True,name='zip-expiry');_JANITOR.start()
        prefix='/'+base.strip('/') if base.strip('/') else ''
        return dict(artifact=ready.name,url=f'{prefix}/app/static/downloads/{ready.name}',expires_at=time.time()+TTL)


def delivery(archive,requested_id=None):
    if not archive or not archive.get('url') or archive.get('expires_at',0)<=time.time():return None
    return {**{k:archive[k] for k in ('request_id','content_version','filename','url','expires_at')},'requested':archive['request_id']==requested_id}
