"""可攜式專案ZIP：只保存影片資料與素材，不保存Secrets或登入狀態。"""
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
import json
import re
import stat
import uuid
import wave
import zipfile
import zlib

from PIL import Image
from .models import MAX_PHOTOS, load_photo
from .overlays import MAX_ASSETS, MAX_ASSET_BYTES, load_asset
from .music import MusicAsset
from .photo_processing import WORKING_BYTES, WORKING_PIXELS, SESSION_BYTES, SESSION_PIXELS

BGM_API_VERSION = 8
FORMAT = 'interior-video-project'
VERSION = 1
MAX_ARCHIVE_MB = 160
MAX_ARCHIVE_BYTES = MAX_ARCHIVE_MB * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_WAV_BYTES = 120 * 44100 * 4 + 4096
PROJECT_KEYS = ('overlays', 'comparisons', 'comparison_overlays', 'cover', 'music')


def archive_filename(title):
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', ' ', str(title)).strip(' .')[:60]
    return (clean or '室內設計案例') + '_專案.zip'


def build_archive(state):
    """只接受已同步的工作階段；檔案名稱使用流水號，避免帶入使用者路徑。"""
    photos = state['photos']
    if not photos:
        raise ValueError('請先加入照片再儲存專案。')
    manifest = dict(format=FORMAT, version=VERSION, created_at=datetime.now(timezone.utc).isoformat(),
                    video=dict(width=state.get('video_width', 1080), fps=30),
                    template_id=state.get('template_mode', 'items'), photos=[], assets=[], music_asset=None,
                    **{key: state[key] for key in PROJECT_KEYS})
    output = BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as bundle:
        def add(path, data):
            bundle.writestr(path, data)
            return dict(file=path, sha256=sha256(data).hexdigest())

        for index, photo in enumerate(photos):
            with Image.open(BytesIO(photo.original)) as image:
                extension = {'JPEG':'jpg', 'PNG':'png', 'WEBP':'webp'}[image.format]
            manifest['photos'].append({**photo.metadata(), 'optimization_note':photo.optimization_note,
                                      **add(f'media/photos/{index:02d}.{extension}', photo.original)})
        for index, asset in enumerate(state.get('overlay_assets', {}).values()):
            manifest['assets'].append(dict(id=asset.id, name=asset.name, builtin=asset.builtin,
                                           **add(f'media/overlays/{index:02d}.png', asset.original)))
        asset = state.get('music_asset')
        if asset:
            manifest['music_asset'] = dict(id=asset.id, name=asset.name, truncated=asset.truncated,
                                           **add('media/music.wav', asset.data))
        raw = json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ValueError('專案設定過大，請減少標籤內容。')
        bundle.writestr('manifest.json', raw)
        if sum(info.file_size for info in bundle.infolist()) > MAX_ARCHIVE_BYTES:
            raise ValueError('專案素材總量超過160 MB，請減少素材後再儲存。')
    data = output.getvalue()
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError('專案檔超過160 MB，請減少素材後再儲存。')
    return data


def _ident(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value):
        raise ValueError('專案素材識別碼不正確。')
    return value


def _name(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 180:
        raise ValueError('專案素材名稱不正確。')
    return value


def load_archive(data):
    """記憶體內讀取、檢查大小與雜湊，再沿用編輯器交易驗證；不解壓到磁碟。"""
    if not isinstance(data, bytes) or not data or len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError('請選擇有效的專案ZIP，單檔最多160 MB。')
    try:
        return _load_archive(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError('專案設定JSON無法讀取，請重新下載完整的專案檔。') from exc
    except ValueError:
        raise
    except (zipfile.BadZipFile, KeyError, TypeError, AttributeError, OSError, EOFError,
            RuntimeError, NotImplementedError, RecursionError, wave.Error, zlib.error,
            Image.DecompressionBombError) as exc:
        raise ValueError('專案檔損壞或內容格式不正確，請使用工作室匯出的ZIP。') from exc


def _load_archive(data):
    with zipfile.ZipFile(BytesIO(data)) as bundle:
        infos = bundle.infolist()
        names = [info.filename for info in infos]
        if not 1 <= len(infos) <= MAX_PHOTOS + MAX_ASSETS + 2 or len(set(names)) != len(names):
            raise ValueError('專案檔案數量超過限制或含重複檔案。')
        if sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
            raise ValueError('專案解壓後超過160 MB，無法安全讀取。')
        for info in infos:
            path = PurePosixPath(info.filename)
            if (not info.filename or len(info.filename) > 180 or path.is_absolute() or '..' in path.parts
                    or '\\' in info.filename or ':' in info.filename or info.is_dir()
                    or stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1
                    or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                raise ValueError('專案包含不支援的檔案路徑、連結或壓縮方式。')
        if 'manifest.json' not in names or bundle.getinfo('manifest.json').file_size > MAX_MANIFEST_BYTES:
            raise ValueError('找不到有效的專案設定manifest.json。')
        manifest = json.loads(bundle.read('manifest.json').decode('utf-8'))
        if not isinstance(manifest, dict) or manifest.get('format') != FORMAT:
            raise ValueError('這不是案例影片工作室的專案檔。')
        if type(manifest.get('version')) is not int or manifest['version'] != VERSION:
            raise ValueError('此專案版本尚不支援，請使用相容版本的工作室開啟。')
        template = manifest.get('template_id')
        video = manifest.get('video')
        if (template not in ('items', 'compare') or not isinstance(video, dict)
                or type(video.get('width')) is not int or video['width'] not in (360,720,1080)
                or type(video.get('fps')) is not int or video['fps'] != 30):
            raise ValueError('專案影片模板、解析度或影格率不正確。')
        rows, assets = manifest.get('photos'), manifest.get('assets')
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_PHOTOS:
            raise ValueError('專案需包含1～12張來源照片。')
        if not isinstance(assets, list) or len(assets) > MAX_ASSETS:
            raise ValueError('專案最多24個PNG素材。')
        used = {'manifest.json'}

        def media(meta, prefix, limit):
            if not isinstance(meta, dict):raise ValueError('專案素材資料不正確。')
            path = meta.get('file')
            if not isinstance(path, str) or not path.startswith(prefix) or path not in names or path in used:
                raise ValueError('專案缺少素材檔案或素材被重複引用。')
            info = bundle.getinfo(path)
            if not 0 < info.file_size <= limit:raise ValueError('專案內有素材超過單檔大小限制。')
            blob = bundle.read(path)
            if sha256(blob).hexdigest() != meta.get('sha256'):
                raise ValueError('專案素材校驗失敗，檔案可能不完整。')
            used.add(path)
            return blob

        photos, photo_ids, pixels, photo_bytes = [], set(), 0, 0
        for row in rows:
            blob = media(row, 'media/photos/', WORKING_BYTES)
            ident = _ident(row.get('id'))
            if ident in photo_ids:raise ValueError('照片識別碼不可重複。')
            photo_ids.add(ident)
            with Image.open(BytesIO(blob)) as image:
                count = image.width * image.height
                if count > WORKING_PIXELS:raise ValueError('專案照片超過工作副本的畫素限制。')
            pixels += count;photo_bytes += len(blob)
            if pixels > SESSION_PIXELS or photo_bytes > SESSION_BYTES:
                raise ValueError('專案照片總量超過目前工作階段上限。')
            photo = load_photo(_name(row.get('name')), blob);photo.id = ident
            note = row.get('optimization_note', '')
            if not isinstance(note,str):raise ValueError('照片最佳化說明格式不正確。')
            photo.optimization_note = note
            photos.append(photo)

        bank = {}
        for meta in assets:
            blob = media(meta, 'media/overlays/', MAX_ASSET_BYTES)
            ident = _ident(meta.get('id'))
            if ident in bank:raise ValueError('PNG素材識別碼不可重複。')
            if type(meta.get('builtin')) is not bool:raise ValueError('PNG素材來源格式不正確。')
            asset = load_asset(_name(meta.get('name')), blob, meta['builtin'])
            asset.id = ident  # 身分沿用專案，避免Pillow版本的PNG重新編碼改變引用。
            bank[ident] = asset
        if sum(len(a.original) for a in bank.values()) > 40*1024*1024:
            raise ValueError('PNG素材總量超過40 MB。')

        music_asset = None
        meta = manifest.get('music_asset')
        if meta is not None:
            blob = media(meta, 'media/', MAX_WAV_BYTES)
            with wave.open(BytesIO(blob), 'rb') as wav:
                count = wav.getnframes()
                if ((wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getcomptype()) != (2,2,44100,'NONE')
                        or not 4410 <= count <= 120*44100 or len(wav.readframes(count)) != count*4):
                    raise ValueError('專案BGM不是有效的標準WAV工作副本。')
            if type(meta.get('truncated')) is not bool:raise ValueError('BGM截取設定不正確。')
            music_asset = MusicAsset(_ident(meta.get('id')), _name(meta.get('name')), blob, count/44100, meta['truncated'])
        if used != set(names):raise ValueError('專案含有未列在設定中的額外檔案。')

        # 所有可編輯欄位共用既有驗證，並保持載入前的工作階段不動。
        from .sync import consume_editor_event
        staged = dict(photos=photos, overlay_assets=bank, music_asset=music_asset,
                      template_mode=template, editor_session='project-import', revision=0)
        event = dict(session='project-import', base_revision=0, nonce='project-import', action='apply',
                     photos=rows, template_id=template, **{key:manifest[key] for key in PROJECT_KEYS})
        consume_editor_event(staged, event)
        if not staged['editor_response']['ok']:
            raise ValueError('專案設定不正確：'+staged['editor_response']['message'])
        for group in [*staged['photos'], *staged['comparisons']]:
            for label in group['labels'] if isinstance(group,dict) else group.labels:
                # 專案時間為已儲存的定稿，不再次套用預設延後1秒。
                if label.get('comparison_side') not in ('before','after'):
                    label['label_timing_version'] = 1
        return {**{key:staged[key] for key in (*PROJECT_KEYS,'photos','overlay_assets','music_asset')},
                'template_mode':template, 'video_width':video['width']}


def install_project(state, project):
    """驗證成功後一次開啟新工作區；保留登入與AI用量，舊前端事件失效。"""
    state.update({key:project[key] for key in (*PROJECT_KEYS,'photos','overlay_assets','music_asset','template_mode','video_width')})
    state.update(editor_session=uuid.uuid4().hex, revision=state.get('revision',0)+1,
                 last_template=project['template_mode'], output=None, output_seconds=None, project_payload=None,
                 editor_assets={}, editor_response=None, editor_seen=[], pending_export=None, editor_busy=False,
                 project_archive=None, ai_cache={}, ai_results={}, ai_reports=[], ai_imports=[],
                 ai_queue=[], ai_delivered={}, ai_pending={}, asset_warnings=[])
    for key in ('studio_editor','render_job','project_save_job','ai_chosen','ai_consent','ai_force'):
        state.pop(key, None)
    for key in ('uploader_epoch','png_epoch','music_epoch','project_import_epoch'):
        state[key] = state.get(key,0)+1
    state['photo_upload_epochs'] = {role:state.get('photo_upload_epochs',{}).get(role,0)+1 for role in ('general','before','after')}
