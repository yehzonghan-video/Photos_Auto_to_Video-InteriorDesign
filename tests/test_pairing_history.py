"""第四階段來源引用／刪除復原／版本與實際輸出；不呼叫Gemini。"""
from copy import deepcopy
from io import BytesIO
import unittest
from PIL import Image
from studio import versioning as V
from studio.sync import consume_editor_event
from studio.comparison import validate_comparisons, new_comparison
from studio.project_io import build_archive,load_archive
from studio.photo_history import sources,preview
from studio.cover import new_cover
from tests.test_project_io import fixture
from tests.test_versions import snapshot


def clean_fixture(template='compare'):
    s=fixture(template);s.update(overlays=[],comparison_overlays=[],cover=new_cover())
    s['cover']['enabled']=False
    return s


def send(s,nonce,rows=None,clips=None,restore=None,deleted=None):
    event=snapshot(s,nonce)
    if rows is not None:event['photos']=rows
    if clips is not None:event['comparisons']=clips
    if restore:event['restore_photo']=restore
    if deleted:event['deleted_photo']=deleted
    # 本測試專注實際資料驗證；其他測試核對前後端SHA一致性。
    event.pop('content_version',None)
    if rows is not None and s['cover']['photo_id'] not in {r['id'] for r in rows}:
        event['cover']['photo_id']=rows[0]['id'] if rows else ''
    consume_editor_event(s,event)
    return event


class PairingHistoryTests(unittest.TestCase):
    def test_swap_and_reclassify_keep_clip_id_animation_labels_crop_and_zip(self):
        s=fixture('compare');V.refresh(s);c=s['comparisons'][0];before=deepcopy(c);old=s['content_version'];s.update(output=b'old',mp4_version=old)
        c['before_id'],c['after_id']=c['after_id'],c['before_id'];c['before_crop'],c['after_crop']=c['after_crop'],c['before_crop']
        s['photos'][0].role='general'
        s['comparisons']=validate_comparisons(s['comparisons'],s['photos']);V.refresh(s)
        self.assertEqual(c['id'],before['id']);self.assertEqual(c['labels'],before['labels']);self.assertEqual(c['duration'],before['duration'])
        self.assertEqual(s['output'],b'old');self.assertNotEqual(s['content_version'],s['mp4_version'])
        loaded=load_archive(build_archive(s));self.assertEqual(loaded['comparisons'][0]['before_id'],c['before_id'])
        self.assertEqual(loaded['photos'][0].role,'general')

    def test_delete_sync_undo_restore_preserves_settings_and_versions(self):
        s=clean_fixture('compare');V.refresh(s);original=deepcopy(s['comparisons']);rows=[deepcopy(p.metadata()) for p in s['photos']];old=s['content_version'];p=s['photos'][0]
        event=send(s,'delete',rows[1:],[],deleted=p.id)
        self.assertTrue(s['editor_response']['ok']);self.assertEqual(s['photo_undo'].original,p.original)
        self.assertEqual(len(s['photos']),1);self.assertNotEqual(old,s['content_version']);self.assertEqual(preview(s)['id'],p.id)
        first=preview(s);self.assertIs(preview(s),first)
        restored=send(s,'undo',rows,original,restore=p.id)
        self.assertTrue(s['editor_response']['ok']);self.assertEqual([r.id for r in s['photos']],[r['id'] for r in rows])
        self.assertEqual(s['comparisons'],original);self.assertIsNone(s.get('photo_undo'))
        rev=s['revision'];consume_editor_event(s,restored);self.assertEqual(s['revision'],rev)
        self.assertEqual(load_archive(build_archive(s))['comparisons'],original)

    def test_deleted_photo_not_exported_and_history_single_slot(self):
        s=clean_fixture('items');V.refresh(s);rows=[p.metadata() for p in s['photos']];first=s['photos'][0]
        send(s,'delete',rows[1:],[],deleted=first.id);self.assertTrue(s['editor_response']['ok'])
        loaded=load_archive(build_archive(s));self.assertEqual(len(loaded['photos']),1);self.assertNotIn('photo_undo',loaded)
        self.assertEqual(len(s['photos'])+int(s.get('photo_undo') is not None),2)
        send(s,'delete2',[],[],deleted=s['photos'][0].id);self.assertTrue(s['editor_response']['ok'])
        self.assertNotEqual(s['photo_undo'].id,first.id)

    def test_invalid_restore_failed_transaction_preserves_original(self):
        s=fixture('items');V.refresh(s);before=s['content_version'];ids=[p.id for p in s['photos']]
        send(s,'unknown',restore='unknown');self.assertFalse(s['editor_response']['ok']);self.assertEqual(s['content_version'],before)
        self.assertEqual([p.id for p in s['photos']],ids)
        event=snapshot(s,'over-limit');event['photos']*=7
        with self.assertRaises(ValueError):sources(s,event)

    def test_same_photo_and_missing_reference_rejected_not_role(self):
        s=fixture('compare');c=deepcopy(s['comparisons'][0]);c['before_id']=c['after_id']
        with self.assertRaises(ValueError):validate_comparisons([c],s['photos'])
        c['before_id']='missing'
        with self.assertRaises(ValueError):validate_comparisons([c],s['photos'])

    def test_reset_drops_trash_not_archive_schema(self):
        s=fixture();s['photo_undo']=s['photos'][0];s['photo_undo_preview']={'id':'test'};V.refresh(s)
        with_history=s['content_version'];s.pop('photo_undo');self.assertEqual(V.project_version(s),with_history)
        s['photo_undo']=s['photos'][0];V.reset_versions(s);self.assertNotIn('photo_undo',s);self.assertNotIn('photo_undo_preview',s)

    def test_actual_full_hd_swapped_comparison_export_and_zip_roundtrip(self):
        from studio.export import export_video,ffmpeg_path
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import subprocess
        s=clean_fixture('compare');s['cover']['body']['enabled']=False;s['cover']['body']['logo_enabled']=False
        for p,color in zip(s['photos'],['red','blue']):
            out=BytesIO();Image.new('RGB',(108,192),color).save(out,'PNG');p.original=out.getvalue()
        c=new_comparison(*s['photos']);c.update(duration=1,before_time=.5,transition_time=0,transition='cut',labels=[])
        c['before_id'],c['after_id']=c['after_id'],c['before_id'];s['comparisons']=[c]
        loaded=load_archive(build_archive(s));data=export_video(loaded['photos'],1080,1920,template='compare',comparisons=loaded['comparisons'],cover=loaded['cover'])
        with TemporaryDirectory() as folder:
            path=Path(folder)/'comparison.mp4';path.write_bytes(data)
            raw=subprocess.run([ffmpeg_path(),'-v','error','-i',str(path),'-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True,timeout=60).stdout
            frame_size=1080*1920*3;self.assertEqual(len(raw),frame_size*30)
            offset=(960*1080+540)*3
            self.assertGreater(raw[offset+2],200);self.assertLess(raw[offset],20)
            self.assertGreater(raw[20*frame_size+offset],200);self.assertLess(raw[20*frame_size+offset+2],20)


if __name__=='__main__':unittest.main()
