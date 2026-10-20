"""導覽真素材／ZIP／FFmpeg測試，不呼叫Gemini。"""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,subprocess,unittest,zipfile
from PIL import Image
from studio.tour import new_tour,load_plan,validate_tour,box,plan_layer,LAYOUT
from studio.tour_video import load_video,MAX_VIDEO_BYTES,original_audio
from studio.export import export_video,ffmpeg_path
from studio.project_io import build_archive,load_archive,install_project
from studio.cover import new_cover
from studio import versioning as V,output_jobs
from studio.sync import consume_editor_event
from tests.test_project_io import fixture
from tests.test_versions import snapshot


def plan_bytes(size=(400,240),fmt='PNG'):
    out=BytesIO();Image.new('RGB',size,'white').save(out,fmt);return out.getvalue()


def make_video(path,rate=24,audio=True):
    command=[ffmpeg_path(),'-v','error','-y','-f','lavfi','-i',f"color=red:s=160x90:r={rate}:d=3,drawbox=color=blue:t=fill:enable='gte(t,1)',drawbox=color=green:t=fill:enable='gte(t,2)'"]
    if audio:command+=['-f','lavfi','-i','sine=frequency=660:duration=3','-c:a','aac']
    command+=['-c:v','libx264','-pix_fmt','yuv420p','-shortest',str(path)]
    subprocess.run(command,capture_output=True,check=True,timeout=30);return path.read_bytes()


def clip(source,kind='photo',room='living'):
    return dict(id='clip-'+source.id,type='tour_clip',kind=kind,source=source.id,name=source.name,room_id=room,duration=1.,**{'in':0.,'out':1.},muted=True,volume=1.,crop=dict(fit='contain',zoom=1.,crop_x=.5,crop_y=.5),labels=[])


def project(video=None):
    s=fixture('items');s.update(template_mode='tour',tour=new_tour(),video_assets={},floor_plan=load_plan('plan.png',plan_bytes()),comparisons=[],overlays=[],comparison_overlays=[])
    s['cover']=new_cover();s['cover']['enabled']=False;s['cover']['body'].update(enabled=False,logo_enabled=False)
    s['tour']['rooms']=[dict(id='living',name='客廳',x=.25,y=.5,needs_review=False),dict(id='kitchen',name='廚房',x=.75,y=.5,needs_review=False)]
    s['tour']['clips']=[clip(s['photos'][0])]
    if video:s['video_assets']={video.id:video};c=clip(video,'video','kitchen');c.update(**{'in':1.,'out':2.});s['tour']['clips'].append(c)
    s['tour']['clips'].append(clip(s['photos'][1],room=None));return s


class TourTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory();cls.folder=Path(cls.tmp.name);cls.raw=make_video(cls.folder/'source.mp4');cls.video=load_video('source.mp4',cls.raw)
        cls.silent=load_video('silent.mp4',make_video(cls.folder/'silent.mp4',rate=60,audio=False))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_template_registered_and_old_templates_unchanged(self):
        from studio.rendering import template_config
        self.assertEqual([template_config(k)['id'] for k in ('items','compare','tour')],['items','compare','tour'])

    def test_plan_png_jpeg_sizes_invalid_and_geometry_matches_js(self):
        for size in [(100,100),(600,100),(100,700),(3,2)]:
            for ext,fmt in [('png','PNG'),('jpg','JPEG')]:
                data=plan_bytes(size,fmt);p=load_plan('plan.'+ext,data);self.assertEqual(p.original,data);t=new_tour();t.update(dot_size=24,size=.5);b=box(p,t)
                code="const T=require('./frontend/tour-model.js');console.log(JSON.stringify(T.box(JSON.parse(process.argv[1]),JSON.parse(process.argv[2]))))"
                actual=json.loads(subprocess.run(['node','-e',code,json.dumps(dict(width=p.width,height=p.height)),json.dumps(t)],capture_output=True,check=True).stdout)
                self.assertEqual(actual,b);self.assertGreaterEqual(b['x']-b['pad'],125);self.assertLessEqual(b['x']+b['w']+b['pad'],955)
        for name,data in [('a.webp',b'bad'),('bad.png',b'bad'),('big.png',b'x'*(8*1024*1024+1))]:
            with self.assertRaises(ValueError):load_plan(name,data)

    def test_rooms_unassigned_review_and_coordinate_updates(self):
        s=project();t=validate_tour(s['tour'],s['photos'],{},s['floor_plan']);a=plan_layer(s['floor_plan'],t,'living');none=plan_layer(s['floor_plan'],t,None)
        self.assertNotEqual(a.tobytes(),none.tobytes());t['rooms'][0]['needs_review']=True;self.assertEqual(plan_layer(s['floor_plan'],t,'living').tobytes(),none.tobytes())
        t['rooms'][0].update(needs_review=False,x=.8);self.assertNotEqual(plan_layer(s['floor_plan'],t,'living').tobytes(),a.tobytes());t['rooms'][0]['x']=2
        with self.assertRaises(ValueError):validate_tour(t,s['photos'],{},s['floor_plan'])

    def test_invalid_references_and_trim_fail_atomically(self):
        for mutate in [lambda t:t['clips'][0].update(room_id='missing'),lambda t:t['rooms'].append(dict(t['rooms'][0])),lambda t:t['clips'][1].update(**{'in':2.,'out':1.}),lambda t:t['clips'][0].update(source='missing')]:
            s=project(self.video);old=V.refresh(s);t=deepcopy(s['tour']);mutate(t);event=snapshot(s);event['tour']=t;consume_editor_event(s,event)
            self.assertFalse(s['editor_response']['ok']);self.assertEqual(V.project_version(s),old)

    def test_video_fps_audio_invalid_and_working_copy_roundtrip(self):
        self.assertTrue(self.video.has_audio);self.assertFalse(self.silent.has_audio);self.assertGreaterEqual(self.video.duration,2.9)
        self.assertEqual(load_video('working.mp4',self.video.data,normalized=True).data,self.video.data)
        for name,data in [('bad.mp4',b'broken'),('file.avi',self.raw),('big.mp4',b'x'*(MAX_VIDEO_BYTES+1))]:
            with self.assertRaises(ValueError):load_video(name,data)

    def test_rotation_and_variable_fps_normalize(self):
        rotated=self.folder/'rotated.mp4';subprocess.run([ffmpeg_path(),'-v','error','-y','-display_rotation','90','-i',str(self.folder/'source.mp4'),'-c','copy',str(rotated)],check=True,capture_output=True)
        self.assertEqual((load_video('rotated.mp4',rotated.read_bytes()).width,load_video('rotated.mp4',rotated.read_bytes()).height),(90,160))
        path=self.folder/'vfr.mp4';subprocess.run([ffmpeg_path(),'-v','error','-y','-f','lavfi','-i','testsrc=s=160x90:r=30:d=2','-vf',"select='if(lt(t,1),not(mod(n,2)),1)'",'-fps_mode','vfr','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True,capture_output=True)
        self.assertGreater(load_video('vfr.mp4',path.read_bytes()).duration,1)

    def test_video_verification_timeouts_are_readable_and_preserve_source(self):
        from types import SimpleNamespace
        meta=dict(codec='h264',width=self.video.width,height=self.video.height,fps=30,rotation=0,duration=3,has_audio=True)
        for calls in [[subprocess.TimeoutExpired('ffmpeg',30)],
                      [SimpleNamespace(returncode=0,stdout=b'frame=90'),subprocess.TimeoutExpired('ffmpeg',15)]]:
            with patch('studio.tour_video.probe',return_value=meta.copy()),patch('studio.tour_video.subprocess.run',side_effect=calls):
                with self.assertRaisesRegex(ValueError,'逾時'):load_video('working.mp4',self.video.data,normalized=True)
        self.assertEqual(load_video('working.mp4',self.video.data,normalized=True).data,self.video.data)

    def test_zip_v2_media_once_and_v1_still_readable(self):
        s=project(self.video);s['tour']['clips'].append({**deepcopy(s['tour']['clips'][1]),'id':'reuse'});data=build_archive(s)
        with zipfile.ZipFile(BytesIO(data)) as z:self.assertEqual(len([n for n in z.namelist() if n.startswith('media/videos/')]),1);self.assertEqual(json.loads(z.read('manifest.json'))['version'],2)
        restored=load_archive(data);self.assertEqual(restored['floor_plan'].original,s['floor_plan'].original);self.assertEqual(restored['video_assets'][self.video.id].data,self.video.data);self.assertEqual(restored['tour']['clips'][1]['in'],1)
        old=build_archive(fixture());self.assertEqual(load_archive(old)['template_mode'],'compare')
        with zipfile.ZipFile(BytesIO(old)) as z:self.assertEqual(json.loads(z.read('manifest.json'))['version'],1)

    def test_cross_language_versions_noop_sync_and_snapshot_isolation(self):
        s=project(self.video);V.refresh(s);ctx=V.context(s);event=snapshot(s);event['tour']=deepcopy(s['tour']);code="const V=require('./frontend/content-version.js');const x=JSON.parse(require('fs').readFileSync(0,'utf8'));console.log(V.digest(V.document(x.data,x.ctx)));"
        actual=subprocess.run(['node','-e',code],input=json.dumps(dict(data=event,ctx=ctx)).encode(),capture_output=True,check=True).stdout.decode().strip();self.assertEqual(actual,V.project_version(s))
        rev=s['revision'];event['content_version']=actual;consume_editor_event(s,event);self.assertTrue(s['editor_response']['ok'],s['editor_response']);self.assertEqual(s['revision'],rev)
        a=output_jobs.snapshot(s);version=V.project_version(a);s['tour']['rooms'][0]['x']=.8;V.refresh(s);self.assertEqual(s['revision'],rev+1);self.assertEqual(V.project_version(a),version)

    def test_inactive_room_draft_zip_and_import_reset_upload_events(self):
        s=project();s.update(template_mode='items',floor_plan=None);s['tour']['clips']=[]
        restored=load_archive(build_archive(s));self.assertEqual(restored['tour']['rooms'],s['tour']['rooms'])
        s.update(tour_plan_epoch=4,tour_video_epoch=6,tour_plan_receipt='old-plan',tour_video_receipts=['old-video'])
        install_project(s,restored)
        self.assertEqual((s['tour_plan_epoch'],s['tour_video_epoch']),(5,7))
        self.assertNotIn('tour_plan_receipt',s);self.assertNotIn('tour_video_receipts',s)

    def test_real_full_hd_mixed_trim_room_switch_and_audio_mix(self):
        s=project(self.video);s['tour']['clips'][1]['muted']=False
        data=export_video(s['photos'],1080,1920,template='tour',tour=s['tour'],floor_plan=s['floor_plan'],videos=s['video_assets'],cover=s['cover'],music=s['music'],music_asset=s['music_asset']);path=self.folder/'mixed.mp4';path.write_bytes(data)
        decoded=subprocess.run([ffmpeg_path(),'-v','error','-i',str(path),'-progress','pipe:1','-f','null','-'],capture_output=True,check=True,timeout=60).stdout;self.assertIn(b'frame=90',decoded)
        def frame(t):
            raw=subprocess.run([ffmpeg_path(),'-v','error','-ss',str(t),'-i',str(path),'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],capture_output=True,check=True,timeout=30).stdout;return Image.open(BytesIO(raw)).convert('RGB')
        images=[frame(.5),frame(1.5),frame(2.5)];b=box(s['floor_plan'],s['tour']);x1=round(b['x']+b['w']*.25);x2=round(b['x']+b['w']*.75);y=round(b['y']+b['h']*.5)
        self.assertLess(images[0].getpixel((x1,y))[1],100);self.assertLess(images[1].getpixel((x2,y))[1],100);self.assertGreater(images[1].getpixel((540,960))[2],180);self.assertGreater(images[2].getpixel((x2,y))[1],180)
        raw=subprocess.run([ffmpeg_path(),'-v','error','-i',str(path),'-vn','-ac','1','-ar','8000','-f','f32le','pipe:1'],capture_output=True,check=True,timeout=30).stdout
        import array,math
        audio=array.array('f');audio.frombytes(raw);rms=lambda start:math.sqrt(sum(x*x for x in audio[int(start*8000):int((start+.25)*8000)])/2000);self.assertGreater(rms(1.3),rms(.3)*1.5)

    def test_silent_muted_and_video_only_export_zip(self):
        s=project(self.silent);s['tour']['clips']=[s['tour']['clips'][1]];s['photos']=[];s['tour']['clips'][0]['muted']=False
        data=export_video([],360,640,template='tour',tour=s['tour'],videos=s['video_assets'],floor_plan=s['floor_plan'],cover=s['cover']);self.assertGreater(len(data),1000)
        loaded=load_archive(build_archive(s));self.assertFalse(loaded['photos']);self.assertEqual(len(loaded['tour']['clips']),1);s['tour']['clips'][0]['muted']=True
        with TemporaryDirectory() as folder:self.assertIsNone(original_audio(s['tour']['clips'],s['video_assets'],folder,0))

    def test_tour_zip_and_mp4_protocol3_latest_snapshot_without_apply(self):
        for kind in ('save_project','export'):
            s=project(self.video);V.refresh(s);event=snapshot(s,'tour-'+kind,kind);event['tour']=deepcopy(s['tour']);event['tour']['rooms'][0]['x']=.4
            event.update(output_protocol=3,request=event['nonce'],width=360,seq=9);event['content_version']=V.digest(V.document(event,V.context(s)))
            consume_editor_event(s,event);self.assertTrue(s['editor_response']['ok'],s['editor_response']);version=event['content_version']
            consume_editor_event(s,dict(action='start_output',nonce='start-'+kind,session=s['editor_session'],operation_id=event['nonce'],content_version=version))
            s['tour']['rooms'][0]['x']=.9;V.refresh(s);job=output_jobs._TASKS[s['output_task']['task']];job['future'].result(timeout=90);output_jobs.collect(s)
            self.assertEqual(s['output_status']['phase'],'done');self.assertEqual(s['zip_version' if kind=='save_project' else 'mp4_version'],version)
            if kind=='save_project':self.assertEqual(load_archive(s['project_archive']['data'])['tour']['rooms'][0]['x'],.4)
            else:self.assertGreater(len(s['output']),1000)

    def test_streamlit_plan_only_replace_remove_and_video_intake_replay(self):
        from tests.app_helpers import authenticated_app
        from types import SimpleNamespace
        app=authenticated_app();uploads={}
        def uploader(label,*args,**kwargs):return uploads.get(label,[] if kwargs.get('accept_multiple_files') else None)
        with patch('streamlit.file_uploader',side_effect=uploader):
            uploads['上傳／更換平面圖']=SimpleNamespace(name='plan.png',getvalue=lambda:plan_bytes())
            app.selectbox(key='template_mode').select('tour').run();self.assertFalse(app.exception);self.assertIsNotNone(app.session_state.floor_plan)
            self.assertTrue(app.get('component_instance'))
            app.session_state.tour['rooms']=[dict(id='r',name='房間',x=.2,y=.4,needs_review=False)]
            uploads['上傳／更換平面圖']=SimpleNamespace(name='new.jpg',getvalue=lambda:plan_bytes((100,200),'JPEG'))
            app.run();self.assertFalse(app.exception);self.assertTrue(app.session_state.tour['rooms'][0]['needs_review'])
            uploads['加入MP4影片（自動追加導覽片段）']=[SimpleNamespace(name='walk.mp4',getvalue=lambda:self.raw)]
            app.run();self.assertFalse(app.exception);self.assertEqual(len(app.session_state.video_assets),1);rev=app.session_state.revision
            app.run();self.assertEqual(len(app.session_state.video_assets),1);self.assertEqual(app.session_state.revision,rev)
            uploads.pop('上傳／更換平面圖')
            next(b for b in app.button if b.label=='移除平面圖（保留房名與片段）').click().run();self.assertFalse(app.exception);self.assertIsNone(app.session_state.floor_plan);self.assertEqual(len(app.session_state.tour['rooms']),1)


if __name__=='__main__':unittest.main()
