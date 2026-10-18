"""內容版本、成果保留與工作區保護；Gemini測試另以Mock驗證。"""
import copy
import json
import subprocess
import unittest
from unittest.mock import patch
from contextlib import nullcontext
from io import BytesIO
import zipfile

from studio import versioning as V, protection as P
from studio.sync import consume_editor_event
from studio.project_ui import prepare_download,download_requested,confirm_backup
from studio.project_io import build_archive,load_archive,install_project
from tests.test_project_io import fixture
from tests.app_helpers import authenticated_app


def snapshot(state,nonce='apply',action='apply'):
    return dict(session=state['editor_session'],base_revision=state['revision'],nonce=nonce,action=action,
        photos=copy.deepcopy([p.metadata() for p in state['photos']]),
        **{k:copy.deepcopy(state[k]) for k in ('overlays','comparisons','comparison_overlays','cover','music')},
        template_id=state['template_mode'])


def probe(state,version):
    return dict(action='inspect_guard',nonce='probe-'+state['guard_request']['id'],
                session=state['editor_session'],request=state['guard_request']['id'],
                base_revision=state['revision'],content_version=version,seq=5)


class VersionTests(unittest.TestCase):
    def test_python_javascript_versions_match_with_all_media_and_settings(self):
        state=fixture();ctx=V.context(state);data=snapshot(state);data['photos'][0]['labels'][0]['color']='#AaBBcc'
        script="const V=require('./frontend/content-version.js');const x=JSON.parse(require('fs').readFileSync(0,'utf8'));V.configure(x.context.schema);process.stdout.write(V.digest(V.document(x.data,x.context)));"
        actual=subprocess.run(['node','-e',script],input=json.dumps(dict(data=data,context=ctx),ensure_ascii=False).encode(),capture_output=True,check=True,timeout=30).stdout.decode()
        self.assertEqual(actual,V.digest(V.document(data,ctx)))
        self.assertEqual(V.digest({'x':1,'y':-0.}),V.digest({'y':0,'x':1.0}))
        self.assertEqual(V.digest('😀繁體\n中文'),V.digest(json.loads(json.dumps('😀繁體\n中文'))))

    def test_versions_include_media_content_and_ignore_ui_or_json_format(self):
        state=fixture();initial=V.refresh(state);revision=state['revision']
        state.update(editor_response={'nonce':'different'},ai_calls=19,selected_photo='elsewhere')
        self.assertEqual(V.refresh(state),initial);self.assertEqual(state['revision'],revision)
        state['cover']['font_size']=float(state['cover']['font_size']);self.assertEqual(V.refresh(state),initial)
        state['photos'][0].original+=b'new-content';self.assertNotEqual(V.refresh(state),initial)
        base=V.project_version(state);state['music_asset'].data+=b'changed';self.assertNotEqual(V.project_version(state),base)
        base=V.project_version(state);state['video_width']=720;self.assertNotEqual(V.project_version(state),base)
        base=V.project_version(state);state['overlay_assets'][next(iter(state['overlay_assets']))].original+=b'changed'
        self.assertNotEqual(V.project_version(state),base)

    def test_unchanged_apply_keeps_mp4_zip_and_content_version_then_change_is_stale(self):
        state=fixture();old=V.refresh(state);revision=state['revision']
        V.complete_export(state,b'last-good',1,old)
        state['zip_version']=old;state['project_archive']={'data':b'zip','content_version':old}
        event=snapshot(state);event['content_version']=old
        consume_editor_event(state,event)
        self.assertTrue(state['editor_response']['ok']);self.assertEqual(state['content_version'],old)
        self.assertEqual(state['revision'],revision);self.assertEqual(state['output'],b'last-good')
        self.assertEqual(state['project_archive']['data'],b'zip')
        event=snapshot(state,'new');event['photos'][0]['labels'][0]['text']='新文字'
        consume_editor_event(state,event);self.assertTrue(state['editor_response']['ok'])
        self.assertNotEqual(state['content_version'],old)
        self.assertEqual(state['mp4_version'],old);self.assertEqual(state['output'],b'last-good')
        self.assertEqual(state['zip_version'],old);self.assertEqual(state['project_archive']['data'],b'zip')
        V.complete_export(state,b'new-good',2,state['content_version'])
        self.assertEqual(state['output'],b'new-good');self.assertEqual(state['mp4_version'],state['content_version'])

    def test_incorrect_declared_version_rejects_without_partial_commit(self):
        state=fixture();old=V.refresh(state);event=snapshot(state)
        event['photos'][0]['duration']=3;event['content_version']=old
        consume_editor_event(state,event);self.assertFalse(state['editor_response']['ok'])
        self.assertEqual(state['content_version'],old);self.assertEqual(state['photos'][0].duration,2)

    def test_zip_generation_download_request_and_explicit_confirmation_are_distinct(self):
        state=fixture();state['project_save_job']=True
        with patch('studio.project_ui.st.spinner',return_value=nullcontext()):prepare_download(state)
        version=state['zip_version'];self.assertEqual(version,state['content_version'])
        self.assertIsNone(state.get('backup_confirmed_version'))
        confirm_backup(state,version);self.assertIsNone(state.get('backup_confirmed_version'))
        download_requested(state,version);self.assertIsNone(state.get('backup_confirmed_version'))
        confirm_backup(state,version);self.assertEqual(state['backup_confirmed_version'],version)
        old_zip=state['project_archive'];state['project_save_job']=True
        with patch('studio.project_ui.st.spinner',return_value=nullcontext()),patch('studio.project_ui.build_archive',side_effect=MemoryError):prepare_download(state)
        self.assertIs(state['project_archive'],old_zip);self.assertFalse(state['editor_response']['ok'])

    def test_old_zip_without_version_can_import_and_untrusted_backup_claim_is_ignored(self):
        state=fixture();raw=build_archive(state);out=BytesIO()
        with zipfile.ZipFile(BytesIO(raw)) as src,zipfile.ZipFile(out,'w') as dst:
            for info in src.infolist():
                data=src.read(info.filename)
                if info.filename=='manifest.json':
                    doc=json.loads(data);doc.pop('content_version',None);doc['backup_confirmed_version']='forged'
                    data=json.dumps(doc,ensure_ascii=False).encode()
                dst.writestr(info.filename,data)
        opened=load_archive(out.getvalue());target={};install_project(target,opened)
        self.assertEqual(target['backup_confirmed_version'],V.project_version(target))
        self.assertNotEqual(target['backup_confirmed_version'],'forged')


class ProtectionTests(unittest.TestCase):
    def test_unbacked_frontend_probe_requires_confirmation_and_cancel_preserves_everything(self):
        for action in ('clear','logout','import'):
            with self.subTest(action=action):
                state=fixture();V.refresh(state);V.complete_export(state,b'mp4',1,state['content_version'])
                state['backup_confirmed_version']=state['content_version']
                P.request(state,action);new_version='cv1-'+'a'*64
                consume_editor_event(state,probe(state,new_version))
                self.assertEqual(state['guard_request']['status'],'confirm');self.assertNotIn('guard_approved',state)
                before=copy.deepcopy({k:v for k,v in state.items() if k not in ('guard_request','guard_import_project')})
                P.cancel(state)
                self.assertNotIn('guard_request',state)
                self.assertEqual({k:v for k,v in state.items() if k not in ('guard_request','guard_import_project')},before)

    def test_confirmed_current_backup_needs_no_extra_confirmation_and_stale_probe_is_ignored(self):
        state=fixture();version=V.refresh(state);state['backup_confirmed_version']=version
        P.request(state,'clear');event=probe(state,version)
        consume_editor_event(state,{**event,'request':'old-request'})
        self.assertNotIn('guard_approved',state)
        consume_editor_event(state,{**event,'nonce':'current-probe'})
        self.assertEqual(state['guard_approved'],'clear');self.assertNotIn('guard_request',state)
        empty={'photos':[],'revision':0};P.request(empty,'logout')
        self.assertEqual(empty['guard_approved'],'logout');self.assertNotIn('guard_request',empty)

    def test_generated_or_download_requested_zip_does_not_suppress_warning(self):
        state=fixture();version=V.refresh(state);state.update(zip_version=version,zip_download_requested_version=version)
        P.request(state,'logout');consume_editor_event(state,probe(state,version))
        self.assertEqual(state['guard_request']['status'],'confirm')
        P.approve(state);self.assertEqual(state['guard_approved'],'logout')


    def test_empty_photos_with_custom_title_still_has_unbacked_work(self):
        from studio.cover import new_cover
        state={'photos':[],'cover':new_cover()};self.assertFalse(P.has_project(state))
        state['cover']['title']='尚需保留的標題';P.request(state,'clear')
        self.assertEqual(state['guard_request']['status'],'checking');self.assertNotIn('guard_approved',state)

    def test_old_revision_probe_is_reissued_and_unknown_version_is_conservative(self):
        state=fixture();V.refresh(state);P.request(state,'clear');old=probe(state,state['content_version'])
        state['revision']+=1;consume_editor_event(state,old)
        self.assertNotEqual(state['guard_request']['id'],old['request']);self.assertNotIn('guard_approved',state)
        consume_editor_event(state,probe(state,None));self.assertEqual(state['guard_request']['status'],'confirm')


class AppVersionTests(unittest.TestCase):
    def test_confirmed_backup_clear_has_no_confirmation_and_backup_ack_is_explicit(self):
        app=authenticated_app();next(b for b in app.button if b.label=='載入 5 張測試示意圖').click().run()
        app.session_state['project_save_job']=True;app.run();version=app.session_state.zip_version
        self.assertNotIn('backup_confirmed_version',app.session_state)
        app.session_state['zip_download_requested_version']=version;app.run()
        next(b for b in app.button if b.label=='我已確認此版本ZIP已儲存').click().run()
        self.assertEqual(app.session_state.backup_confirmed_version,version)
        next(b for b in app.button if b.label=='清空目前工作階段').click().run();guard=app.session_state.guard_request
        app.session_state['studio_editor']=dict(action='inspect_guard',nonce=guard['id'],request=guard['id'],
                session=app.session_state.editor_session,base_revision=app.session_state.revision,content_version=version)
        app.run();self.assertFalse(app.exception);self.assertEqual(app.session_state.photos,[])
        self.assertFalse(any(b.label=='仍要清空工作區' for b in app.button))

    def test_failed_export_keeps_previous_success_and_rerun_preserves_versions(self):
        app=authenticated_app();next(b for b in app.button if b.label=='載入 5 張測試示意圖').click().run()
        old=app.session_state.content_version
        app.session_state['output']=b'last-good-mp4';app.session_state['mp4_version']=old;app.session_state['output_seconds']=1
        rows=copy.deepcopy([p.metadata() for p in app.session_state.photos]);rows[0]['labels'][0]['text']='更新標籤'
        app.session_state['studio_editor']=dict(session=app.session_state.editor_session,base_revision=app.session_state.revision,
            nonce='new-text',action='apply',photos=rows)
        app.run();self.assertFalse(app.exception);new=app.session_state.content_version
        self.assertNotEqual(new,old);self.assertEqual(app.session_state.output,b'last-good-mp4')
        self.assertTrue(any('較舊' in w.value for w in app.warning))
        app.session_state['render_job']={'width':360,'content_version':new};app.session_state['editor_busy']=True
        with patch('studio.export.export_video',autospec=True,side_effect=RuntimeError('模擬編碼失敗')):app.run()
        self.assertFalse(app.exception);self.assertEqual(app.session_state.output,b'last-good-mp4')
        self.assertEqual(app.session_state.mp4_version,old);self.assertEqual(app.session_state.content_version,new)
        app.run();self.assertEqual(app.session_state.content_version,new)

    def test_clear_cancel_then_confirm_and_logout_cancel(self):
        app=authenticated_app();next(b for b in app.button if b.label=='載入 5 張測試示意圖').click().run()
        ids=[p.id for p in app.session_state.photos];version=app.session_state.content_version
        for label in ('清空目前工作階段','登出'):
            next(b for b in app.button if b.label==label).click().run()
            self.assertEqual([p.id for p in app.session_state.photos],ids)
            guard=app.session_state.guard_request
            app.session_state['studio_editor']=dict(action='inspect_guard',nonce=guard['id'],request=guard['id'],
                session=app.session_state.editor_session,base_revision=app.session_state.revision,content_version=version)
            app.run();self.assertFalse(app.exception)
            self.assertTrue(any('尚無已確認' in w.value for w in app.warning))
            next(b for b in app.button if b.label=='取消操作').click().run()
            self.assertEqual([p.id for p in app.session_state.photos],ids);self.assertEqual(app.session_state.content_version,version)
        next(b for b in app.button if b.label=='清空目前工作階段').click().run()
        guard=app.session_state.guard_request
        app.session_state['studio_editor']=dict(action='inspect_guard',nonce=guard['id'],request=guard['id'],
                session=app.session_state.editor_session,base_revision=app.session_state.revision,content_version=version)
        app.run();next(b for b in app.button if b.label=='仍要清空工作區').click().run()
        self.assertFalse(app.exception);self.assertEqual(app.session_state.photos,[])
