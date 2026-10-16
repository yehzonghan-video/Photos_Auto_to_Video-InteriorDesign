"""正文LOGO獨立時間、舊專案相容與真實Full HD輸出。"""
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from PIL import Image, ImageChops, ImageStat
from studio.body import logo_span, logo_visible, title_visible, body_layer
from studio.cover import new_cover, validate_cover, cover_frame
from studio.sync import consume_editor_event
from studio.project_io import build_archive, load_archive
from studio.comparison import new_comparison, comparison_frame, prepare_comparison
from studio.rendering import crop_photo
from studio.export import export_video, ffmpeg_path
from tests.test_cover import photo
from tests.test_project_io import fixture


class LogoTimelineTests(unittest.TestCase):
    def test_defaults_validation_boundaries_and_legacy_upgrade(self):
        p=photo();c=validate_cover(new_cover(),[p]);b=c['body']
        self.assertEqual(logo_span(b,.3,2.3),(.3,2.3))
        b.update(logo_auto_timing=False,logo_start=.6,logo_end=1.6)
        self.assertFalse(logo_visible(b,.59,.3,2.3));self.assertTrue(logo_visible(b,.6,.3,2.3))
        self.assertFalse(logo_visible(b,1.6,.3,2.3));self.assertEqual(logo_span(b,.3,1),(.6,1))
        for change in ({'logo_auto_timing':'true'},{'logo_start':True},{'logo_start':float('nan')},
                       {'logo_end':None},{'logo_end':.6},{'logo_end':121}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_cover({**c,'body':{**b,**change}},[p])
        old=copy.deepcopy(c);old['body']['version']=4;old['body']['font_size']=120
        for key in ('logo_auto_timing','logo_start','logo_end'):old['body'].pop(key)
        upgraded=validate_cover(old,[p])['body'];self.assertEqual(upgraded['font_size'],120)
        self.assertTrue(upgraded['logo_auto_timing']);self.assertEqual(logo_span(upgraded,.3,2.3),(.3,2.3))

    def test_sync_zip_roundtrip_and_old_page_does_not_erase_logo_times(self):
        state=fixture();c=copy.deepcopy(state['cover']);c['body'].update(logo_auto_timing=False,logo_start=.6,logo_end=1.6)
        def event(nonce,cover):return dict(session=state['editor_session'],base_revision=state['revision'],nonce=nonce,
            action='apply',photos=[p.metadata() for p in state['photos']],cover=cover)
        consume_editor_event(state,event('logo',c));self.assertTrue(state['editor_response']['ok'])
        legacy=copy.deepcopy(c)
        for key in ('logo_auto_timing','logo_start','logo_end'):legacy['body'].pop(key)
        consume_editor_event(state,event('old-page',legacy));self.assertTrue(state['editor_response']['ok'])
        self.assertEqual(state['cover']['body']['logo_end'],1.6)
        restored=load_archive(build_archive(state));self.assertEqual(restored['cover']['body'],state['cover']['body'])
        old_project=copy.deepcopy(state);old_project['cover']['body']=legacy['body'];old_project['cover']['body']['version']=4
        restored=load_archive(build_archive(old_project));self.assertTrue(restored['cover']['body']['logo_auto_timing'])

    def test_real_full_hd_logo_time_is_independent_on_both_templates(self):
        photos=[photo('before.png','red',(108,192)),photo('after.png','blue',(108,192))]
        photos[0].role='before';photos[1].role='after'
        c=validate_cover(new_cover(),photos);c['body'].update(logo_auto_timing=False,logo_start=.6,logo_end=1.6,
                                                           auto_timing=False,start=1.1,end=2)
        clip=new_comparison(*photos);clip.update(duration=2,before_time=.6,transition_time=.4,labels=[])
        logo=body_layer(c,include_title=False);title=body_layer(c,include_logo=False)
        with tempfile.TemporaryDirectory(prefix='timed-logo-') as folder:
            for template in ('items','compare'):
                video=Path(folder)/(template+'.mp4');video.write_bytes(export_video(photos,cover=c,template=template,comparisons=[clip]))
                for n,shown in ((0,False),(12,False),(18,True),(38,True),(40,True),(48,False),(54,False)):
                    output=Path(folder)/f'{template}-{n}.png'
                    subprocess.run([ffmpeg_path(),'-y','-i',str(video),'-vf',f'select=eq(n\\,{n})','-frames:v','1',str(output)],capture_output=True,check=True,timeout=60)
                    t=n/30;local=t-.3
                    if n==0:expected=cover_frame(c,photos)
                    else:
                        expected=comparison_frame(clip,prepare_comparison(clip,photos),local) if template=='compare' else crop_photo(photos[0 if local<1 else 1])
                        self.assertEqual(logo_visible(c['body'],t,.3,2.3),shown)
                        if shown:expected.alpha_composite(logo)
                        if title_visible(c['body'],t,.3,2.3):expected.alpha_composite(title)
                    with Image.open(output) as actual:
                        self.assertEqual(actual.size,(1080,1920))
                        delta=ImageChops.difference(expected.convert('L'),actual.convert('L'))
                        self.assertLess(ImageStat.Stat(delta).mean[0],4)
                        self.assertLess(ImageStat.Stat(delta.crop((700,195,965,390))).mean[0],4,'LOGO結束後不得殘留在照片底圖')
