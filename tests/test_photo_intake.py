"""選檔事件與媒體替換交易；不呼叫 Gemini、不碰使用者照片。"""
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from PIL import Image

from studio.photo_intake import append_photos, replace_photo, batch_id
from studio.models import load_photo, new_label
from studio.comparison import new_comparison
from studio.versioning import refresh


def upload(name='room.png', color='red', ident='file-1', data=None):
    if data is None:
        out=BytesIO();Image.new('RGB',(120,80),color).save(out,'PNG');data=out.getvalue()
    return SimpleNamespace(name=name, file_id=ident, getvalue=lambda:data)


def state():
    return dict(photos=[],revision=0,editor_session='test',comparisons=[],template_mode='items')


class PhotoIntakeTests(unittest.TestCase):
    def test_append_replay_intentional_repeat_and_noop_versions(self):
        s=state();refresh(s);file=upload()
        key=batch_id('test','general',0,[file]);result=append_photos(s,[file],'general',key)
        self.assertEqual(len(result['added']),1);rev=s['revision'];v=s['content_version']
        self.assertTrue(append_photos(s,[file],'general',key)['replayed'])
        self.assertEqual((s['revision'],s['content_version']),(rev,v))
        next_key=batch_id('test','general',1,[file]);self.assertNotEqual(key,next_key)
        append_photos(s,[file],'general',next_key)
        self.assertEqual(len(s['photos']),2);self.assertNotEqual(s['photos'][0].id,s['photos'][1].id)
        self.assertEqual(s['revision'],rev+1)

    def test_partial_errors_capacity_and_roles(self):
        s=state();files=[upload(ident=str(i)) for i in range(11)]
        append_photos(s,files,'before','first');existing=s['photos'][0];existing.labels=[new_label()]
        result=append_photos(s,[upload(data=b'broken'),upload(ident='good'),upload(ident='overflow')],'after','mixed')
        self.assertEqual(len(result['added']),1);self.assertEqual(len(result['errors']),2)
        self.assertIn('12',result['errors'][1]);self.assertEqual(len(s['photos']),12)
        self.assertEqual(s['photos'][-1].role,'after');self.assertEqual(s['photos'][0].labels,existing.labels)

    def test_all_failed_or_empty_does_not_change_version_or_existing_output(self):
        s=state();refresh(s);version=s['content_version'];s['output']=b'previous-mp4'
        for key,files in [('empty',[]),('bad',[upload(data=b'broken')])]:
            append_photos(s,files,'general',key)
            self.assertEqual(s['content_version'],version);self.assertEqual(s['revision'],0)
        self.assertEqual(s['output'],b'previous-mp4')

    def test_replace_preserves_identity_settings_references_and_flags_ai_only(self):
        s=state();append_photos(s,[upload(),upload(color='blue',ident='b')],'general','batch')
        before,after=s['photos'];before.role='before';after.role='after'
        before.duration=5;before.zoom=1.7;before.crop_x=.7;before.fit='cover'
        manual=new_label(5);manual.update(point_x=.13,point_y=.83)
        ai={**new_label(5),'source':'gemini','needs_review':False}
        before.labels=[manual,ai];s['comparisons']=[new_comparison(before,after)]
        s['output']=b'old'
        refresh(s);original=deepcopy(before.metadata());clip=deepcopy(s['comparisons'])
        result=replace_photo(s,before.id,upload(color='green'),'replace')
        changed=s['photos'][0];self.assertEqual(changed.id,before.id)
        for key in ('duration','zoom','crop_x','crop_y','fit','role'):
            self.assertEqual(changed.metadata()[key],original[key])
        self.assertEqual(changed.labels[0],manual);self.assertTrue(changed.labels[1]['needs_review'])
        self.assertEqual(s['comparisons'],clip);self.assertEqual(s['output'],b'old')
        rev=s['revision'];replace_photo(s,before.id,upload(color='yellow'),'replace')
        self.assertEqual(s['revision'],rev);self.assertTrue(result is not None)

    def test_invalid_replace_and_capacity_failure_are_atomic(self):
        s=state();append_photos(s,[upload()],'general','batch');old=s['photos'][0];rev=s['revision']
        with self.assertRaises(ValueError):replace_photo(s,old.id,upload(data=b'bad'),'bad')
        with patch('studio.photo_intake.fit_session',side_effect=MemoryError()):
            with self.assertRaises(MemoryError):replace_photo(s,old.id,upload(color='blue'),'memory')
        self.assertIs(s['photos'][0],old);self.assertEqual(s['revision'],rev)
        self.assertNotIn('memory',s.get('photo_receipts',{}))

    def test_streamlit_automatically_imports_once_and_allows_same_file_again(self):
        from tests.app_helpers import authenticated_app
        app=authenticated_app();file=upload()
        def selected(label,**kwargs):
            if kwargs.get('key')=='uploads_general_0':return [file,upload(data=b'bad',ident='broken')]
            return [] if kwargs.get('accept_multiple_files') else None
        with patch('streamlit.file_uploader',side_effect=selected):app.run()
        self.assertFalse(app.exception);self.assertEqual(len(app.session_state.photos),1)
        revision=app.session_state.revision;app.run()
        self.assertEqual(app.session_state.revision,revision)
        def selected_again(label,**kwargs):
            if kwargs.get('key')=='uploads_general_1':return [file]
            return [] if kwargs.get('accept_multiple_files') else None
        with patch('streamlit.file_uploader',side_effect=selected_again):app.run()
        self.assertFalse(app.exception);self.assertEqual(len(app.session_state.photos),2)
        self.assertEqual(app.session_state.revision,revision+1)
        self.assertFalse(any(b.label=='加入已選照片' for b in app.button))

    def test_replacement_request_is_non_content_and_dialog_select_applies(self):
        from tests.app_helpers import authenticated_app
        app=authenticated_app()
        next(b for b in app.button if b.label=='載入 5 張測試示意圖').click().run()
        photo=app.session_state.photos[0];ident=photo.id;labels=deepcopy(photo.labels);revision=app.session_state.revision
        app.session_state['studio_editor']=dict(action='replace_photo',nonce='replace-dialog',
            session=app.session_state.editor_session,base_revision=revision,photo_id=ident)
        app.run();self.assertFalse(app.exception);self.assertEqual(app.session_state.revision,revision)
        next(b for b in app.button if b.label=='取消替換').click().run()
        self.assertFalse(app.exception);self.assertEqual(app.session_state.revision,revision)
        self.assertEqual(app.session_state.photos[0].original,photo.original)
        app.session_state['studio_editor']=dict(action='replace_photo',nonce='replace-dialog-2',
            session=app.session_state.editor_session,base_revision=revision,photo_id=ident)
        def selected(label,**kwargs):
            if label=='選擇替換照片':return upload(color='blue')
            return [] if kwargs.get('accept_multiple_files') else None
        with patch('streamlit.file_uploader',side_effect=selected):app.run()
        self.assertFalse(app.exception);self.assertEqual(app.session_state.photos[0].id,ident)
        self.assertEqual(app.session_state.photos[0].labels,labels)
        self.assertNotEqual(app.session_state.photos[0].original,photo.original)
        app.run();self.assertEqual(app.session_state.revision,revision+1)


if __name__=='__main__':unittest.main()
