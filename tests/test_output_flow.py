"""第三階段固定快照／握手／背景工作測試；Mock渲染與真ZIP分開。"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from unittest.mock import patch

from studio import output_jobs as jobs, versioning as V, downloads
from studio.sync import consume_editor_event
from studio.project_io import load_archive
from studio.project_ui import confirm_backup, download_requested
from tests.test_project_io import fixture
from tests.test_versions import snapshot


def prepare(state,kind='zip',nonce='request',text=None):
    V.refresh(state)
    event=snapshot(state,nonce,'save_project' if kind=='zip' else 'export')
    if text:event['photos'][0]['labels'][0]['text']=text
    event.update(output_protocol=3,width=state.get('video_width',1080),request=nonce,seq=20)
    event['content_version']=V.digest(V.document(event,V.context(state)))
    consume_editor_event(state,event)
    return event


def start(state,event,nonce='start'):
    consume_editor_event(state,dict(action='start_output',nonce=nonce,session=state['editor_session'],
        operation_id=event['nonce'],content_version=event['content_version']))


def finish(state,static_enabled=False):
    task=jobs._TASKS[state['output_task']['task']]
    try:task['future'].result(timeout=90)
    except (RuntimeError,ValueError,OSError):pass
    jobs.collect(state,static_enabled)


class OutputFlowTests(unittest.TestCase):
    def tearDown(self):
        for task in list(jobs._TASKS.values()):
            try:task['future'].result(timeout=10)
            except Exception:pass
        jobs._TASKS.clear()

    def test_zip_latest_text_without_apply_roundtrip_and_unchanged_revision(self):
        s=fixture();V.refresh(s);rev=s['revision'];event=prepare(s,text='客廳設計')
        self.assertTrue(s['editor_response']['ok']);self.assertNotIn('output_task',s)
        self.assertEqual(s['editor_response']['content_version'],event['content_version'])
        self.assertEqual(s['revision'],rev+1)
        start(s,event);finish(s)
        loaded=load_archive(s['project_archive']['data'])
        self.assertEqual(loaded['photos'][0].labels[0]['text'],'客廳設計')
        self.assertEqual(s['zip_version'],event['content_version']);self.assertNotIn('backup_confirmed_version',s)
        rev=s['revision'];again=prepare(s,nonce='again');start(s,again,'start-again');finish(s)
        self.assertEqual(s['revision'],rev)

    def test_zip_work_isolated_from_later_text_media_and_music(self):
        s=fixture();event=prepare(s,text='客廳設計');fixed=s['prepared_output']['snapshot'];revision=s['revision']
        s['photos'][0].labels[0]['text']='現代客廳設計'
        s['photos'][0].original=b'not-in-A'
        s['music_asset'].name='new-music.wav'
        s['revision']+=1
        self.assertEqual(fixed['photos'][0].labels[0]['text'],'客廳設計')
        self.assertNotEqual(fixed['photos'][0].original,s['photos'][0].original)
        self.assertNotEqual(fixed['music_asset'].name,s['music_asset'].name)
        start(s,event);finish(s)
        self.assertEqual(s['project_archive']['revision'],revision)
        self.assertEqual(load_archive(s['project_archive']['data'])['photos'][0].labels[0]['text'],'客廳設計')

    def test_mock_render_snapshot_preserves_latest_photo_and_older_output_until_success(self):
        s=fixture();old=V.refresh(s);s.update(output=b'old-mp4',mp4_version=old,output_seconds=1)
        from tests.test_photo_intake import upload
        s['photos'][0].original=upload(color='green').getvalue()
        event=prepare(s,'mp4',text='影片A');entered=Event();release=Event();seen=[]
        def render(source,kind,version,progress):
            seen.append((source['photos'][0].original,source['photos'][0].labels[0]['text']))
            entered.set();release.wait(5);return dict(data=b'mocked-new-mp4',seconds=.1)
        with patch('studio.output_jobs._run',side_effect=render) as mock:
            start(s,event);self.assertTrue(entered.wait(5));self.assertEqual(s['output'],b'old-mp4')
            s['photos'][0].labels[0]['text']='影片B';V.refresh(s)
            start(s,event,'repeat-start');self.assertEqual(mock.call_count,1)
            release.set();finish(s)
        self.assertEqual(seen[0][0],upload(color='green').getvalue());self.assertEqual(seen[0][1],'影片A')
        self.assertEqual(s['mp4_version'],event['content_version']);self.assertNotEqual(s['mp4_version'],s['content_version'])
        self.assertEqual(s['output'],b'mocked-new-mp4')

    def test_failed_render_or_zip_keeps_all_previous_successes(self):
        for kind in ('zip','mp4'):
            s=fixture();old=V.refresh(s);s.update(output=b'old-mp4',mp4_version=old,
                project_archive=dict(data=b'old-zip',content_version=old),zip_version=old)
            event=prepare(s,kind,text='新草稿')
            with patch('studio.output_jobs._run',side_effect=RuntimeError('模擬輸出失敗')):
                start(s,event);finish(s)
            self.assertEqual(s['output'],b'old-mp4');self.assertEqual(s['project_archive']['data'],b'old-zip')
            self.assertEqual(s['output_status']['phase'],'error');self.assertFalse(s['editor_busy'])
            self.assertEqual(s['photos'][0].labels[0]['text'],'新草稿')

    def test_wrong_hash_ack_start_replay_and_cancel_are_safe(self):
        s=fixture();V.refresh(s);old=s['content_version'];bad=prepare(s,text='A')
        # 錯版本start不能啟動；使用者可重新要求一次新的同步。
        consume_editor_event(s,dict(action='start_output',nonce='wrong',session=s['editor_session'],
            operation_id=bad['nonce'],content_version='wrong-version'))
        self.assertNotIn('output_task',s)
        event=prepare(s,nonce='retry',text='B')
        consume_editor_event(s,dict(action='cancel_output',nonce='cancel',session=s['editor_session'],operation_id='retry'))
        self.assertNotIn('prepared_output',s)
        event=prepare(s,nonce='final',text='C');before=s['revision']
        consume_editor_event(s,event);self.assertEqual(s['revision'],before)
        with patch('studio.output_jobs._run',return_value=dict(data=b'zip',filename='project.zip')) as run:
            start(s,event);start(s,event);finish(s)
            self.assertEqual(run.call_count,1)
        self.assertNotEqual(s['content_version'],old)

    def test_confirm_A_after_B_only_marks_A_backed_up_and_download_does_not_change_revision(self):
        s=fixture();event=prepare(s);start(s,event);finish(s);rev=s['revision'];version=event['content_version']
        self.assertNotIn('backup_confirmed_version',s)
        download_requested(s,version);self.assertEqual(s['revision'],rev)
        s['photos'][0].labels[0]['text']='版本B';V.refresh(s);current=s['content_version']
        confirm_backup(s,version);self.assertEqual(s['backup_confirmed_version'],version)
        self.assertNotEqual(current,version)

    def test_snapshot_and_download_metadata_contain_no_secret_or_runtime_state(self):
        s=fixture();s.update(APP_PASSWORD='not-for-export',GEMINI_API_KEY='not-for-export')
        source=jobs.snapshot(s);self.assertNotIn('APP_PASSWORD',source);self.assertNotIn('GEMINI_API_KEY',source)
        self.assertNotIn('editor_session',source)

    def test_static_binary_publication_atomic_ttl_budget_and_path_safety(self):
        with TemporaryDirectory() as folder,patch.object(downloads,'ROOT',Path(folder)):
            asset=downloads.publish(b'PK-binary','nested-app')
            self.assertTrue(asset['url'].startswith('/nested-app/app/static/downloads/'))
            self.assertEqual((Path(folder)/asset['artifact']).read_bytes(),b'PK-binary')
            self.assertFalse(list(Path(folder).glob('*.part')))
            downloads.revoke({'artifact':'../unrelated.zip'});self.assertTrue((Path(folder)/asset['artifact']).exists())
            downloads.cleanup(time.time()+downloads.TTL+1);self.assertFalse((Path(folder)/asset['artifact']).exists())
            with patch.object(downloads,'MAX_DISK',2):
                with self.assertRaises(OSError):downloads.publish(b'too-large')

    def test_real_background_mp4_uses_changed_photo_at_click_not_later_photo(self):
        from tests.test_photo_intake import upload
        from studio.export import ffmpeg_path
        from PIL import Image
        from io import BytesIO
        import subprocess
        s=fixture('items');s['photos'][0].original=upload(color='green').getvalue()
        event=prepare(s,'mp4');s['photos'][0].original=upload(color='blue').getvalue();V.refresh(s)
        start(s,event);finish(s)
        self.assertEqual(s['output_status']['phase'],'done');self.assertGreater(len(s['output']),1000)
        with TemporaryDirectory() as folder:
            path=Path(folder)/'snapshot.mp4';path.write_bytes(s['output'])
            result=subprocess.run([ffmpeg_path(),'-v','error','-ss','1.2','-i',str(path),'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],capture_output=True,check=True,timeout=30)
            pixel=Image.open(BytesIO(result.stdout)).convert('RGB').getpixel((180,320))
            self.assertGreater(pixel[1],100);self.assertLess(pixel[2],20)
        self.assertEqual(s['mp4_version'],event['content_version']);self.assertNotEqual(s['content_version'],s['mp4_version'])

    def test_app_new_zip_handshake_no_apply_and_backup_A_after_B(self):
        from tests.app_helpers import authenticated_app,output_controls
        app=authenticated_app();next(b for b in app.button if b.label=='載入 5 張測試示意圖').click().run()
        s={k:app.session_state[k] for k in ('photos','cover','music','music_asset','overlay_assets','overlays',
            'comparisons','comparison_overlays','template_mode','video_width','editor_session','revision')}
        V.refresh(s);event=snapshot(s,'new-output','save_project');event['photos'][0]['labels'][0]['text']='下載當下A'
        event.update(output_protocol=3,width=s['video_width'],request='new-output',seq=30)
        event['content_version']=V.digest(V.document(event,V.context(s)))
        app.session_state['studio_editor']=event;app.run();self.assertFalse(app.exception)
        self.assertEqual(app.session_state.editor_response['operation_id'],'new-output')
        self.assertFalse(output_controls(app)['locked'])
        app.session_state.photos[0].labels[0]['text']='後來B'
        app.session_state['studio_editor']=dict(action='start_output',nonce='start-new',operation_id='new-output',
            content_version=event['content_version'],session=s['editor_session'])
        app.run();self.assertFalse(app.exception)
        try:active=app.session_state['output_task']
        except KeyError:active=None
        if active:
            jobs._TASKS[active['task']]['future'].result(timeout=90);app.run()
        self.assertFalse(app.exception);archive=app.session_state.project_archive
        self.assertEqual(load_archive(archive['data'])['photos'][0].labels[0]['text'],'下載當下A')
        self.assertEqual(app.session_state.photos[0].labels[0]['text'],'後來B')
        app.session_state['studio_editor']=dict(action='zip_download_requested',nonce='download-meta',operation_id='new-output',
            content_version=event['content_version'],session=s['editor_session'])
        app.run();next(b for b in app.button if b.label=='我已確認此版本ZIP已儲存').click().run()
        self.assertEqual(app.session_state.backup_confirmed_version,event['content_version'])
        self.assertNotEqual(app.session_state.backup_confirmed_version,app.session_state.content_version)
        downloads.revoke(archive)


if __name__=='__main__':unittest.main()
