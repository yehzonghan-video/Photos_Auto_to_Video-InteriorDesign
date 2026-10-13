"""PNG Alpha、全片時間、圖層順序與真實 MP4；沒有真實 AI 呼叫。"""
import copy
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
import unittest

from PIL import Image, ImageDraw, ImageChops, ImageStat
from studio.overlays import load_asset, discover_assets, validate_overlays, geometry, prepare_overlays
from studio.animation import overlay_pose
from studio.models import load_photo, new_label
from studio.rendering import render_frame, label_tile, crop_photo
from studio.export import export_video, ffmpeg_path
from studio.sync import consume_editor_event


def asset(color='red',transparent=False):
    image=Image.new('RGBA',(100,60),color)
    if transparent:
        draw=ImageDraw.Draw(image);draw.rectangle((35,20,65,40),fill=(0,0,0,0))
    buffer=BytesIO();image.save(buffer,'PNG')
    return load_asset('透明素材.png',buffer.getvalue())


def overlay(source,**changes):
    return dict(id='png',type='png',source=source,start=.5,duration=1,layer=20,x=.5,y=.5,width=.3,
        scale=1,rotation=0,opacity=1,animation='none',exit_animation='none',enter=0,exit=0,**changes)


class OverlayTests(unittest.TestCase):
    def test_alpha_and_strict_png_limits(self):
        a=asset(transparent=True)
        with Image.open(BytesIO(a.original)) as img:self.assertEqual(img.getpixel((50,30))[3],0)
        out=BytesIO();Image.new('RGB',(10,10)).save(out,'JPEG')
        with self.assertRaises(ValueError):load_asset('fake.png',out.getvalue())
        with self.assertRaises(ValueError):load_asset('empty.png',b'')
        out=BytesIO();Image.new('RGBA',(10,10),'red').save(out,'PNG',save_all=True,append_images=[Image.new('RGBA',(10,10),'blue')])
        with self.assertRaises(ValueError):load_asset('animation.png',out.getvalue())
        bank,warnings=discover_assets();self.assertGreaterEqual(len(bank),2);self.assertFalse(warnings)

    def test_invalid_overlay_atomic_sync(self):
        a=asset();out=BytesIO();Image.new('RGB',(100,100)).save(out,'PNG');photo=load_photo('p.png',out.getvalue())
        state=dict(photos=[photo],revision=1,editor_session='s',overlay_assets={a.id:a},overlays=[])
        row=photo.metadata();row['duration']=3
        raw=overlay(a.id);raw['source']='unknown'
        consume_editor_event(state,dict(nonce='bad',session='s',base_revision=1,action='apply',photos=[row],overlays=[raw]))
        self.assertFalse(state['editor_response']['ok']);self.assertEqual(photo.duration,4)
        for update in ({'opacity':2},{'rotation':float('nan')},{'duration':5},{'layer':1.5}):
            with self.assertRaises(ValueError):validate_overlays([{**overlay(a.id),**update}],{a.id:a},2)
        with self.assertRaises(ValueError):validate_overlays([None],{a.id:a},2)
        with self.assertRaises(ValueError):validate_overlays([overlay(a.id)]*2,{a.id:a},2)

    def test_geometry_rotation_scale_stays_in_frame_and_animation(self):
        a=asset();o=overlay(a.id);o.update(scale=5,x=0,y=1,rotation=43)
        g=geometry(o,a)
        self.assertGreaterEqual(g['x']-g['box_width']/2,0)
        self.assertLessEqual(g['y']+g['box_height']/2,1920)
        o.update(animation='left',exit_animation='fade',enter=.25,exit=.25)
        self.assertIsNone(overlay_pose(o,.4));self.assertEqual(overlay_pose(o,.5)['alpha'],0)
        self.assertAlmostEqual(overlay_pose(o,1)['alpha'],1)
        self.assertLess(overlay_pose(o,1.49)['alpha'],.15)
        self.assertIsNone(overlay_pose(o,1.5))

    def test_transparency_and_png_text_layer_order(self):
        a=asset();o=overlay(a.id);base=Image.new('RGBA',(1080,1920),'#666666')
        label=new_label();label.update(text='層',x=.45,y=.49,background='#0000ff',opacity=1,font_size=24,line=False,animation='none',layer=10)
        tile=label_tile(label);pos=(round(label['x']*1080)+tile.width//2,round(label['y']*1920)+5)
        top=render_frame(base,[label],[tile],1,prepare_overlays([o],{a.id:a}),1)
        self.assertEqual(top.getpixel(pos),(255,0,0))
        o['layer']=5
        back=render_frame(base,[label],[tile],1,prepare_overlays([o],{a.id:a}),1)
        self.assertEqual(back.getpixel(pos),(0,0,255))
        transparent=asset(transparent=True);o=overlay(transparent.id)
        image=render_frame(base,[],[],1,prepare_overlays([o],{transparent.id:transparent}),1)
        self.assertEqual(image.getpixel((540,960)),(102,102,102))

    def test_real_full_hd_png_crosses_photo_boundary_and_disappears(self):
        photos=[]
        for color in ('#668866','#667799'):
            out=BytesIO();Image.new('RGB',(540,960),color).save(out,'PNG')
            p=load_photo('scene.png',out.getvalue());p.duration=1;photos.append(p)
        a=asset(transparent=True);b=asset('green');bank={a.id:a,b.id:b}
        one=overlay(a.id);one.update(rotation=25,scale=.9,opacity=.8,animation='left',enter=.15,exit_animation='fade',exit=.15)
        two=overlay(b.id);two.update(id='second',start=.9,duration=.3,x=.6,y=.6,layer=30,width=.15)
        overlays=validate_overlays([one,two],bank,2);prepared=prepare_overlays(overlays,bank)
        state=dict(photos=photos,overlays=[],overlay_assets=bank,editor_session='s',revision=1,pending_export={'id':'request','width':1080})
        consume_editor_event(state,dict(nonce='export',session='s',base_revision=1,action='export',request='request',
            photos=[p.metadata() for p in photos],overlays=overlays))
        self.assertTrue(state['editor_response']['ok']);self.assertEqual(len(state['overlays']),2)
        data=export_video(state['photos'],overlays=state['overlays'],assets=bank)
        with tempfile.TemporaryDirectory(prefix='png-verify-') as folder:
            path=Path(folder)/'png.mp4';path.write_bytes(data)
            result=subprocess.run([ffmpeg_path(),'-hide_banner','-i',str(path),'-f','null','-'],capture_output=True,timeout=60)
            log=result.stderr.decode('utf8',errors='replace');self.assertEqual(result.returncode,0)
            self.assertIn('1080x1920',log);self.assertIn('h264',log);self.assertIn('00:00:02.00',log)
            for index,t in enumerate((.2,.8,1.1,1.7)):
                frame=Path(folder)/f'{index}.png'
                subprocess.run([ffmpeg_path(),'-y','-ss',str(t),'-i',str(path),'-frames:v','1',str(frame)],capture_output=True,check=True)
                expected=render_frame(crop_photo(photos[0 if t<1 else 1]),[],[],t%1,prepared,t)
                decoded=Image.open(frame).convert('RGB')
                diff=ImageStat.Stat(ImageChops.difference(expected,decoded))
                self.assertLess(max(diff.mean),5)
                region=(350,780,750,1240)
                roi=ImageStat.Stat(ImageChops.difference(expected.crop(region),decoded.crop(region)))
                self.assertLess(max(roi.mean),8,'PNG圖層區域必須與預期一致')
                if t==.8:self.assertGreater(decoded.getpixel((474,929))[0],180,'跨照片前確實有紅色PNG')
                if t==1.1:self.assertLess(decoded.getpixel((648,1152))[2],40,'跨照片後確實有上層綠色PNG')


if __name__=='__main__':unittest.main()
