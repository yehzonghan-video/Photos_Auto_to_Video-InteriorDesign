"""專案ZIP真實素材往返、驗證、工作階段及匯入後MP4；AI不呼叫外部API。"""
import copy
from contextlib import nullcontext
from dataclasses import asdict
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import subprocess
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave
import warnings
import zipfile
import zlib

from PIL import Image
import streamlit as st
from studio.models import load_photo, new_label
from studio.cover import new_cover
from studio.music import new_music, MusicAsset
from studio.overlays import load_asset
from studio.comparison import new_comparison
from studio.sync import consume_editor_event
from studio.project_io import build_archive, load_archive, install_project, archive_filename, MAX_ARCHIVE_BYTES
from studio.project_ui import prepare_download
from studio.export import export_video, ffmpeg_path
from tests.app_helpers import authenticated_app


def fixture(template='compare'):
    photos=[]
    for role,color in (('before','#935533'),('after','#336688')):
        out=BytesIO();Image.new('RGB',(320,180),color).save(out,'PNG')
        p=load_photo(role+'.png',out.getvalue());p.role=role;p.duration=2;p.zoom=1.4;p.crop_x=.7
        l=new_label(2);l.update(text='可修改標籤',start=.2,enter=.2,layer=12)
        p.labels=[l];photos.append(p)
    photos[1].labels[0].update(source='gemini',description='可見櫃體外觀',category='收納',confidence_level='中',needs_review=True,ai_item_id='confirmed-item')
    out=BytesIO();im=Image.new('RGBA',(60,40),(0,0,0,0));im.paste((255,210,0,170),(5,5,50,35));im.save(out,'PNG')
    a=load_asset('透明公司LOGO.png',out.getvalue())
    layer=dict(id='layer',type='png',source=a.id,start=1.5,duration=2.1,x=.6,y=.7,width=.3,
               scale=1.2,rotation=23,opacity=.7,layer=30,animation='left',exit_animation='fade',enter=.4,exit=.5)
    cover=new_cover();cover.update(title='老屋88萬',highlights=[dict(start=2,end=4,color='#ffd34e')])
    cover['body'].update(x=.4,y=.245,font_size=112,auto_timing=False,start=.5,end=3.9,
                         logo_auto_timing=False,logo_start=.9,logo_end=3.8)
    sound=BytesIO()
    with wave.open(sound,'wb') as wav:
        wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(44100)
        pcm=bytearray()
        for index in range(4410):
            sample=round(8192*math.sin(2*math.pi*440*index/44100));pcm.extend(struct.pack('<hh',sample,sample))
        wav.writeframes(pcm)
    blob=sound.getvalue();music_asset=MusicAsset('music-'+sha256(blob).hexdigest()[:32],'自己的音樂.mp3',blob,.1,True)
    clips=[new_comparison(*photos),new_comparison(*photos)]
    clips[0].update(mode='reveal',direction='rtl',before_time=.7,transition_time=.8)
    other={**layer,'id':'comparison-layer','start':4.5,'duration':2}
    state=dict(photos=photos,overlay_assets={a.id:a},music_asset=music_asset,template_mode=template,
               video_width=360,editor_session='fixture',revision=1)
    consume_editor_event(state,dict(session='fixture',base_revision=1,nonce='initial',action='apply',
        photos=[p.metadata() for p in photos],cover=cover,music={**new_music(),'source':music_asset.id,'volume':.25,'fade_out':2},
        comparisons=clips,overlays=[layer],comparison_overlays=[other]))
    assert state['editor_response']['ok'],state['editor_response']
    return state


def rewrite(data, change=None, extra=None):
    out=BytesIO()
    with zipfile.ZipFile(BytesIO(data)) as original,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as target:
        manifest=json.loads(original.read('manifest.json'))
        if change:change(manifest)
        for name in original.namelist():
            target.writestr(name,json.dumps(manifest,ensure_ascii=False).encode('utf-8') if name=='manifest.json' else original.read(name))
        if extra:target.writestr(*extra)
    return out.getvalue()


class ProjectIOTests(unittest.TestCase):
    def test_roundtrip_all_media_settings_both_templates_and_ai_labels(self):
        for template in ('items','compare'):
            with self.subTest(template=template):
                state=fixture(template);state['API_KEY']='must-not-be-in-archive';state['_access_verified']='private-login'
                data=build_archive(state);restored=load_archive(data)
                self.assertEqual([p.metadata() for p in restored['photos']],[p.metadata() for p in state['photos']])
                self.assertEqual([p.original for p in restored['photos']],[p.original for p in state['photos']])
                for key in ('overlays','comparison_overlays','comparisons','cover','music','template_mode','video_width'):
                    self.assertEqual(restored[key],state[key],key)
                # Cloud熱更新可留下舊dataclass類別；比較完整欄位與bytes，不依賴類別身分。
                self.assertEqual(asdict(restored['music_asset']),asdict(state['music_asset']))
                for ident,asset in state['overlay_assets'].items():
                    self.assertEqual(asdict(restored['overlay_assets'][ident]),asdict(asset))
                with zipfile.ZipFile(BytesIO(data)) as bundle:
                    raw=bundle.read('manifest.json');manifest=json.loads(raw)
                    self.assertNotIn(b'must-not-be-in-archive',raw);self.assertNotIn(b'private-login',raw)
                    self.assertNotIn('editor_session',manifest)
                    self.assertEqual(len(bundle.namelist()),5)
                self.assertEqual(load_archive(build_archive({**state,**restored}))['photos'][0].labels[0]['start'],.2)

    def test_invalid_archive_versions_hashes_references_and_settings(self):
        data=build_archive(fixture())
        changes=[lambda m:m.update(version=99),lambda m:m['photos'][0].update(sha256='wrong'),
                 lambda m:m['comparisons'][0].update(after_id='not-a-photo'),
                 lambda m:m['photos'][0]['labels'][0].update(x=float('nan')),
                 lambda m:m['photos'][0].update(file='../outside.png'),
                 lambda m:m['photos'][1].update(id=m['photos'][0]['id']),
                 lambda m:m['music'].update(source='missing'),lambda m:m['video'].update(fps=60)]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):load_archive(rewrite(data,change))
        for raw in (b'',b'not zip',rewrite(data,extra=('../escape.txt',b'bad')),
                    rewrite(data,extra=('unknown.txt',b'bad'))):
            with self.subTest(raw_size=len(raw)),self.assertRaises(ValueError):load_archive(raw)
        with patch.object(zipfile.ZipFile,'read',side_effect=zlib.error('bad compressed data')),self.assertRaises(ValueError):
            load_archive(data)
        with patch('studio.project_io.Image.open',side_effect=Image.DecompressionBombError('unsafe image')),self.assertRaises(ValueError):
            load_archive(data)

    def test_missing_files_duplicate_entries_and_declared_expansion_limit(self):
        data=build_archive(fixture());out=BytesIO()
        with zipfile.ZipFile(BytesIO(data)) as original,zipfile.ZipFile(out,'w') as target:
            for name in original.namelist():
                if not name.startswith('media/photos/'):target.writestr(name,original.read(name))
        with self.assertRaises(ValueError):load_archive(out.getvalue())
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            duplicate=rewrite(data,extra=('manifest.json',b'{}'))
        with self.assertRaisesRegex(ValueError,'重複'):load_archive(duplicate)
        # 不建立巨型檔案，模擬ZIP目錄宣告值驗證讀取前的資源限制。
        original_infos=zipfile.ZipFile.infolist
        def huge(bundle):
            infos=original_infos(bundle);infos[0].file_size=MAX_ARCHIVE_BYTES+1;return infos
        with patch.object(zipfile.ZipFile,'infolist',huge),self.assertRaisesRegex(ValueError,'解壓後'):
            load_archive(data)
        with self.assertRaisesRegex(ValueError,'版本'):
            load_archive(rewrite(data,lambda m:m.update(version=True)))

    def test_install_starts_new_session_keeps_quota_login_and_saved_times(self):
        restored=load_archive(build_archive(fixture()))
        state=dict(editor_session='old-session',revision=20,ai_calls=17,_access_verified='login-token',
                   pending_export={'id':'stale'},render_job={},studio_editor={'nonce':'old'},
                   ai_queue=[{'id':'stale'}],uploader_epoch=2)
        install_project(state,restored)
        self.assertNotEqual(state['editor_session'],'old-session');self.assertEqual(state['revision'],21)
        self.assertEqual(state['ai_calls'],17);self.assertEqual(state['_access_verified'],'login-token')
        self.assertNotIn('studio_editor',state);self.assertNotIn('render_job',state)
        self.assertEqual(state['ai_queue'],[]);self.assertIsNone(state['pending_export'])
        self.assertEqual(state['photos'][0].labels[0]['start'],.2)
        self.assertNotIn('/',archive_filename('abc/def\n案例'))

    def test_save_nonce_is_once_and_unchanged_project_keeps_existing_mp4(self):
        state=fixture();state.update(output=b'existing-mp4',output_seconds=2)
        event=dict(session=state['editor_session'],base_revision=state['revision'],nonce='save',action='save_project',
                   photos=[p.metadata() for p in state['photos']])
        revision=state['revision'];consume_editor_event(state,event)
        self.assertTrue(state['editor_response']['ok']);self.assertTrue(state.pop('project_save_job'))
        self.assertEqual(state['output'],b'existing-mp4')
        consume_editor_event(state,event);self.assertNotIn('project_save_job',state);self.assertEqual(state['revision'],revision+1)

    def test_pack_failure_reports_failed_ack_and_keeps_applied_edits(self):
        state=fixture();state.update(project_save_job=True,editor_response={'nonce':'save','ok':True})
        before=[p.metadata() for p in state['photos']]
        with patch('studio.project_ui.st.spinner',return_value=nullcontext()),patch('studio.project_ui.build_archive',side_effect=MemoryError):
            prepare_download(state)
        self.assertFalse(state['editor_response']['ok']);self.assertEqual(state['editor_response']['nonce'],'save')
        self.assertTrue(state['notice_error']);self.assertIsNone(state['project_archive'])
        self.assertEqual([p.metadata() for p in state['photos']],before)

    def test_real_mp4_decoded_frames_and_audio_match_after_archive_import(self):
        state=fixture();restored=load_archive(build_archive(state))
        def render(project):
            return export_video(project['photos'],360,640,template='compare',comparisons=project['comparisons'],
                cover=project['cover'],overlays=project['comparison_overlays'],assets=project['overlay_assets'],
                music=project['music'],music_asset=project['music_asset'])
        with tempfile.TemporaryDirectory(prefix='project-roundtrip-') as folder:
            hashes=[]
            for index,project in enumerate((state,restored)):
                path=Path(folder)/f'{index}.mp4';path.write_bytes(render(project))
                result=subprocess.run([ffmpeg_path(),'-v','error','-i',str(path),'-map','0','-f','framemd5','-'],capture_output=True,check=True,timeout=60)
                hashes.append([line for line in result.stdout.splitlines() if not line.startswith(b'#')])
            self.assertGreater(len(hashes[0]),300);self.assertEqual(hashes[0],hashes[1])

    def test_streamlit_saves_latest_snapshot_and_does_not_repack_on_rerun(self):
        app=authenticated_app()
        next(b for b in app.button if b.label=='載入 5 張測試示意圖').click().run()
        rows=copy.deepcopy([p.metadata() for p in app.session_state.photos])
        rows[0]['labels'][0].update(text='儲存時最新內容',x=.66)
        app.session_state['studio_editor']=dict(session=app.session_state.editor_session,
            base_revision=app.session_state.revision,nonce='save-project',action='save_project',photos=rows)
        app.run();self.assertFalse(app.exception)
        saved=app.session_state.project_archive['data'];restored=load_archive(saved)
        self.assertEqual(restored['photos'][0].labels[0]['text'],'儲存時最新內容')
        self.assertEqual(restored['photos'][0].labels[0]['x'],.66)
        self.assertTrue(any(e.proto.label=='下載專案檔 ZIP（含素材）' for e in app.get('download_button')))
        app.run();self.assertFalse(app.exception);self.assertEqual(app.session_state.project_archive['data'],saved)

    def test_streamlit_import_restores_template_width_and_rejects_bad_file_atomically(self):
        # AppTest尚不支援上傳；只模擬UploadedFile來源，其餘匯入按鈕與工作階段用真實程式。
        app=authenticated_app();data=build_archive(fixture());real_upload=st.file_uploader
        supplied=[data]
        def upload(label,*args,**kwargs):
            if label=='選擇工作室專案檔':return SimpleNamespace(getvalue=lambda:supplied[0])
            return real_upload(label,*args,**kwargs)
        with patch('studio.project_ui.st.file_uploader',side_effect=upload):
            app.run();next(b for b in app.button if b.label=='匯入並開啟專案').click().run()
            self.assertFalse(app.exception);self.assertEqual(app.session_state.template_mode,'compare')
            self.assertEqual(app.session_state.video_width,360)
            self.assertEqual(app.session_state.photos[0].labels[0]['start'],.2)
            ids=[p.id for p in app.session_state.photos];session=app.session_state.editor_session
            supplied[0]=b'corrupt';next(b for b in app.button if b.label=='匯入並開啟專案').click().run()
            self.assertFalse(app.exception);self.assertEqual(app.session_state.editor_session,session)
            self.assertEqual([p.id for p in app.session_state.photos],ids);self.assertTrue(app.error)
