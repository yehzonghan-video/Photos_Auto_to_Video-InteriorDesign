"""延後一次、短照片邊界及真實MP4；不需要Gemini API。"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from PIL import Image, ImageChops, ImageStat
from studio.models import new_label, delay_label, validate_label
from studio.animation import pose
from studio.rendering import crop_photo, label_tile, render_frame
from studio.export import export_video, ffmpeg_path
from tests.test_core import photo
from tests.app_helpers import authenticated_app


class LabelTimingTests(unittest.TestCase):
    def test_new_and_legacy_labels_delay_once_and_keep_manual_edits(self):
        label=new_label(4)
        self.assertEqual((label['start'],label['end']),(1,4))
        self.assertIsNone(pose(label,.9))
        del label['label_timing_version'];label['start']=.3
        self.assertTrue(delay_label(label,4));self.assertEqual(label['start'],1.3)
        label=validate_label(label,4);label['start']=.5
        self.assertFalse(delay_label(label,4));self.assertEqual(label['start'],.5)
        title=dict(start=0,end=2,enter=.3,comparison_side='before')
        self.assertFalse(delay_label(title,5));self.assertEqual(title['start'],0)

    def test_short_labels_are_valid_and_visible_in_last_frame(self):
        for duration,start,end in ((1,0,1),(4,3.8,4),(4,0,.01)):
            with self.subTest(duration=duration,start=start,end=end):
                label=new_label(duration);label.pop('label_timing_version');label.update(start=start,end=end)
                delay_label(label,duration);validate_label(label,duration)
                self.assertLess(label['start'],label['end']);self.assertLessEqual(label['end'],duration)
                self.assertEqual(label['enter'],0);self.assertEqual(pose(label,label['start'])['alpha'],1)

    def test_streamlit_legacy_migration_is_idempotent_and_preserves_content(self):
        app=authenticated_app()
        next(b for b in app.button if b.label=='載入 5 張測試示意圖').click().run()
        label=app.session_state.photos[0].labels[0]
        label.pop('label_timing_version',None);label.update(start=.3,text='保留人工內容')
        app.session_state.cover['body'].update(font_size=120,x=.5,y=530/1920,version=3)
        app.session_state.body_title_version=3
        app.run();self.assertFalse(app.exception)
        self.assertEqual(label['start'],1.3);self.assertEqual(label['text'],'保留人工內容')
        body=app.session_state.project_payload['cover']['body']
        self.assertEqual((body['font_size'],body['x'],body['y']),(100,.5,.245))
        revision=app.session_state.revision;app.run();self.assertFalse(app.exception)
        self.assertEqual(label['start'],1.3);self.assertEqual(app.session_state.revision,revision)

    def test_real_full_hd_mp4_delays_each_photo_label(self):
        photos=[photo(),photo()]
        for p in photos:
            p.duration=2;label=new_label(2);label.update(text='延後標籤',x=.2,y=.15,line=False)
            p.labels=[label]
        data=export_video(photos)
        with tempfile.TemporaryDirectory(prefix='label-delay-') as folder:
            video=Path(folder)/'test.mp4';video.write_bytes(data)
            for n in (15,45,75,105):
                p=photos[n//60];t=(n%60)/30;frame=Path(folder)/f'{n}.png'
                subprocess.run([ffmpeg_path(),'-y','-i',str(video),'-vf',f'select=eq(n\\,{n})','-frames:v','1',str(frame)],capture_output=True,check=True,timeout=60)
                base=crop_photo(p);tile=label_tile(p.labels[0]);expected=render_frame(base,p.labels,[tile],t)
                region=(160,250,700,500)
                self.assertEqual(pose(p.labels[0],t) is not None,t>=1)
                with Image.open(frame) as actual:
                    self.assertEqual(actual.size,(1080,1920))
                    error=ImageStat.Stat(ImageChops.difference(actual.convert('RGB').crop(region),expected.crop(region)))
                    self.assertLess(max(error.mean),5)
                if t>=1:self.assertIsNotNone(ImageChops.difference(expected,base.convert('RGB')).getbbox())
