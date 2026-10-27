"""快速標題：真JS操作資料、ZIP／FFmpeg往返與AppTest；不呼叫Gemini。"""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json,subprocess,unittest,zipfile
from PIL import Image,ImageChops,ImageStat

from studio import versioning as V,output_jobs as jobs,quick_preview
from studio.cover import validate_cover,title_box
from studio.titles import filename,project_title
from studio.project_io import build_archive,load_archive,install_project
from studio.sync import consume_editor_event
from tests.test_project_io import fixture
from tests.test_versions import snapshot
from tests.test_dual_output import pair_event
from tests.test_output_flow import start,finish


def edit(cover,text='18坪小宅超強收納？'):
    code="""const T=require('./frontend/title-model.js');const c=JSON.parse(require('fs').readFileSync(0,'utf8'));T.ensure(c,'cover',true);T.setText(c,process.argv[1]);T.setBreaks(c,'cover',Array.from(T.title(c)).slice(0,5).join('')+'\\n'+Array.from(T.title(c)).slice(5).join(''));c.shared_title.cover_x=.44;c.shared_title.cover_y=.34;c.font_size=88;c.body.font_size=92;c.body.x=.55;c.body.y=.245;c.highlights=[{start:6,end:10,color:'#ffd34e'}];c.body.highlights=[{start:5,end:9,color:'#00aaff'}];console.log(JSON.stringify(c));"""
    return json.loads(subprocess.run(['node','-e',code,text],input=json.dumps(cover).encode(),check=True,capture_output=True).stdout)


def apply_title(s,c):
    e=snapshot(s,'title-edit');e['cover']=c
    if s.get('tour') is not None:e['tour']=deepcopy(s['tour'])
    e['content_version']=V.digest(V.document(e,V.context(s)));consume_editor_event(s,e)
    if not s['editor_response']['ok']:raise AssertionError(s['editor_response'])
    return e


class QuickTitleTests(unittest.TestCase):
    def test_shared_text_independent_styles_only_cover_data_changes(self):
        s=fixture('items');before=jobs.snapshot(s);c=edit(s['cover']);apply_title(s,c)
        after=jobs.snapshot(s);self.assertEqual({k:v for k,v in before.items() if k!='cover'},{k:v for k,v in after.items() if k!='cover'})
        self.assertEqual(s['cover']['title'].replace('\n',''),s['cover']['body']['title'])
        self.assertEqual(s['cover']['body']['color'],before['cover']['color']);self.assertNotEqual(s['cover']['highlights'],s['cover']['body']['highlights'])
        for key in ('auto_timing','start','end','logo_auto_timing','logo_start','logo_end'):
            self.assertEqual(s['cover']['body'][key],before['cover']['body'][key])

    def test_old_zip_unchanged_new_version_three_roundtrip_and_explicit_ids(self):
        for mode in ('items','compare'):
            s=fixture(mode);old=build_archive(s);loaded=load_archive(old);self.assertNotIn('shared_title',loaded['cover'])
            install_project(s,loaded);old_version=V.refresh(s);apply_title(s,edit(s['cover']));self.assertNotEqual(old_version,V.project_version(s))
            data=build_archive(s)
            with zipfile.ZipFile(BytesIO(data)) as z:self.assertEqual(json.loads(z.read('manifest.json'))['version'],3)
            restored=load_archive(data);self.assertEqual(restored['cover'],s['cover']);self.assertEqual(restored['photos'][0].original,s['photos'][0].original)
            self.assertEqual(restored['cover']['shared_title']['body_id'],'project-body-title')

    def test_cross_language_hash_and_noop_title_sync(self):
        s=fixture('items');apply_title(s,edit(s['cover']));e=snapshot(s,'noop-title');ctx=V.context(s)
        code="const V=require('./frontend/content-version.js');const x=JSON.parse(require('fs').readFileSync(0,'utf8'));console.log(V.digest(V.document(x.data,x.ctx)))"
        actual=subprocess.run(['node','-e',code],input=json.dumps(dict(data=e,ctx=ctx)).encode(),capture_output=True,check=True).stdout.decode().strip()
        self.assertEqual(actual,V.project_version(s));rev=s['revision'];consume_editor_event(s,e);self.assertTrue(s['editor_response']['ok']);self.assertEqual(s['revision'],rev)

    def test_invalid_link_or_breaks_rejected_atomically(self):
        for change in [lambda c:c['shared_title'].update(body_id='ordinary-label'),lambda c:c['shared_title'].update(cover_breaks=[999]),lambda c:c['body'].update(title='不同文字'),lambda c:c['shared_title'].update(cover_x=2)]:
            s=fixture('items');c=edit(s['cover']);change(c);old=V.refresh(s);e=snapshot(s,'bad-title');e['cover']=c;consume_editor_event(s,e)
            self.assertFalse(s['editor_response']['ok']);self.assertEqual(V.project_version(s),old)

    def test_filename_safety_matches_javascript_and_keeps_display(self):
        for raw in ['18坪小宅？','<|?*>',' \n. ','CON','AUX.txt','案例/衛浴\n設計','😀'*100]:
            for kind in ('mp4','zip'):
                actual=subprocess.run(['node','-e',"console.log(require('./frontend/title-model.js').filename(process.argv[1],process.argv[2]))",raw,kind],capture_output=True,check=True).stdout.decode().strip()
                self.assertEqual(filename(raw,kind),actual);self.assertNotIn('/',actual);self.assertNotIn('\n',actual)
        c=edit(fixture()['cover']);original=deepcopy(c);self.assertEqual(filename(project_title(c),'mp4'),'18坪小宅超強收納.mp4');self.assertEqual(c,original)

    def test_original_snapshot_frames_remain_fixed_and_readonly_events_no_revision(self):
        s=fixture('items');quick_preview.capture(s);scene=quick_preview.scenes(s['_quick_original'])[0]
        old_image,_=quick_preview.frame(s['_quick_original'],scene['id']);old_bytes=old_image.tobytes();apply_title(s,edit(s['cover']));rev=s['revision']
        consume_editor_event(s,dict(action='quick_original',nonce='original-preview',session=s['editor_session'],scene_id=scene['id']))
        self.assertEqual(s['revision'],rev);self.assertIn(scene['id'],s['_quick_frames']);self.assertEqual(quick_preview.frame(s['_quick_original'],scene['id'])[0].tobytes(),old_bytes)
        consume_editor_event(s,dict(action='set_edit_mode',nonce='full-view',session=s['editor_session'],mode='full'));self.assertEqual(s['revision'],rev);self.assertEqual(s['edit_mode'],'full')

    def test_body_preview_chooses_actual_visible_span_and_handles_all_templates(self):
        from tests.test_tour import project
        for s in [fixture('items'),fixture('compare'),project()]:
            s['cover']['body'].update(enabled=True,auto_timing=False,start=1.1,end=1.8)
            rows=quick_preview.scenes(s);visible=[r for r in rows if r['id']!='project-cover' and r['visible']]
            self.assertTrue(visible);self.assertTrue(all(1.1<=r['time']<1.8 for r in visible))
            image,row=quick_preview.frame(s,visible[0]['id']);self.assertEqual(image.size,(1080,1920));self.assertEqual(row['id'],visible[0]['id'])

    def test_real_edit_export_both_files_and_reimport_visible_title_changed(self):
        from studio.export import ffmpeg_path
        s=fixture('items');install_project(s,load_archive(build_archive(s)));original=s['_quick_original'];apply_title(s,edit(s['cover']));event=pair_event(s)
        start(s,event);finish(s);self.assertEqual(s['output_status']['phase'],'done');self.assertEqual(s['zip_version'],s['mp4_version'])
        self.assertEqual(s['project_archive']['filename'],'18坪小宅超強收納.zip');self.assertEqual(s['mp4_download']['filename'],'18坪小宅超強收納.mp4')
        restored=load_archive(s['project_archive']['data']);self.assertEqual(restored['cover'],s['cover'])
        with TemporaryDirectory() as folder:
            movie=Path(folder)/'edited.mp4';movie.write_bytes(s['output'])
            subprocess.run([ffmpeg_path(),'-v','error','-i',str(movie),'-f','null','-'],capture_output=True,check=True,timeout=60)
            for ident in ['project-cover',s['photos'][0].id]:
                expected,row=quick_preview.frame(jobs.snapshot(s),ident);before,_=quick_preview.frame(original,ident);t=.1 if ident=='project-cover' else row['time']
                raw=subprocess.run([ffmpeg_path(),'-v','error','-ss',str(t),'-i',str(movie),'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],capture_output=True,check=True,timeout=30).stdout
                actual=Image.open(BytesIO(raw)).convert('RGB');expected=expected.resize(actual.size,Image.Resampling.LANCZOS).convert('RGB');before=before.resize(actual.size,Image.Resampling.LANCZOS).convert('RGB')
                region=(0,100,360,340);distance=lambda im:sum(ImageStat.Stat(ImageChops.difference(actual.crop(region),im.crop(region))).mean)
                self.assertLess(distance(expected),distance(before)*.7)
        self.assertNotEqual(s.get('backup_confirmed_version'),s['content_version'])

    def test_streamlit_quick_import_mode_switch_keeps_project_and_hides_full_controls(self):
        from tests.app_helpers import authenticated_app
        app=authenticated_app();app.radio(key='edit_mode').set_value('quick').run();self.assertFalse(app.exception)
        self.assertFalse(any(s.label=='影片模板' for s in app.selectbox));self.assertEqual(len(app.get('file_uploader')),1)
        data=build_archive(fixture('items'))
        def upload(label,*args,**kwargs):return SimpleNamespace(getvalue=lambda:data) if label=='選擇工作室專案檔' else None
        with patch('studio.project_ui.st.file_uploader',side_effect=upload):
            app.run();next(b for b in app.button if b.label=='匯入並開啟專案').click().run()
        self.assertFalse(app.exception);self.assertIn('_quick_original',app.session_state);rev=app.session_state.revision
        s={k:app.session_state[k] for k in ['photos','cover','overlays','comparisons','comparison_overlays','music','music_asset','overlay_assets','template_mode','video_width','editor_session','revision','tour','floor_plan','video_assets']}
        c=edit(s['cover']);e=snapshot(s,'quick-app-edit');e['cover']=c;e['tour']=s['tour'];e['content_version']=V.digest(V.document(e,V.context(s)))
        app.session_state['studio_editor']=e;app.run();self.assertFalse(app.exception);self.assertEqual(app.session_state.revision,rev+1)
        app.session_state['studio_editor']=dict(action='set_edit_mode',mode='full',session=s['editor_session'],nonce='enter-full');app.run()
        self.assertFalse(app.exception);self.assertEqual(app.session_state.cover['shared_title']['text'],'18坪小宅超強收納？');self.assertEqual(app.session_state.revision,rev+1)
        self.assertTrue(any(s.label=='影片模板' for s in app.selectbox))

    def test_new_title_zip_mp4_and_original_video_preview_for_compare_and_tour(self):
        from studio.export import ffmpeg_path
        from studio.tour_video import load_video
        from tests.test_tour import project,make_video
        with TemporaryDirectory() as folder:
            folder=Path(folder);video=load_video('walk.mp4',make_video(folder/'source.mp4'))
            for s in [fixture('compare'),project(video)]:
                with self.subTest(template=s['template_mode']):
                    s['cover']['body']['enabled']=True;quick_preview.capture(s)
                    rows=quick_preview.scenes(s['_quick_original']);row=next(r for r in rows if r['id']==s['tour']['clips'][1]['id']) if s['template_mode']=='tour' else rows[1]
                    original,_=quick_preview.frame(s['_quick_original'],row['id']);self.assertEqual(original.size,(1080,1920))
                    apply_title(s,edit(s['cover']));e=pair_event(s);start(s,e);finish(s);self.assertEqual(s['output_status']['phase'],'done',s['output_status'])
                    restored=load_archive(s['project_archive']['data']);self.assertEqual(restored['cover'],s['cover']);self.assertEqual(s['mp4_download']['filename'],'18坪小宅超強收納.mp4')
                    path=folder/(s['template_mode']+'.mp4');path.write_bytes(s['output']);subprocess.run([ffmpeg_path(),'-v','error','-i',str(path),'-f','null','-'],capture_output=True,check=True,timeout=60)
                    if s['template_mode']=='tour':self.assertEqual(restored['video_assets'][video.id].data,video.data);self.assertEqual(restored['tour']['rooms'],s['tour']['rooms'])


if __name__=='__main__':unittest.main()
