"""逐影格送至 FFmpeg，不將使用者照片或未壓縮影格永久寫入磁碟。"""
from functools import lru_cache
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time

from .models import MAX_TOTAL_SECONDS
from .rendering import crop_photo, label_tile, render_frame

BGM_API_VERSION = 7
# 相容性重載時沿用現有輸出鎖，避免同時開啟第二個FFmpeg程序。
RENDER_LOCK = globals().get('RENDER_LOCK', threading.Lock())


def ffmpeg_path():
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("找不到 FFmpeg。請安裝 requirements.txt；Cloud 需加入 packages.txt。") from exc


@lru_cache(maxsize=1)
def capabilities():
    binary = ffmpeg_path()
    result = subprocess.run([binary, "-hide_banner", "-encoders"], capture_output=True, timeout=20)
    if result.returncode or b"libx264" not in result.stdout:
        raise RuntimeError("目前 FFmpeg 不含 libx264，無法可靠輸出 H.264 MP4。")
    return dict(binary=binary, encoder="libx264", font="由系統中文字型產生共用標籤素材")


def export_video(photos, width=1080, height=1920, fps=30, progress=None, timeout=300, overlays=None, assets=None,
                 template="items", comparisons=None, cover=None, music=None, music_asset=None):
    if not photos:
        raise ValueError("請先上傳照片。")
    if (width, height) not in ((360, 640), (720, 1280), (1080, 1920)) or fps != 30:
        raise ValueError("不支援的輸出尺寸或影格率。")
    if template not in ("items","compare"):raise ValueError("影片模板不正確。")
    from .comparison import validate_comparisons, prepare_comparison, comparison_frame
    sequence=validate_comparisons(comparisons or [],photos) if template=="compare" else photos
    if not sequence:raise ValueError("請先新增一組前後配對再輸出。")
    from .cover import validate_cover, cover_frame, DURATION
    cover=validate_cover(cover,photos);prefix=DURATION if cover['enabled'] else 0
    from .body import body_layer, title_visible
    decoration=body_layer(cover,include_title=False) if cover['body']['logo_enabled'] else None
    title_decoration=body_layer(cover,include_logo=False) if cover['body']['enabled'] else None
    duration = sum(p["duration"] if template=="compare" else p.duration for p in sequence)
    duration+=prefix
    if duration > MAX_TOTAL_SECONDS:
        raise ValueError("影片最長 120 秒。")
    binary = capabilities()["binary"]
    from .music import validate_music, audio_filter
    music = validate_music(music, music_asset)
    has_music = music['enabled'] and music['source'] is not None
    total = sum(round((p['duration'] if template=='compare' else p.duration)*fps) for p in sequence)+round(prefix*fps)
    from .overlays import prepare_overlays, validate_overlays
    validated = validate_overlays(overlays or [], assets or {}, duration)
    if not RENDER_LOCK.acquire(blocking=False):
        raise RuntimeError("目前有另一支影片正在輸出，請稍候再試；可使用瀏覽器輸出。")
    process = None
    stop = threading.Event()
    started = time.monotonic()
    try:
        prepared = prepare_overlays(validated, assets or {})
        # 壓縮影片、BGM與FFmpeg診斷均使用暫存檔，離開區塊一律清除。
        with tempfile.TemporaryDirectory(prefix="interior-video-") as folder:
            target = Path(folder) / "case.mp4"
            with (Path(folder) / "encoder.log").open("w+b") as log:
                command = [binary, "-hide_banner", "-loglevel", "error", "-y",
                           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
                           "-r", str(fps), "-i", "pipe:0"]
                if has_music:
                    audio_path = Path(folder)/'bgm.wav';audio_path.write_bytes(music_asset.data)
                    if music['loop']:command += ['-stream_loop', '-1']
                    command += ['-i', str(audio_path), '-map', '0:v:0', '-map', '1:a:0',
                                '-af', audio_filter(music, music_asset.duration, total/fps),
                                '-c:a', 'aac', '-b:a', '192k', '-t', f'{total/fps:.9f}']
                else:
                    command += ['-an']
                command += ["-c:v", "libx264",
                           "-preset", "veryfast", "-threads", "2", "-crf", "20",
                           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)]
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
                # Watchdog 能打斷因編碼器掛住造成的 stdin 阻塞。
                def watchdog():
                    if not stop.wait(timeout):
                        process.kill()
                timer = threading.Thread(target=watchdog, daemon=True)
                timer.start()
                done = 0
                try:
                    def write_frame(frame):
                        nonlocal done
                        if (width,height)!=frame.size:
                            from PIL import Image
                            frame=frame.resize((width,height),Image.Resampling.LANCZOS)
                        process.stdin.write(frame.tobytes());done+=1
                        if progress and (done%15==0 or done==total):
                            progress(min(.98,done/total*.98),f'已送入編碼器 {done}/{total} 影格')
                        if time.monotonic()-started>timeout:
                            raise TimeoutError('輸出超過5分鐘，請縮短影片或改用720p。')
                    if prefix:
                        base=cover_frame(cover,photos)
                        for index in range(round(prefix*fps)):
                            write_frame(render_frame(base,[],[],index/fps,prepared,index/fps))
                    for photo in sequence:
                        if template=="compare":
                            frames=prepare_comparison(photo,photos);labels=photo["labels"];length=photo["duration"]
                        else:
                            base=crop_photo(photo);labels=photo.labels;length=photo.duration
                            if decoration is not None:base.alpha_composite(decoration)
                            title_base=base.copy() if title_decoration is not None else base
                            if title_decoration is not None:title_base.alpha_composite(title_decoration)
                        tiles = [label_tile(label) for label in labels]
                        count = round(length * fps)
                        for index in range(count):
                            if template=="compare":base=comparison_frame(photo,frames,index/fps)
                            if template=="compare" and decoration is not None:base.alpha_composite(decoration)
                            show_title=title_decoration is not None and title_visible(cover['body'],done/fps,round(prefix*fps)/fps,total/fps)
                            if template=="compare" and show_title:base.alpha_composite(title_decoration)
                            current=title_base if template!='compare' and show_title else base
                            frame = render_frame(current, labels, tiles, index / fps, prepared, done / fps)
                            write_frame(frame)
                    process.stdin.close()
                    code = process.wait(timeout=max(1, timeout - (time.monotonic() - started)))
                    if code:
                        log.seek(0)
                        detail = log.read().decode("utf-8", errors="replace")[-2000:]
                        raise RuntimeError("FFmpeg 編碼失敗：" + detail)
                    if not target.exists() or target.stat().st_size < 1000:
                        raise RuntimeError("影片輸出不完整，請重新嘗試。")
                    result = target.read_bytes()
                    if progress:
                        progress(1., "H.264 MP4 已完成")
                    return result
                except (BrokenPipeError, subprocess.TimeoutExpired) as exc:
                    raise RuntimeError("編碼器停止或輸出逾時。請改用 720p 或減少照片後重試。") from exc
                finally:
                    stop.set()
                    if process.poll() is None:
                        process.kill()
                    process.wait()
                    if not process.stdin.closed:
                        process.stdin.close()
                    timer.join(timeout=1)
    finally:
        RENDER_LOCK.release()
