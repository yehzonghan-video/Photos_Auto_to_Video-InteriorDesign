"""封面、局部字色、細黑描邊與真正Full HD片頭影格。"""
import copy
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from PIL import Image, ImageChops, ImageStat
from studio.cover import new_cover,validate_cover,title_colors,title_tile,cover_frame,LAYOUT
from studio.body import body_layer
from studio.models import load_photo,new_label
from studio.export import export_video,ffmpeg_path
from studio.rendering import label_tile,crop_photo,render_frame
from studio.comparison import new_comparison
from studio.overlays import load_asset
from studio.sync import consume_editor_event
from tests.app_helpers import authenticated_app


def photo(name='case.png',color='red',size=(300,100)):
    buffer=BytesIO();Image.new('RGB',size,color).save(buffer,'PNG');p=load_photo(name,buffer.getvalue());p.duration=1;return p


class CoverTests(unittest.TestCase):
    def test_running_half_second_project_updates_png_times_only_once(self):
        app=authenticated_app()
        next(b for b in app.button if b.label=='載入 5 張測試示意圖').click().run()
        app.session_state.cover_version=1;app.session_state.cover_duration=.5
        source=next(iter(app.session_state.overlay_assets))
        overlay=dict(id='old-cover-png',type='png',source=source,start=1,duration=1,x=.5,y=.5,
                     width=.2,scale=1,rotation=0,opacity=1,layer=20,animation='none',exit_animation='none',enter=0,exit=0)
        app.session_state.overlays=[overlay]
        app.run();self.assertFalse(app.exception)
        self.assertAlmostEqual(app.session_state.overlays[0]['start'],.8)
        self.assertEqual(app.session_state.project_payload['cover_assets']['layout']['duration'],.3)
        app.run();self.assertFalse(app.exception)
        self.assertAlmostEqual(app.session_state.overlays[0]['start'],.8,'rerun不能再次扣除片頭差額')

    def test_ranges_validation_and_photo_source(self):
        p=photo();raw={**new_cover(),'title':'老屋88萬','highlights':[dict(start=2,end=4,color='#ff0000')]}
        c=validate_cover(raw,[p]);self.assertEqual(c['photo_id'],p.id)
        self.assertEqual(title_colors(c),['#ffffff','#ffffff','#ff0000','#ff0000','#ffffff'])
        for change in ({'photo_id':'missing'},{'font_size':999},{'title':'\n'*7},{'highlights':[dict(start=1,end=99,color='#ff0000')]},{'highlights':[dict(start=True,end=2,color='#ff0000')]}):
            with self.subTest(change=change),self.assertRaises(ValueError):validate_cover({**raw,**change},[p])
        self.assertEqual(validate_cover({**raw,'enabled':False,'photo_id':'missing'},[])['photo_id'],'')

    def test_title_fits_safe_area_outline_and_complete_landscape_photo(self):
        p=photo();c=validate_cover({**new_cover(),'title':'老屋翻新\n最低88萬起','highlights':[dict(start=7,end=9,color='#ff0000')]},[p])
        tile=title_tile(c);bbox=tile.getbbox();self.assertGreaterEqual(bbox[0],0);self.assertLessEqual(bbox[2],LAYOUT['title']['width']);self.assertLessEqual(bbox[3],LAYOUT['title']['height'])
        self.assertTrue(any(r>200 and g<80 and b<80 and a>0 for r,g,b,a in tile.get_flattened_data()),'部分文字真正改色')
        self.assertTrue(any(r==g==b==0 and a>100 for r,g,b,a in tile.get_flattened_data()),'文字含細黑描邊')
        frame=cover_frame(c,[p]);self.assertEqual(frame.size,(1080,1920))
        box=LAYOUT['photo'];self.assertEqual(frame.getpixel((540,box['y']+3))[:3],(0,0,0));self.assertEqual(frame.getpixel((540,box['y']+box['height']//2))[:3],(255,0,0))
        # 普通影片文字也要有黑色描邊，背景仍透明。
        label=new_label(1);label.update(text='文字',opacity=0,line=False)
        ordinary=label_tile(label);self.assertEqual(ordinary.getpixel((0,0))[3],0)
        self.assertTrue(any(r==g==b==0 and a>100 for r,g,b,a in ordinary.get_flattened_data()))

    def test_real_comparison_cover_and_png_use_same_global_clock(self):
        before=photo('b.png','black',(108,192));before.role='before'
        after=photo('a.png','blue',(108,192));after.role='after';photos=[before,after]
        clip=new_comparison(before,after);clip.update(duration=1,before_time=.2,transition_time=.3,labels=[])
        cover=validate_cover(new_cover(),photos)
        buffer=BytesIO();Image.new('RGBA',(100,100),'#00ff00').save(buffer,'PNG');asset=load_asset('clock.png',buffer.getvalue())
        o=dict(id='o',type='png',source=asset.id,start=.6,duration=.3,x=.5,y=.75,width=.1,scale=1,rotation=0,opacity=1,layer=20,animation='none',exit_animation='none',enter=0,exit=0)
        data=export_video(photos,template='compare',comparisons=[clip],cover=cover,overlays=[o],assets={asset.id:asset})
        with tempfile.TemporaryDirectory(prefix='cover-clock-') as folder:
            path=Path(folder)/'case.mp4';path.write_bytes(data)
            for n,expected in ((8,(0,0,255)),(9,(0,0,0)),(18,(0,255,0)),(30,(0,0,255))):
                target=Path(folder)/f'{n}.png'
                subprocess.run([ffmpeg_path(),'-y','-i',str(path),'-vf',f'select=eq(n\\,{n})','-frames:v','1',str(target)],capture_output=True,check=True,timeout=60)
                with Image.open(target) as image:
                    self.assertLess(max(abs(a-b) for a,b in zip(image.convert('RGB').getpixel((540,1440)),expected)),8)

    def test_invalid_cover_rolls_back_entire_sync_and_good_cover_is_batched(self):
        p=photo();state=dict(photos=[p],comparisons=[],overlays=[],comparison_overlays=[],overlay_assets={},editor_session='s',revision=1)
        row=p.metadata();row['duration']=2
        event=dict(nonce='bad',session='s',base_revision=1,action='apply',photos=[row],cover={**new_cover(),'photo_id':'missing'})
        consume_editor_event(state,event);self.assertFalse(state['editor_response']['ok']);self.assertEqual(p.duration,1)
        event.update(nonce='good',cover={**new_cover(),'photo_id':p.id});consume_editor_event(state,event)
        self.assertTrue(state['editor_response']['ok']);self.assertEqual(state['cover']['photo_id'],p.id);self.assertEqual(p.duration,2)
        second=photo('second.png','blue');state['photos'].append(second)
        consume_editor_event(state,dict(nonce='old-client-delete',session='s',base_revision=2,action='apply',photos=[second.metadata()]))
        self.assertTrue(state['editor_response']['ok']);self.assertEqual(state['cover']['photo_id'],second.id)

    def test_real_full_hd_first_nine_frames_cover_then_original_scene(self):
        p=photo(size=(108,192));c=validate_cover({**new_cover(),'title':'翻新88萬','highlights':[dict(start=2,end=4,color='#ffff00')]},[p])
        label=new_label(1);label.update(text='施工後',start=0,end=1,enter=0,animation='none',opacity=0,line=False);p.labels=[label]
        data=export_video([p],cover=c)
        with tempfile.TemporaryDirectory(prefix='cover-mp4-') as folder:
            video=Path(folder)/'case.mp4';video.write_bytes(data)
            result=subprocess.run([ffmpeg_path(),'-i',str(video),'-f','null','-'],capture_output=True,timeout=60)
            self.assertEqual(result.returncode,0);log=result.stderr.decode('utf-8',errors='replace')
            for value in ('h264','1080x1920','30 fps','00:00:01.30'):self.assertIn(value,log)
            self.assertRegex(log,r'frame=\s*39')
            select='+'.join(f'eq(n\\,{n})' for n in (0,8,9,24))
            subprocess.run([ffmpeg_path(),'-y','-i',str(video),'-vf',f'select={select}','-vsync','0',str(Path(folder)/'%02d.png')],capture_output=True,check=True,timeout=60)
            for i,n in enumerate((0,8,9,24),1):
                base=crop_photo(p);base.alpha_composite(body_layer(c))
                expected=cover_frame(c,[p]).convert('RGB') if n<9 else render_frame(base,p.labels,[label_tile(label)],(n-9)/30)
                with Image.open(Path(folder)/f'{i:02d}.png') as image:
                    delta=ImageChops.difference(expected.convert('L'),image.convert('L'))
                    self.assertLess(ImageStat.Stat(delta).mean[0],4)
                    if n<9:
                        self.assertLess(max(image.convert('RGB').getpixel((246,400))),10,'封面安全框不輸出')


if __name__=='__main__':unittest.main()
