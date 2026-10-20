"""受限MP4工作副本：一次轉碼供瀏覽器／FFmpeg／ZIP共用，不保存原始大檔。"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re,subprocess,tempfile,threading,time,secrets,os
from PIL import Image

BGM_API_VERSION=10
MAX_VIDEO_BYTES=20*1024*1024
MAX_VIDEOS=3
MAX_VIDEO_TOTAL=40*1024*1024
ROOT=Path(__file__).resolve().parents[1]/'static'/'tour'
_LOCK=globals().get('_LOCK',threading.RLock())
_JANITOR=globals().get('_JANITOR')


def _sweep():
    while True:
        time.sleep(60)
        with _LOCK:
            for path in ROOT.glob('*.mp4'):
                if re.fullmatch(r'[0-9a-f]{64}\.mp4',path.name) and not path.is_symlink():
                    try:
                        if time.time()-path.stat().st_mtime>7200:path.unlink()
                    except OSError:pass


@dataclass
class VideoAsset:
    id:str
    name:str
    data:bytes
    width:int
    height:int
    duration:float
    has_audio:bool
    poster:bytes


def probe(path):
    from .export import ffmpeg_path
    try:r=subprocess.run([ffmpeg_path(),'-hide_banner','-protocol_whitelist','file,pipe','-f','mov','-i',str(path)],capture_output=True,timeout=15)
    except subprocess.TimeoutExpired:raise ValueError('讀取影片資訊逾時，請使用較短MP4。') from None
    info=r.stderr.decode('utf-8','replace');d=re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)',info);v=re.search(r'Video: (\w+)[^\n]*? (\d{2,5})x(\d{2,5})',info)
    if not d or not v:raise ValueError('MP4缺少可讀取的影片／時長資訊，請先轉成一般H.264 MP4。')
    duration=int(d[1])*3600+int(d[2])*60+float(d[3]);w,h=int(v[2]),int(v[3])
    if not 1<=duration<=60.05 or w*h>16_777_216:raise ValueError('影片來源需為1～60秒、最多約4K畫素；請先截短或縮小。')
    fps=re.search(r'(\d+(?:\.\d+)?) fps',info)
    rotation=re.search(r'rotation of ([\-\d.]+)',info)
    return dict(width=w,height=h,duration=round(duration*30)/30,has_audio='Audio:' in info,codec=v[1],fps=float(fps[1]) if fps else None,rotation=float(rotation[1]) if rotation else 0)


def load_video(name,data,normalized=False):
    from .export import ffmpeg_path
    if Path(name).suffix.lower()!='.mp4' or not isinstance(data,bytes) or not 0<len(data)<=MAX_VIDEO_BYTES:raise ValueError('影片請使用MP4，單檔最多20 MB。')
    with tempfile.TemporaryDirectory(prefix='tour-video-') as folder:
        source=Path(folder)/'source.mp4';source.write_bytes(data);meta=probe(source);target=source if normalized else Path(folder)/'working.mp4'
        if not normalized:
            command=[ffmpeg_path(),'-v','error','-y','-protocol_whitelist','file,pipe','-f','mov','-i',str(source),'-map','0:v:0','-map','0:a:0?',
                '-t','60','-vf',"scale=w='min(720,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,fps=30,setsar=1",'-c:v','libx264','-preset','veryfast','-threads','2','-crf','23','-maxrate','1800k','-bufsize','3600k',
                '-c:a','aac','-b:a','128k','-ar','44100','-ac','2','-sn','-dn','-map_metadata','-1','-movflags','+faststart',str(target)]
            try:r=subprocess.run(command,capture_output=True,timeout=75)
            except subprocess.TimeoutExpired:raise ValueError('影片轉碼超過75秒，請縮短／縮小後再試。') from None
            if r.returncode:raise ValueError('FFmpeg無法解碼此MP4編碼，原專案保留；請先轉成H.264。')
            data=target.read_bytes();meta=probe(target)
        if len(data)>MAX_VIDEO_BYTES or meta['codec']!='h264' or meta['width']>720 or meta['height']>1280 or meta['fps']!=30 or meta['rotation']%360:
            raise ValueError('影片工作副本需為最高720p／30 FPS H.264，且已校正旋轉。')
        # AAC尾端可能讓容器比視訊長一影格；以實際解碼影格數決定可裁切範圍。
        try:packets=subprocess.run([ffmpeg_path(),'-v','error','-i',str(target),'-map','0:v:0','-an','-progress','pipe:1','-nostats','-f','null','-'],capture_output=True,timeout=30)
        except subprocess.TimeoutExpired:raise ValueError('影片影格驗證逾時，請縮短／縮小後再試。') from None
        counts=re.findall(rb'frame=(\d+)',packets.stdout)
        if packets.returncode or not counts:raise ValueError('無法確認影片影格數，請重新轉檔。')
        meta['duration']=int(counts[-1])/30
        if not 1<=meta['duration']<=60:raise ValueError('影片需1～60秒。')
        try:r=subprocess.run([ffmpeg_path(),'-v','error','-i',str(target),'-frames:v','1','-vf','scale=320:-2','-f','image2pipe','-vcodec','mjpeg','pipe:1'],capture_output=True,timeout=15)
        except subprocess.TimeoutExpired:raise ValueError('影片預覽影格讀取逾時，原專案保留。') from None
        if r.returncode or not r.stdout:raise ValueError('影片無法解碼預覽影格。')
        return VideoAsset('video-'+sha256(data).hexdigest()[:32],str(name)[:180],data,meta['width'],meta['height'],meta['duration'],meta['has_audio'],r.stdout)


def publish(asset):
    """短效能力網址，不把影片Base64送進元件；限制全程序暫存160MB。"""
    global _JANITOR
    with _LOCK:
        ROOT.mkdir(parents=True,exist_ok=True);now=time.time()
        for p in ROOT.glob('*.mp4'):
            if re.fullmatch(r'[0-9a-f]{64}\.mp4',p.name) and now-p.stat().st_mtime>7200:
                try:p.unlink()
                except OSError:pass
        # 不使用內容摘要作公開URL；程序內快取只保留有限影片的隨機檔名。
        entries=globals().setdefault('_PUBLISHED',{});entry=entries.get(asset.id)
        if entry and (ROOT/entry).exists():os.utime(ROOT/entry,None);return '/app/static/tour/'+entry
        entries={k:v for k,v in entries.items() if (ROOT/v).exists()};globals()['_PUBLISHED']=entries
        if sum(p.stat().st_size for p in ROOT.glob('*.mp4'))+len(asset.data)>160*1024*1024:raise ValueError('影片預覽暫存空間不足，請稍候或重新啟動本機工作室。')
        name=secrets.token_hex(32)+'.mp4';path=ROOT/name;part=ROOT/(name+'.part')
        try:part.write_bytes(asset.data);os.replace(part,path)
        finally:part.unlink(missing_ok=True)
        entries[asset.id]=name
        if _JANITOR is None or not _JANITOR.is_alive():_JANITOR=threading.Thread(target=_sweep,daemon=True,name='tour-media-expiry');_JANITOR.start()
        return '/app/static/tour/'+name


def decoder(asset,clip,folder):
    from .export import ffmpeg_path
    path=Path(folder)/(asset.id+'.mp4')
    if not path.exists():path.write_bytes(asset.data)
    p=subprocess.Popen([ffmpeg_path(),'-v','error','-ss',str(clip['in']),'-i',str(path),'-an','-vf','fps=30','-frames:v',str(round(clip['duration']*30)),'-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    try:
        for _ in range(round(clip['duration']*30)):
            raw=p.stdout.read(asset.width*asset.height*3)
            if len(raw)!=asset.width*asset.height*3:raise ValueError('影片影格不足或解碼失敗，請重新匯入。')
            yield Image.frombytes('RGB',(asset.width,asset.height),raw)
    finally:
        p.stdout.close()
        if p.poll() is None:p.kill()
        p.wait(timeout=10)


def original_audio(clips,videos,folder,prefix):
    from .export import ffmpeg_path
    import wave
    enabled=any(c['kind']=='video' and not c['muted'] and c['volume']>0 and videos[c['source']].has_audio for c in clips)
    if not enabled:return None
    rate=44100;pcm=bytearray(round((prefix+sum(c['duration'] for c in clips))*rate)*4);offset=round(prefix*rate)
    for c in clips:
        length=round(c['duration']*rate)
        if c['kind']=='video' and not c['muted'] and videos[c['source']].has_audio:
            a=videos[c['source']];path=Path(folder)/(a.id+'.mp4')
            if not path.exists():path.write_bytes(a.data)
            r=subprocess.run([ffmpeg_path(),'-v','error','-ss',str(c['in']),'-i',str(path),'-t',str(c['duration']),'-vn','-af',f"volume={c['volume']}",'-ac','2','-ar',str(rate),'-f','s16le','pipe:1'],capture_output=True,timeout=30)
            if r.returncode:raise ValueError('影片原音解碼失敗，請靜音該片段後重試。')
            data=r.stdout[:length*4];pcm[offset*4:offset*4+len(data)]=data
        offset+=length
    target=Path(folder)/'tour-original.wav'
    with wave.open(str(target),'wb') as wav:wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes(pcm)
    return target
