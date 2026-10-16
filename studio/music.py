"""BGM僅存目前工作階段；預覽與輸出共用PCM及線性淡出時間。"""
import base64
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
import wave

from .models import number, MAX_TOTAL_SECONDS

# 與照片上傳的200 MB上限一致；解碼仍只保留影片可使用的前120秒。
MAX_MUSIC_UPLOAD_MB = 200
MAX_MUSIC_BYTES = MAX_MUSIC_UPLOAD_MB * 1024 * 1024
BGM_API_VERSION = 7
FORMATS = {'mp3':'mp3', 'wav':'wav', 'm4a':'mov', 'ogg':'ogg', 'flac':'flac'}


@dataclass
class MusicAsset:
    id: str
    name: str
    data: bytes
    duration: float
    truncated: bool = False

    def metadata(self):
        return dict(id=self.id, name=self.name, duration=self.duration, truncated=self.truncated,
                    src='data:audio/wav;base64,'+base64.b64encode(self.data).decode('ascii'))


def new_music():
    return dict(enabled=True, source=None, volume=.5, fade_out=1., loop=True)


def validate_music(raw, asset=None):
    raw = new_music() if raw is None else raw
    if not isinstance(raw, dict) or type(raw.get('enabled')) is not bool or type(raw.get('loop')) is not bool:
        raise ValueError('BGM設定格式不正確。')
    source = raw.get('source')
    if source is not None and (not asset or source != asset.id):
        raise ValueError('BGM已替換或移除，請重新套用目前音樂。')
    for field in ('volume', 'fade_out'):
        if type(raw.get(field)) not in (int, float):
            raise ValueError('BGM音量與淡出時間必須為數值。')
    return dict(enabled=raw['enabled'], source=source, loop=raw['loop'],
                volume=number(raw['volume'], 0, 1), fade_out=number(raw['fade_out'], 0, 10))


def music_end(settings, source_duration, video_duration):
    return video_duration if settings['loop'] else min(source_duration, video_duration)


def gain_at(settings, source_duration, video_duration, time):
    if not settings['enabled'] or settings['source'] is None or time < 0:
        return 0.
    end = music_end(settings, source_duration, video_duration)
    if time >= end:
        return 0.
    fade = min(settings['fade_out'], end)
    return settings['volume'] * (min(1., (end-time)/fade) if fade else 1.)


def audio_filter(settings, source_duration, video_duration):
    end = music_end(settings, source_duration, video_duration)
    fade = min(settings['fade_out'], end)
    parts = [f'volume={settings["volume"]:.9f}']
    if fade:
        parts.append(f'afade=t=out:st={end-fade:.9f}:d={fade:.9f}:curve=tri')
    parts += ['apad', f'atrim=duration={video_duration:.9f}', 'asetpts=PTS-STARTPTS']
    return ','.join(parts)


def load_music(name, data):
    extension = Path(str(name)).suffix.lower().lstrip('.')
    if extension not in FORMATS or not isinstance(data, bytes) or not data:
        raise ValueError('BGM請使用有效的MP3、WAV、M4A、OGG或FLAC音檔。')
    if len(data) > MAX_MUSIC_BYTES:
        raise ValueError(f'BGM單檔最多{MAX_MUSIC_UPLOAD_MB} MB，請先用音訊工具截取需要的片段後再上傳。')
    from .export import ffmpeg_path
    with tempfile.TemporaryDirectory(prefix='interior-music-') as folder:
        source = Path(folder)/('input.'+extension)
        target = Path(folder)/'decoded.wav'
        source.write_bytes(data)
        try:
            result = subprocess.run([ffmpeg_path(), '-hide_banner', '-loglevel', 'error', '-y',
                '-protocol_whitelist', 'file,pipe', '-f', FORMATS[extension], '-i', str(source),
                '-map', '0:a:0', '-vn', '-t', str(MAX_TOTAL_SECONDS+.1), '-ac', '2', '-ar', '44100',
                '-c:a', 'pcm_s16le', str(target)], capture_output=True, timeout=30)
            if result.returncode or not target.exists():
                raise ValueError('無法讀取BGM，請確認音樂格式正確且檔案未損壞。')
            with wave.open(str(target), 'rb') as decoded:
                count = min(decoded.getnframes(), MAX_TOTAL_SECONDS*44100)
                truncated = decoded.getnframes() > count
                pcm = decoded.readframes(count)
            if count < 4410:
                raise ValueError('BGM至少需0.1秒。')
            normalized = BytesIO()
            with wave.open(normalized, 'wb') as output:
                output.setnchannels(2); output.setsampwidth(2); output.setframerate(44100); output.writeframes(pcm)
            wav = normalized.getvalue()
            return MusicAsset('music-'+sha256(wav).hexdigest()[:32], str(name)[:180], wav, count/44100, truncated)
        except subprocess.TimeoutExpired:
            raise ValueError('BGM處理超過30秒，請縮短音樂或改用MP3／WAV再試。') from None
        except (wave.Error, EOFError, OSError) as error:
            raise ValueError('無法處理BGM，請確認檔案與FFmpeg執行環境。') from error
