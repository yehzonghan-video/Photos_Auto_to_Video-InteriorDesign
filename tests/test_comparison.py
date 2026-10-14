"""實際對比合成／MP4；AI 沿用既有 Mock 回歸。"""
import base64
import copy
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import subprocess
import tempfile
import unittest
from PIL import Image, ImageChops, ImageStat
from streamlit.testing.v1 import AppTest
from studio.models import load_photo
from studio.animation import pose
from studio.comparison import (new_comparison,auto_pair,validate_comparisons,prepare_comparison,
                               comparison_frame,comparison_pose)
from studio.export import export_video,ffmpeg_path
from studio.overlays import load_asset,prepare_overlays
from studio.rendering import label_tile,render_frame
from studio.sync import consume_editor_event
from studio.component import payload
from studio.safe_area import SAFE_AREA
from tests.app_helpers import authenticated_app


def source(name,role,color,size=(108,192)):
    out=BytesIO();Image.new('RGB',size,color).save(out,'PNG')
    p=load_photo(name,out.getvalue());p.role=role;return p


class ComparisonTests(unittest.TestCase):
    def test_safe_area_default_titles_fit_and_manual_positions_are_unrestricted(self):
        photos=[source('b','before','black'),source('a','after','black')];c=new_comparison(*photos)
        box=SAFE_AREA['inner']
        for label in c['labels']:
            tile=label_tile(label);x=label['x']*1080;y=label['y']*1920
            self.assertGreaterEqual(x,box['left']);self.assertGreaterEqual(y,box['top'])
            self.assertLessEqual(x+tile.width,box['right']);self.assertLessEqual(y+tile.height,box['bottom'])
            label.update(x=0,y=0)
        result=validate_comparisons([c],photos)[0]
        self.assertTrue(all(l['x']==l['y']==0 and l['safe_area_version']==1 for l in result['labels']))
        self.assertEqual(payload(photos,comparisons=[c],template='compare')['safe_area'],SAFE_AREA)

    def test_plain_titles_same_position_and_exact_change_boundary(self):
        photos=[source('b','before','red'),source('a','after','blue')]
        c=new_comparison(*photos);before,after=c['labels']
        self.assertEqual((before['x'],before['y']),(after['x'],after['y']))
        self.assertEqual(before['end'],after['start'])
        for label in c['labels']:
            self.assertEqual((label['opacity'],label['radius'],label['line']),(0,0,False))
            tile=label_tile(label);self.assertEqual(tile.getpixel((0,0))[3],0)
            self.assertEqual(tile.getchannel('A').getextrema(),(0,255),'只有文字具有Alpha，背景透明')
        for frame in range(150):
            labels=[l for l in c['labels'] if pose(l,frame/30) is not None]
            self.assertEqual(len(labels),1)
            self.assertEqual(labels[0]['comparison_side'],'before' if frame/30<2 else 'after')
        result=validate_comparisons([c],photos)[0]
        self.assertTrue(all(l['comparison_title_version']==2 for l in result['labels']))
        self.assertTrue(all(l['font_size']==72 for l in result['labels']))
        self.assertGreater(pose(before,1.7)['alpha'],pose(before,1.9)['alpha'])
        self.assertGreater(pose(after,2.3)['alpha'],pose(after,2.1)['alpha'])
        c['before_time']=0;before.update(start=0,end=0,enter=0,exit=0);after.update(start=0)
        self.assertEqual(validate_comparisons([c],photos)[0]['labels'][0]['end'],0)
        self.assertIsNone(pose(before,0));self.assertIsNotNone(pose(after,0))

    def test_auto_pair_partial_reuse_and_validation(self):
        photos=[source('b1','before','red'),source('b2','before','red'),source('a','after','blue')]
        rows,left=auto_pair(photos);self.assertEqual((len(rows),left),(1,1));self.assertEqual(len(photos),3)
        rows.append(new_comparison(photos[1],photos[2]));rows.append(new_comparison(photos[0],photos[2]))
        self.assertEqual(len(validate_comparisons(rows,photos)),3)
        again,_=auto_pair(photos,rows);self.assertEqual(len(again),3)
        for values in ({'split':2},{'mode':'unknown'},{'transition_time':20},{'duration':float('nan')},{'before_id':'missing'},{'before_id':{}}):
            with self.assertRaises(ValueError):validate_comparisons([{**rows[0],**values}],photos)

    def test_real_mp4_large_titles_fade_out_then_in(self):
        photos=[source('b','before','black'),source('a','after','black')]
        c=new_comparison(*photos);c.update(duration=3,before_time=1,transition_time=.5)
        c['labels'][0]['end']=1;c['labels'][1].update(start=1,end=3)
        data=export_video(photos,template='compare',comparisons=[c])
        indices=(20,25,29,30,31,35,41)
        with tempfile.TemporaryDirectory(prefix='title-fade-') as folder:
            video=Path(folder)/'case.mp4';video.write_bytes(data)
            select='+'.join(f'eq(n\\,{index})' for index in indices)
            subprocess.run([ffmpeg_path(),'-y','-i',str(video),'-vf',f'select={select}',
                            '-vsync','0',str(Path(folder)/'%02d.png')],capture_output=True,check=True,timeout=60)
            brightness=[]
            for i,index in enumerate(indices,1):
                with Image.open(Path(folder)/f'{i:02d}.png') as image:
                    self.assertEqual(image.size,(1080,1920))
                    for xy in ((111,400),(48,400),(500,190),(500,1716)):
                        self.assertLess(max(image.convert('RGB').getpixel(xy)),5,'安全區提示不能出現在實際MP4')
                    brightness.append(ImageStat.Stat(image.convert('L').crop((60,145,350,300))).mean[0])
                    base=comparison_frame(c,prepare_comparison(c,photos),index/30)
                    expected=render_frame(base,c['labels'],[label_tile(l) for l in c['labels']],index/30)
                    delta=ImageChops.difference(expected.convert('L'),image.convert('L'))
                    self.assertLess(ImageStat.Stat(delta.crop((60,145,350,300))).mean[0],3)
            self.assertGreater(brightness[0],brightness[1]);self.assertGreater(brightness[1],brightness[2])
            self.assertLess(brightness[3],.5,'換字邊界施工前已消失、施工後正準備漸顯')
            self.assertLess(brightness[4],brightness[5]);self.assertLess(brightness[5],brightness[6])

    def test_mask_is_real_reveal_split_slide_and_cut_pixels(self):
        photos=[source('b','before','red'),source('a','after','blue')];c=new_comparison(*photos);c['show_line']=False
        for mode in ('switch','split','reveal'):
            c['mode']=mode;frames=prepare_comparison(c,photos)
            if mode=='split':
                frame=comparison_frame(c,frames,0);self.assertEqual(frame.getpixel((100,960))[:3],(255,0,0));self.assertEqual(frame.getpixel((900,960))[:3],(0,0,255))
            elif mode=='reveal':
                for direction in ('ltr','rtl'):
                    c['direction']=direction;frame=comparison_frame(c,frames,2.5)
                    self.assertEqual(frame.getpixel((100,960))[:3],(0,0,255) if direction=='ltr' else (255,0,0))
                    self.assertEqual(frame.getpixel((900,960))[:3],(255,0,0) if direction=='ltr' else (0,0,255))
            else:
                c['transition']='cut';c['transition_time']=0
                self.assertEqual(comparison_frame(c,frames,1.9).getpixel((540,960))[:3],(255,0,0))
                self.assertEqual(comparison_frame(c,frames,2).getpixel((540,960))[:3],(0,0,255))
                c['transition_time']=1;c['transition']='fade';frame=comparison_frame(c,frames,2.5)
                self.assertEqual(frame.getpixel((540,960))[:3],(127,0,127))
                c['transition']='slide'
                for d in ('ltr','rtl'):
                    c['direction']=d
                    self.assertEqual(comparison_frame(c,frames,0).getpixel((540,960))[:3],(255,0,0))
                    self.assertEqual(comparison_frame(c,frames,4).getpixel((540,960))[:3],(0,0,255))

    def test_contain_and_independent_cover_crop(self):
        photos=[source('b','before','red',(300,100)),source('a','after','blue',(50,200))]
        c=new_comparison(*photos);c['mode']='split';c['show_line']=False
        frame=comparison_frame(c,prepare_comparison(c,photos),0)
        self.assertEqual(frame.getpixel((100,0))[:3],(0,0,0));self.assertEqual(frame.getpixel((100,960))[:3],(255,0,0))
        c['before_crop'].update(fit='cover',zoom=2,crop_x=0);c['after_crop'].update(fit='cover',zoom=3,crop_y=1)
        frames=prepare_comparison(c,photos)
        self.assertEqual(frames[0].getpixel((0,0))[:3],(255,0,0));self.assertEqual(frames[1].getpixel((0,0))[:3],(0,0,255))
        self.assertEqual(photos[0].fit,'contain')
        buffer=BytesIO();image=Image.new('RGB',(300,100),'red');image.paste('green',(200,0,300,100));image.save(buffer,'PNG')
        photos[0].original=buffer.getvalue()
        c['before_crop']['crop_x']=0
        self.assertEqual(prepare_comparison(c,photos)[0].getpixel((270,960))[:3],(255,0,0))
        c['before_crop']['crop_x']=1
        self.assertEqual(prepare_comparison(c,photos)[0].getpixel((270,960))[:3],(0,128,0))

    def test_atomic_sync_slots_repeat_nonce_and_stale_template(self):
        photos=[source('b','before','red'),source('a','after','blue')];c=new_comparison(*photos)
        state=dict(photos=photos,comparisons=[],comparison_overlays=[],overlays=[],overlay_assets={},editor_session='s',revision=1,template_mode='compare')
        rows=[p.metadata() for p in photos];rows[0]['duration']=3
        event=dict(nonce='bad',session='s',base_revision=1,action='apply',template_id='compare',photos=rows,comparisons=[{**c,'after_id':'missing'}])
        consume_editor_event(state,event);self.assertFalse(state['editor_response']['ok']);self.assertEqual(photos[0].duration,4)
        event.update(nonce='good',comparisons=[c]);consume_editor_event(state,event)
        self.assertTrue(state['editor_response']['ok']);self.assertEqual(len(state['comparisons']),1)
        consume_editor_event(state,event);self.assertEqual(state['revision'],2)
        event.update(nonce='stale',base_revision=2,template_id='items');consume_editor_event(state,event)
        self.assertFalse(state['editor_response']['ok']);self.assertEqual(len(state['comparisons']),1)
        rendered=payload(photos,comparisons=state['comparisons'],template='compare')
        self.assertEqual(rendered['template_id'],'compare');self.assertEqual(len(rendered['comparisons'][0]['tiles']),2)

    def test_real_all_modes_full_hd_png_text_and_frame_validation(self):
        photos=[source('b','before','#d74433'),source('a','after','#3355cc')];clips=[]
        for mode,transition in (('switch','cut'),('switch','fade'),('switch','slide'),('split','fade'),('reveal','fade')):
            c=new_comparison(*photos);c.update(mode=mode,transition=transition,duration=2,before_time=.5,transition_time=0 if transition=='cut' else .8,show_line=True)
            for l in c['labels']:
                l.update(start=0 if mode=='split' or l['comparison_side']=='before' else .5,
                         end=2 if mode=='split' or l['comparison_side']=='after' else .5,enter=0)
            if mode=='split':c['labels'][1]['x']=.57
            c['labels'][1].update(text='施工後新文字',color='#ffff00',font_size=60)
            clips.append(c)
        out=BytesIO();image=Image.new('RGBA',(160,100),'#00ff00');image.paste((0,0,0,0),(50,20,110,80));image.save(out,'PNG')
        asset=load_asset('透明.png',out.getvalue());bank={asset.id:asset}
        o=dict(id='overlay',type='png',source=asset.id,start=1.5,duration=3,x=.5,y=.7,width=.2,scale=1,rotation=20,opacity=.8,
               layer=20,animation='fade',exit_animation='fade',enter=.2,exit=.2)
        state=dict(photos=photos,comparisons=[],comparison_overlays=[],overlays=[],overlay_assets=bank,editor_session='s',revision=1,template_mode='compare',pending_export={'id':'e','width':1080})
        consume_editor_event(state,dict(nonce='export',session='s',base_revision=1,action='export',request='e',template_id='compare',
            photos=[p.metadata() for p in photos],comparisons=clips,comparison_overlays=[o]))
        self.assertTrue(state['editor_response']['ok']);prepared=prepare_overlays(state['comparison_overlays'],bank)
        data=export_video(photos,template='compare',comparisons=state['comparisons'],overlays=state['comparison_overlays'],assets=bank)
        with tempfile.TemporaryDirectory(prefix='compare-verify-') as folder:
            video=Path(folder)/'case.mp4';video.write_bytes(data)
            decode=subprocess.run([ffmpeg_path(),'-hide_banner','-i',str(video),'-f','null','-'],capture_output=True,timeout=60)
            self.assertEqual(decode.returncode,0);log=decode.stderr.decode('utf8',errors='replace')
            for value in ('h264','1080x1920','00:00:10.00'):self.assertIn(value,log)
            self.assertIn('30 fps',log);self.assertRegex(log,r'frame=\s*300')
            for index,t in enumerate((.2,.9,1.8,2.9,4.8,5.2,6.9,8.8,9.2)):
                target=Path(folder)/f'{index}.png';subprocess.run([ffmpeg_path(),'-y','-ss',str(t),'-i',str(video),'-frames:v','1',str(target)],capture_output=True,check=True)
                c=state['comparisons'][min(4,int(t//2))];local=t%2
                base=comparison_frame(c,prepare_comparison(c,photos),local)
                expected=render_frame(base,c['labels'],[label_tile(l) for l in c['labels']],local,prepared,t)
                with Image.open(target) as image:
                    delta=ImageChops.difference(expected,image.convert('RGB'))
                    self.assertLess(max(ImageStat.Stat(delta).mean),5)
                    self.assertLess(max(ImageStat.Stat(delta.crop((380,1150,700,1550))).mean),8)
                    # 黃字配藍底經 yuv420p 會有色度抽樣誤差；以亮度比較字形／殘影。
                    text_delta=ImageChops.difference(expected.convert('L'),image.convert('L'))
                    ink=ImageChops.difference(expected,base.convert('RGB')).convert('L').point(lambda value:255 if value>30 else 0)
                    region=(60,145,650,310)
                    self.assertLess(ImageStat.Stat(text_delta.crop(region),ink.crop(region)).mean[0],15,
                                    f'輸出文字字形需與目前階段一致：{index=} {t=}')
                    self.assertLess(max(abs(x-y) for x,y in zip(image.convert('RGB').getpixel((70,160)),expected.getpixel((70,160)))),8,
                                    '文字左上內距應保留底圖，不能有背景框')

    def test_streamlit_template_upload_regions_session_and_real_export(self):
        app=authenticated_app()
        next(s for s in app.selectbox if s.label=='影片模板').select('compare').run()
        labels=[u.proto.label for u in app.get('file_uploader')]
        self.assertIn('施工前照片（可一次多張）',labels);self.assertIn('施工後照片（可一次多張）',labels)
        next(b for b in app.button if b.label=='載入前後對比測試圖').click().run()
        self.assertFalse(app.exception);photos=app.session_state.photos
        self.assertEqual([p.role for p in photos],['before','before','after','after'])
        clips,_=auto_pair(photos);clips=clips[:1];clips[0].update(duration=1,before_time=.2,transition_time=.3)
        for l in clips[0]['labels']:l.update(start=0,end=1,enter=.1)
        next(s for s in app.selectbox if s.label=='影片解析度').select(360).run()
        next(b for b in app.button if b.label=='輸出 H.264 MP4').click().run();request=app.session_state.pending_export
        app.session_state['studio_editor']=dict(nonce='test',session=app.session_state.editor_session,base_revision=app.session_state.revision,
             action='export',request=request['id'],template_id='compare',photos=[p.metadata() for p in photos],comparisons=clips)
        app.run();self.assertFalse(app.exception);self.assertGreater(len(app.session_state.output),1000)
        app.run();self.assertEqual(len(app.session_state.comparisons),1)
        next(s for s in app.selectbox if s.label=='影片模板').select('items').run()
        self.assertEqual(len(app.session_state.comparisons),1);self.assertEqual(len(app.session_state.photos),4)

    def test_mock_upload_widgets_use_real_photo_bytes_and_before_after_batches(self):
        import streamlit as st
        app=authenticated_app()
        next(s for s in app.selectbox if s.label=='影片模板').select('compare').run()
        original=st.file_uploader
        data=source('sample','general','red').original
        def picker(label,*args,**kwargs):
            value=original(label,*args,**kwargs)
            if label.startswith('施工前照片'):return [SimpleNamespace(name=f'b{i}.png',getvalue=lambda:data) for i in range(2)]
            if label.startswith('施工後照片'):return [SimpleNamespace(name='a.png',getvalue=lambda:data)]
            return value
        with patch('streamlit.file_uploader',side_effect=picker):
            app.run();next(b for b in app.button if b.label=='加入施工前照片').click().run()
            self.assertEqual(app.session_state.photo_upload_epochs['before'],1)
            self.assertEqual(app.session_state.photo_upload_epochs['after'],0,'加入前照片不得清掉後照片的上傳控制')
            next(b for b in app.button if b.label=='加入施工後照片').click().run()
        self.assertFalse(app.exception);photos=app.session_state.photos
        self.assertEqual([p.role for p in photos],['before','before','after'])
        clips,left=auto_pair(photos);self.assertEqual((len(clips),left),(1,1))


if __name__=='__main__':unittest.main()
