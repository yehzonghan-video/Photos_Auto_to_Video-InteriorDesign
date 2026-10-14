"""自行產生正弦波驗證BGM，沒有下載未知授權音樂。"""
from array import array
import copy
from io import BytesIO
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
import wave
from PIL import Image

from studio.music import load_music,new_music,validate_music,gain_at,MAX_MUSIC_UPLOAD_MB
from studio.export import export_video,ffmpeg_path
from studio.models import load_photo
from studio.cover import new_cover
from studio.component import payload
from studio.comparison import new_comparison
from studio.sync import consume_editor_event
from tests.app_helpers import authenticated_app


def tone(seconds=.5):
    data=array('h',(round(8192*math.sin(2*math.pi*440*i/44100)) for i in range(round(seconds*44100))))
    out=BytesIO()
    with wave.open(out,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(44100);wav.writeframes(data.tobytes())
    return out.getvalue()


def photo(name='case.png',color='red'):
    out=BytesIO();Image.new('RGB',(108,192),color).save(out,'PNG');p=load_photo(name,out.getvalue());p.duration=2;return p


def audio_samples(data):
    with tempfile.TemporaryDirectory(prefix='music-test-') as folder:
        path=Path(folder)/'video.mp4';path.write_bytes(data)
        decoded=subprocess.run([ffmpeg_path(),'-hide_banner','-i',str(path),'-map','0:a:0','-ac','1','-ar','44100','-f','s16le','pipe:1'],capture_output=True,check=True,timeout=60)
    pcm=array('h');pcm.frombytes(decoded.stdout);return pcm,decoded.stderr.decode('utf-8',errors='replace')


def rms(pcm,start,end):
    values=pcm[round(start*44100):round(end*44100)]
    return math.sqrt(sum(v*v for v in values)/len(values))


class MusicTests(unittest.TestCase):
    def test_large_wav_over_twenty_mb_is_trimmed_by_duration(self):
        # 真實24 MB、125秒WAV；確認上傳放寬且只保留前120秒音訊。
        source=BytesIO()
        with wave.open(source,'wb') as wav:
            wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(48000)
            wav.writeframes(b'\0'*(125*48000*4))
        data=source.getvalue();self.assertGreater(len(data),20*1024*1024)
        asset=load_music('較大的音樂.wav',data)
        self.assertEqual(asset.duration,120);self.assertTrue(asset.truncated)
        with wave.open(BytesIO(asset.data),'rb') as wav:
            self.assertEqual((wav.getnchannels(),wav.getsampwidth(),wav.getframerate()),(2,2,44100))
            self.assertEqual(wav.getnframes(),120*44100)

    def test_streamlit_uploader_accepts_larger_music(self):
        app=authenticated_app()
        next(b for b in app.button if b.label=='載入 5 張測試示意圖').click().run()
        self.assertFalse(app.exception)
        uploader=next(element for element in app.get('file_uploader') if element.proto.label=='選擇BGM')
        self.assertEqual(uploader.proto.max_upload_size_mb,MAX_MUSIC_UPLOAD_MB)
        self.assertEqual(MAX_MUSIC_UPLOAD_MB,200)

    def test_upload_normalized_stereo_and_bad_input(self):
        asset=load_music('自己的測試.wav',tone())
        self.assertAlmostEqual(asset.duration,.5)
        with wave.open(BytesIO(asset.data),'rb') as wav:
            self.assertEqual((wav.getnchannels(),wav.getsampwidth(),wav.getframerate()),(2,2,44100))
        self.assertTrue(asset.metadata()['src'].startswith('data:audio/wav;base64,'))
        for name,data in (('bad.wav',b'not music'),('bad.txt',tone()),('empty.mp3',b'')):
            with self.assertRaises(ValueError):load_music(name,data)

    def test_mp3_m4a_ogg_flac_actually_decode(self):
        with tempfile.TemporaryDirectory(prefix='music-formats-') as folder:
            source=Path(folder)/'source.wav';source.write_bytes(tone())
            for extension in ('mp3','m4a','ogg','flac'):
                target=Path(folder)/('audio.'+extension)
                subprocess.run([ffmpeg_path(),'-y','-i',str(source),str(target)],capture_output=True,check=True,timeout=30)
                with self.subTest(extension=extension):
                    asset=load_music(target.name,target.read_bytes());self.assertGreater(asset.duration,.4)

    def test_defaults_validation_and_linear_envelope(self):
        asset=load_music('tone.wav',tone());m={**new_music(),'source':asset.id}
        self.assertEqual(m['fade_out'],1)
        for update in ({'volume':2},{'fade_out':-1},{'fade_out':float('nan')},{'loop':'true'},{'source':'missing'},{'volume':True}):
            with self.assertRaises(ValueError):validate_music({**m,**update},asset)
        self.assertEqual(gain_at(m,.5,2.3,1),.5)
        self.assertAlmostEqual(gain_at(m,.5,2.3,1.8),.25)
        self.assertEqual(gain_at(m,.5,2.3,2.3),0)
        self.assertAlmostEqual(gain_at({**m,'loop':False},.5,3,.25),.25)

    def test_real_full_hd_aac_music_loops_and_default_one_second_fade(self):
        asset=load_music('tone.wav',tone());m={**new_music(),'source':asset.id}
        data=export_video([photo()],cover=new_cover(),music=m,music_asset=asset)
        pcm,log=audio_samples(data)
        for expected in ('h264','1080x1920','30 fps','aac','44100 Hz','stereo'):self.assertIn(expected,log)
        baseline=rms(pcm,.2,.3)
        original=array('h')
        with wave.open(BytesIO(asset.data),'rb') as wav:original.frombytes(wav.readframes(wav.getnframes()))
        self.assertAlmostEqual(baseline/rms(original[::2],.2,.3),.5,delta=.05,msg='相對正規化音樂的50%音量已套用')
        self.assertGreater(rms(pcm,1,1.1)/baseline,.9,'短音樂循環延續')
        self.assertAlmostEqual(rms(pcm,1.75,1.85)/baseline,.5,delta=.08)
        self.assertLess(rms(pcm,2.2,2.25)/baseline,.14,'最後一秒確實漸弱')

    def test_nonloop_fades_at_music_end_without_shortening_comparison(self):
        a,b=photo('before.png','black'),photo('after.png','blue');a.role='before';b.role='after';clip=new_comparison(a,b)
        clip.update(duration=2,before_time=.5,transition_time=.5,labels=[])
        asset=load_music('tone.wav',tone());m={**new_music(),'source':asset.id,'loop':False,'fade_out':.2}
        data=export_video([a,b],360,640,template='compare',comparisons=[clip],music=m,music_asset=asset)
        pcm,log=audio_samples(data)
        self.assertIn('00:00:02.00',log);self.assertGreater(rms(pcm,.1,.2),1800)
        self.assertLess(rms(pcm,.6,.7),5,'短音樂後靜音，但影片繼續')

    def test_music_sync_is_atomic_cache_reused_and_latest_settings_exported(self):
        asset=load_music('tone.wav',tone());p=photo()
        state=dict(photos=[p],editor_session='s',revision=1,music_asset=asset,music={**new_music(),'source':asset.id})
        row=p.metadata();row['duration']=3
        event=dict(session='s',base_revision=1,nonce='bad',action='apply',photos=[row],music={**state['music'],'volume':2})
        consume_editor_event(state,event);self.assertFalse(state['editor_response']['ok']);self.assertEqual(p.duration,2)
        event.update(nonce='good',music={**state['music'],'fade_out':2,'volume':.2})
        consume_editor_event(state,event);self.assertTrue(state['editor_response']['ok']);self.assertEqual(state['music']['fade_out'],2)
        cache={};first=payload([p],cache,music=state['music'],music_asset=asset)
        second=payload([p],cache,music=state['music'],music_asset=asset)
        self.assertIs(first['music_asset'],second['music_asset'])

    def test_streamlit_latest_music_export_remove_and_clear(self):
        app=authenticated_app();next(b for b in app.button if b.label=='載入 5 張測試示意圖').click().run()
        asset=load_music('tone.wav',tone());app.session_state.music_asset=asset
        app.session_state.music={**new_music(),'source':asset.id};app.session_state.project_payload=None
        app.run();self.assertFalse(app.exception)
        self.assertEqual(app.session_state.project_payload['music']['fade_out'],1)
        next(s for s in app.selectbox if s.label=='影片解析度').select(360).run()
        next(b for b in app.button if b.label=='輸出 H.264 MP4').click().run()
        rows=copy.deepcopy([p.metadata() for p in app.session_state.photos[:1]])
        rows[0]['duration']=2;rows[0]['labels']=[]
        request=app.session_state.pending_export
        app.session_state['studio_editor']=dict(nonce='music-export',session=app.session_state.editor_session,
            base_revision=app.session_state.revision,action='export',request=request['id'],photos=rows,
            music={**new_music(),'source':asset.id,'volume':.25,'fade_out':.5})
        app.run();self.assertFalse(app.exception);self.assertEqual(app.session_state.music['fade_out'],.5)
        pcm,log=audio_samples(app.session_state.output);self.assertIn('aac',log);self.assertLess(rms(pcm,.1,.2),1800)
        next(b for b in app.button if b.label=='移除BGM').click().run();self.assertFalse(app.exception)
        self.assertIsNone(app.session_state.music_asset)
        next(b for b in app.button if b.label=='清空目前工作階段').click().run()
        self.assertIsNone(app.session_state.music_asset);self.assertEqual(app.session_state.music['fade_out'],1)


if __name__=='__main__':unittest.main()
