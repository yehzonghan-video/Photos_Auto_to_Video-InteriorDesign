"""正文標題／透明LOGO、單次批次同步與真正MP4影格驗證。"""
import copy
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from PIL import Image, ImageChops, ImageStat
from studio.cover import new_cover, validate_cover, cover_frame, title_tile
from studio.body import LAYOUT, body_layer, effective_title, title_span, title_visible, upgrade_body
from studio.component import payload
from studio.sync import consume_editor_event
from studio.comparison import new_comparison, comparison_frame, prepare_comparison
from studio.rendering import crop_photo, render_frame, label_tile
from studio.export import export_video, ffmpeg_path
from tests.test_cover import photo


class BodyTests(unittest.TestCase):
    def test_timing_validation_bounds_and_default_size_upgrade(self):
        p=photo();c=new_cover();self.assertEqual(c['body']['font_size'],120)
        b=c['body'];self.assertEqual(title_span(b,.3,2.3),(.3,2.3))
        b.update(auto_timing=False,start=.6,end=1.5,font_size=240)
        c=validate_cover(c,[p]);self.assertEqual(c['body']['font_size'],240)
        self.assertFalse(title_visible(c['body'],.5,.3,2.3));self.assertTrue(title_visible(c['body'],.6,.3,2.3));self.assertFalse(title_visible(c['body'],1.5,.3,2.3))
        self.assertEqual(title_span(c['body'],.3,1),(.6,1))
        for change in ({'auto_timing':'true'},{'start':float('nan')},{'start':'1'},{'start':True},{'end':None},{'start':2,'end':1},{'start':0,'end':.01}):
            with self.subTest(change=change),self.assertRaises(ValueError):validate_cover({**c,'body':{**c['body'],**change}},[p])
        old={'font_size':88};upgrade_body(old);self.assertEqual(old['font_size'],120);old['font_size']=140;upgrade_body(old);self.assertEqual(old['font_size'],140)
        manual={'font_size':180};upgrade_body(manual);self.assertEqual(manual['font_size'],180)

    def test_custom_time_survives_batch_sync_without_changing_photo_duration(self):
        p=photo();state=dict(photos=[p],editor_session='s',revision=1,cover=validate_cover(new_cover(),[p]))
        c=copy.deepcopy(state['cover']);c['body'].update(auto_timing=False,start=.6,end=1.,font_size=180)
        event=dict(nonce='title-time',session='s',base_revision=1,action='apply',photos=[p.metadata()],cover=c)
        consume_editor_event(state,event);self.assertTrue(state['editor_response']['ok'])
        self.assertEqual(state['cover']['body']['start'],.6);self.assertEqual(state['cover']['body']['end'],1.)
        self.assertEqual(p.duration,1);self.assertEqual(payload([p],cover=state['cover'])['cover']['body']['font_size'],180)

    def test_real_timed_title_crosses_photos_and_clips_and_logo_remains(self):
        a,b=photo('before.png','red',(108,192)),photo('after.png','blue',(108,192));a.role='before';b.role='after';photos=[a,b]
        c=validate_cover(new_cover(),photos);c['body'].update(auto_timing=False,start=.6,end=1.5)
        clips=[new_comparison(a,b),new_comparison(a,b)]
        for clip in clips:clip.update(duration=1,before_time=.1,transition_time=.2,labels=[])
        logo=body_layer(c,include_title=False);title=body_layer(c,include_logo=False);box=LAYOUT['title']
        crop=(box['x'],box['y'],box['x']+box['width'],box['y']+box['height'])
        with tempfile.TemporaryDirectory(prefix='timed-title-') as folder:
            for template in ('items','compare'):
                video=Path(folder)/(template+'.mp4');video.write_bytes(export_video(photos,cover=c,template=template,comparisons=clips))
                for n,shown in ((15,False),(18,True),(38,True),(45,False)):
                    target=Path(folder)/f'{template}-{n}.png'
                    subprocess.run([ffmpeg_path(),'-y','-i',str(video),'-vf',f'select=eq(n\\,{n})','-frames:v','1',str(target)],capture_output=True,check=True,timeout=60)
                    local=(n-9)/30;index=0 if local<1 else 1
                    base=comparison_frame(clips[index],prepare_comparison(clips[index],photos),local-index) if template=='compare' else crop_photo(photos[index])
                    base.alpha_composite(logo)
                    if shown:base.alpha_composite(title)
                    with Image.open(target) as actual:
                        expected=base.convert('RGB');delta=ImageChops.difference(expected.convert('L').crop(crop),actual.convert('L').crop(crop))
                        self.assertLess(ImageStat.Stat(delta).mean[0],4)
                        delta=ImageChops.difference(expected.convert('L').crop((700,195,965,390)),actual.convert('L').crop((700,195,965,390)))
                        self.assertLess(ImageStat.Stat(delta).mean[0],4,'LOGO不跟隨文字裁切時間消失')

    def test_follow_colors_independent_title_and_validation(self):
        p=photo();c=new_cover();c.update(title='老屋88萬',highlights=[dict(start=2,end=4,color='#ff0000')])
        c=validate_cover(c,[p]);self.assertEqual(effective_title(c)['highlights'][0]['color'],'#ff0000')
        c['title']='封面再改';self.assertEqual(effective_title(c)['title'],'封面再改')
        c['body'].update(follow_cover=False,title='正文獨立',highlights=[dict(start=0,end=2,color='#ffff00')])
        self.assertEqual(effective_title(c)['title'],'正文獨立')
        for change in ({'logo_enabled':'true'},{'font_size':999},{'title':'','follow_cover':False},
                       {'highlights':[dict(start=0,end=99,color='#ffffff')]}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_cover({**c,'body':{**c['body'],**change}},[p])

    def test_safe_title_transparent_logo_and_cover_unchanged(self):
        p=photo();c=validate_cover(new_cover(),[p]);base=cover_frame(c,[p])
        c['body'].update(follow_cover=False,title='老屋翻新\n最低88萬起',highlights=[dict(start=7,end=9,color='#ff0000')])
        self.assertIsNone(ImageChops.difference(base.convert('RGB'),cover_frame(c,[p]).convert('RGB')).getbbox(),'正文不改变封面')
        tile=title_tile(effective_title(c),LAYOUT['title']);bbox=tile.getbbox()
        self.assertGreater(bbox[0],0);self.assertLess(bbox[2],tile.width);self.assertLess(bbox[3],tile.height)
        self.assertTrue(any(r>200 and g<80 and b<80 and a>0 for r,g,b,a in tile.get_flattened_data()))
        self.assertTrue(any(r==g==b==0 and a>100 for r,g,b,a in tile.get_flattened_data()))
        c['body']['enabled']=False;logo=body_layer(c);box=logo.getbbox()
        self.assertAlmostEqual(box[0]/1080,1963/3000,delta=.002);self.assertAlmostEqual(box[1]/1920,551/5334,delta=.002)
        self.assertEqual(logo.getpixel((540,960))[3],0,'透明LOGO不遮住中間照片')
        c['body']['logo_enabled']=False;self.assertIsNone(body_layer(c).getbbox())
        c['body']['enabled']=True;c['body']['title']='一\n二\n三\n四\n五\n六';c['body']['highlights']=[]
        self.assertIsNotNone(title_tile(effective_title(c),LAYOUT['title']).getbbox(),'多行自動縮字')

    def test_atomic_sync_legacy_events_and_payload_cache(self):
        p=photo();c=validate_cover(new_cover(),[p]);state=dict(photos=[p],editor_session='s',revision=1,cover=c)
        bad=copy.deepcopy(c);bad['body']['follow_cover']=False;bad['body']['title']=''
        row=p.metadata();row['duration']=2
        event=dict(nonce='bad',session='s',base_revision=1,action='apply',photos=[row],cover=bad)
        consume_editor_event(state,event);self.assertFalse(state['editor_response']['ok']);self.assertEqual(p.duration,1)
        c['body'].update(follow_cover=False,title='正文獨立');event.update(nonce='good',cover=c)
        consume_editor_event(state,event);self.assertTrue(state['editor_response']['ok']);self.assertEqual(p.duration,2)
        legacy={k:v for k,v in c.items() if k!='body'}
        event.update(nonce='legacy',base_revision=2,cover=legacy);consume_editor_event(state,event)
        self.assertEqual(state['cover']['body']['title'],'正文獨立')
        cache={};first=payload([p],cache,cover=state['cover']);second=payload([p],cache,cover=state['cover'])
        self.assertEqual(first['body_assets']['title'],second['body_assets']['title'])
        self.assertEqual(first['body_assets']['layout'],LAYOUT)

    def test_real_full_hd_both_templates_header_starts_after_cover(self):
        before=photo('before.png','red',(108,192));before.role='before'
        after=photo('after.png','blue',(108,192));after.role='after';photos=[before,after]
        c=validate_cover(new_cover(),photos);c.update(title='老屋翻新88萬',highlights=[dict(start=4,end=6,color='#ffff00')])
        clip=new_comparison(before,after);clip.update(duration=1,before_time=.2,transition_time=.3)
        clip['labels'][0].update(start=0,end=.2,enter=0,exit=.2)
        clip['labels'][1].update(start=.2,end=1,enter=.2)
        header=body_layer(c)
        with tempfile.TemporaryDirectory(prefix='body-video-') as folder:
            for template in ('items','compare'):
                data=export_video(photos,cover=c,template=template,comparisons=[clip]);video=Path(folder)/(template+'.mp4');video.write_bytes(data)
                for n in (0,9,24):
                    target=Path(folder)/f'{template}-{n}.png'
                    subprocess.run([ffmpeg_path(),'-y','-i',str(video),'-vf',f'select=eq(n\\,{n})','-frames:v','1',str(target)],capture_output=True,check=True,timeout=60)
                    if n==0:expected=cover_frame(c,photos).convert('RGB')
                    else:
                        base=comparison_frame(clip,prepare_comparison(clip,photos),(n-9)/30) if template=='compare' else crop_photo(before)
                        base.alpha_composite(header);labels=clip['labels'] if template=='compare' else before.labels
                        expected=render_frame(base,labels,[label_tile(l) for l in labels],(n-9)/30)
                    with Image.open(target) as actual:
                        delta=ImageChops.difference(expected.convert('L'),actual.convert('L'))
                        self.assertLess(ImageStat.Stat(delta).mean[0],4)
                        if n>=9:
                            # 參考框左上角維持照片顏色；提示白框不得燒入MP4。
                            pixel=actual.convert('RGB').getpixel((142,410));self.assertLess(pixel[1],20)


if __name__=='__main__':unittest.main()
