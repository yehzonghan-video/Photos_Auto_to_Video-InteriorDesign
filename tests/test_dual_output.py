"""雙檔輸出：Mock故障與真實ZIP／FFmpeg明確分開，不呼叫Gemini。"""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import json,subprocess,unittest,uuid,zipfile
from unittest.mock import patch

from studio import output_jobs as jobs,versioning as V,downloads
from studio.sync import consume_editor_event
from studio.project_io import load_archive
from studio.project_ui import confirm_backup
from tests.test_project_io import fixture
from tests.test_versions import snapshot
from tests.test_output_flow import start,finish


def pair_event(s,backup=True):
    s['video_width']=360;V.refresh(s)
    e=snapshot(s,uuid.uuid4().hex,'export')
    if s.get('tour') is not None:e['tour']=deepcopy(s['tour'])
    e.update(output_protocol=3,width=360,request=e['nonce'],seq=8,zip_backup=backup)
    e['content_version']=V.digest(V.document(e,V.context(s)))
    consume_editor_event(s,e)
    if not s['editor_response']['ok']:raise AssertionError(s['editor_response'])
    return e


class DualOutputTests(unittest.TestCase):
    def tearDown(self):
        for task in list(jobs._TASKS.values()):
            try:task['future'].result(timeout=90)
            except Exception:pass
        jobs._TASKS.clear()

    def test_same_snapshot_both_results_and_later_edits_not_backed_up(self):
        s=fixture('items');e=pair_event(s);entered=Event();release=Event();calls=[];original=jobs._run
        def run(source,kind,version,progress):
            calls.append((id(source),kind,version,source['photos'][0].labels[0]['text']))
            entered.set();release.wait(5)
            return original(source,kind,version,progress) if kind=='zip' else dict(data=b'mock-mp4',seconds=.1)
        with patch.object(jobs,'_run',side_effect=run):
            start(s,e);self.assertTrue(entered.wait(5))
            s['photos'][0].labels[0]['text']='後續版本B';V.refresh(s);release.set();finish(s)
        self.assertEqual(len(calls),2);self.assertEqual(calls[0][0],calls[1][0]);self.assertEqual(calls[0][2],e['content_version'])
        self.assertNotEqual(calls[1][3],'後續版本B');self.assertEqual(s['zip_version'],s['mp4_version'])
        self.assertNotEqual(s['zip_version'],s['content_version']);self.assertNotIn('backup_confirmed_version',s)
        self.assertEqual(load_archive(s['project_archive']['data'])['photos'][0].labels[0]['text'],calls[0][3])
        rev=s['revision'];consume_editor_event(s,dict(action='downloads_requested',nonce='downloads',session=s['editor_session'],downloads=[dict(kind=k,operation_id=e['nonce'],content_version=e['content_version']) for k in ('mp4','zip')]))
        self.assertEqual(s['revision'],rev);self.assertNotIn('backup_confirmed_version',s)
        confirm_backup(s,e['content_version']);self.assertEqual(s['backup_confirmed_version'],e['content_version']);self.assertNotEqual(s['backup_confirmed_version'],s['content_version'])

    def test_unchecked_only_mp4_no_zip_and_no_revision_for_output_option(self):
        s=fixture('items');s['video_width']=360;rev=s['revision'];V.refresh(s);e=pair_event(s,False)
        self.assertEqual(s['revision'],rev)
        with patch('studio.export.export_video',return_value=b'mock-mp4') as render,patch('studio.project_io.build_archive') as archive:
            start(s,e);finish(s)
        render.assert_called_once();archive.assert_not_called();self.assertEqual(s['output'],b'mock-mp4');self.assertNotIn('project_archive',s)

    def test_independent_failure_matrix_keeps_previous_successes(self):
        for mp4_ok,zip_ok in [(True,False),(False,True),(False,False),(True,True)]:
            with self.subTest(mp4=mp4_ok,zip=zip_ok):
                s=fixture('items');old=V.refresh(s);s.update(output=b'previous-mp4',mp4_version=old,project_archive=dict(data=b'previous-zip',content_version=old),zip_version=old,backup_confirmed_version=old)
                s['photos'][0].labels[0]['text']='本次內容';e=pair_event(s)
                def run(source,kind,version,progress):
                    if not (zip_ok if kind=='zip' else mp4_ok):raise RuntimeError(kind+' simulated failure')
                    return dict(data=b'new-zip',filename='snapshot.zip') if kind=='zip' else dict(data=b'new-mp4',seconds=.1)
                with patch.object(jobs,'_run',side_effect=run):start(s,e);finish(s)
                self.assertEqual(s['output'],b'new-mp4' if mp4_ok else b'previous-mp4')
                self.assertEqual(s['project_archive']['data'],b'new-zip' if zip_ok else b'previous-zip')
                self.assertEqual(s['output_status']['artifacts']['mp4']['phase'],'done' if mp4_ok else 'error')
                self.assertEqual(s['output_status']['artifacts']['zip']['phase'],'done' if zip_ok else 'error')
                self.assertEqual(s['output_status']['phase'],'done' if mp4_ok or zip_ok else 'error')
                self.assertEqual(s['backup_confirmed_version'],old);self.assertEqual(s['photos'][0].labels[0]['text'],'本次內容')

    def test_failed_zip_retry_uses_original_snapshot_and_never_rerenders_mp4(self):
        s=fixture('items');e=pair_event(s)
        with patch('studio.project_io.build_archive',side_effect=ValueError('ZIP故障')),patch('studio.export.export_video',return_value=b'first-mp4'):
            start(s,e);finish(s)
        self.assertTrue(s['output_status']['retry_zip']);s['photos'][0].labels[0]['text']='後續B';V.refresh(s)
        retry=dict(action='retry_output_zip',nonce='retry-fixed',operation_id=e['nonce'],content_version=e['content_version'],session=s['editor_session'])
        with patch('studio.project_io.build_archive',side_effect=ValueError('仍然故障')):
            consume_editor_event(s,retry);finish(s)
        self.assertTrue(s['output_status']['retry_zip'])
        retry.update(nonce='retry-second',operation_id='retry-fixed')
        with patch('studio.export.export_video') as render:
            consume_editor_event(s,retry);consume_editor_event(s,retry);finish(s);render.assert_not_called()
        self.assertNotEqual(load_archive(s['project_archive']['data'])['photos'][0].labels[0]['text'],'後續B')
        self.assertEqual(s['zip_version'],s['mp4_version']);self.assertNotIn('output_retry_zip',s);self.assertEqual(s['output'],b'first-mp4')

    def test_bad_receipts_and_invalid_options_do_not_change_project(self):
        s=fixture('items');e=pair_event(s);version=V.project_version(s)
        consume_editor_event(s,dict(action='downloads_requested',nonce='bad-receipt',session=s['editor_session'],downloads=[{},dict(kind='unknown')]))
        self.assertEqual(V.project_version(s),version);self.assertNotIn('zip_download_requested_version',s)
        consume_editor_event(s,dict(action='retry_output_zip',nonce='bad-retry',operation_id='wrong',session=s['editor_session']))
        self.assertNotIn('output_task',s);self.assertEqual(V.project_version(s),version);jobs.release(s)
        e['nonce']='bad-option';e['request']='bad-option';e['zip_backup']='true';consume_editor_event(s,e)
        self.assertFalse(s['editor_response']['ok']);self.assertNotIn('prepared_output',s)

    def test_short_lived_mp4_and_zip_publication_failure_has_native_fallback(self):
        for static,failed in [(False,False),(True,True),(True,False)]:
            with self.subTest(static=static,failed=failed),TemporaryDirectory() as folder,patch.object(downloads,'ROOT',Path(folder)):
                s=fixture('items');e=pair_event(s)
                def run(source,kind,version,progress):return dict(data=b'zip',filename='x.zip') if kind=='zip' else dict(data=b'mp4',seconds=.1)
                with patch.object(jobs,'_run',side_effect=run):
                    start(s,e)
                    if failed:
                        with patch.object(downloads,'publish',side_effect=OSError('暫存已滿')):finish(s,static)
                    else:finish(s,static)
                for key,kind in [('project_archive','zip'),('mp4_download','mp4')]:
                    a=s[key];self.assertEqual(a['content_version'],e['content_version'])
                    if static and not failed:self.assertTrue(a['url'].endswith('.'+kind));self.assertEqual((Path(folder)/a['artifact']).read_bytes(),kind.encode())
                    else:self.assertIn('download_warning',a)
                self.assertEqual(s['output_status']['phase'],'done');jobs.release(s);self.assertFalse(list(Path(folder).iterdir()))

    def test_real_mp4_zip_all_templates_with_tour_video_media(self):
        from studio.export import ffmpeg_path
        from studio.tour_video import load_video
        from tests.test_tour import project,make_video
        with TemporaryDirectory() as folder:
            folder=Path(folder);v=load_video('walk.mp4',make_video(folder/'source.mp4'))
            for s in [fixture('items'),fixture('compare'),project(v)]:
                with self.subTest(template=s['template_mode']):
                    e=pair_event(s);start(s,e);finish(s)
                    self.assertEqual(s['output_status']['phase'],'done',s['output_status']);self.assertEqual(s['zip_version'],s['mp4_version'])
                    restored=load_archive(s['project_archive']['data']);self.assertEqual(restored['template_mode'],s['template_mode'])
                    with zipfile.ZipFile(BytesIO(s['project_archive']['data'])) as z:self.assertEqual(json.loads(z.read('manifest.json'))['content_version'],e['content_version'])
                    path=folder/(s['template_mode']+'.mp4');path.write_bytes(s['output'])
                    subprocess.run([ffmpeg_path(),'-v','error','-i',str(path),'-f','null','-'],check=True,capture_output=True,timeout=60)
                    if s['template_mode']=='tour':self.assertEqual(restored['video_assets'][v.id].data,v.data);self.assertEqual(restored['floor_plan'].original,s['floor_plan'].original)


if __name__=='__main__':unittest.main()
