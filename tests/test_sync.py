import copy
from io import BytesIO
import unittest
from unittest.mock import patch
from PIL import Image
from studio.component import payload
from studio.models import load_photo, new_label
from studio.sync import consume_editor_event


def project():
    buffer=BytesIO();Image.new("RGB", (100, 100), "#555555").save(buffer, "PNG")
    photos=[load_photo("first.png",buffer.getvalue()),load_photo("second.png",buffer.getvalue())]
    return dict(photos=photos, editor_session="session", revision=1, pending_export=None,
                output=b"old video", output_seconds=1, project_payload=None, editor_assets={})


def event(state, nonce="batch", action="apply"):
    return dict(session="session", base_revision=state["revision"], nonce=nonce, action=action,
                seq=10, photos=copy.deepcopy([p.metadata() for p in state["photos"]]))


class SyncTests(unittest.TestCase):
    def test_ten_labels_replace_once_and_survive_repeat_event(self):
        state=project();batch=event(state)
        batch["photos"][0]["labels"]=[new_label() for _ in range(10)]
        batch["photos"][0]["labels"][3].update(text="修改文字",x=.7,color="#00ff00",animation="scale")
        consume_editor_event(state,batch);consume_editor_event(state,batch)
        self.assertEqual(state["revision"],2)
        self.assertEqual(len(state["photos"][0].labels),10)
        self.assertEqual(state["photos"][0].labels[3]["text"],"修改文字")
        self.assertIsNone(state["output"])
        stale=event(state,"old");stale["base_revision"]=1;stale["photos"][0]["labels"]=[]
        consume_editor_event(state,stale)
        self.assertFalse(state["editor_response"]["ok"])
        self.assertEqual(len(state["photos"][0].labels),10)

    def test_export_only_after_latest_snapshot_and_matching_request(self):
        state=project();state["pending_export"]={"id":"request", "width":1080}
        batch=event(state,action="export");batch["request"]="request"
        label=new_label();label.update(text="輸出最新文字",x=.6,font_size=72,background="#990000")
        batch["photos"][0]["labels"]=[label]
        consume_editor_event(state,batch)
        self.assertEqual(state["render_job"]["width"],1080)
        self.assertEqual(state["photos"][0].labels[0]["text"],"輸出最新文字")
        self.assertTrue(state["editor_busy"])
        self.assertIsNone(state["pending_export"])
        state.pop("render_job");consume_editor_event(state,batch)
        self.assertNotIn("render_job",state)
        state["pending_export"]={"id":"retry", "width":720}
        consume_editor_event(state,dict(nonce="cancel",session="session",action="cancel_export",request="retry"))
        self.assertIsNone(state["pending_export"])
        self.assertNotIn("render_job",state)

    def test_invalid_transaction_does_not_partially_change_project(self):
        state=project();batch=event(state)
        batch["photos"][0]["duration"]=5
        batch["photos"][1]["labels"]=[new_label()];batch["photos"][1]["labels"][0]["end"]=0
        consume_editor_event(state,batch)
        self.assertFalse(state["editor_response"]["ok"])
        self.assertEqual(state["photos"][0].duration,4)
        self.assertEqual(state["revision"],1)

    def test_delete_reorder_and_clear_do_not_restore_deleted_labels(self):
        state=project();batch=event(state)
        batch["photos"]=[batch["photos"][1]]
        consume_editor_event(state,batch)
        self.assertEqual(len(state["photos"]),1)
        batch=event(state,"clear");batch["photos"]=[];consume_editor_event(state,batch)
        self.assertEqual(state["photos"],[])

    def test_raster_cache_reuses_assets_when_only_positions_change(self):
        state=project();state["photos"][0].labels=[new_label()]
        with patch("studio.component.label_tile",wraps=__import__("studio.rendering",fromlist=["label_tile"]).label_tile) as render:
            first=payload(state["photos"],state["editor_assets"])
            state["photos"][0].labels[0]["x"] = .8
            second=payload(state["photos"],state["editor_assets"])
            self.assertEqual(render.call_count,1)
            self.assertEqual(first["photos"][0]["tiles"],second["photos"][0]["tiles"])
            state["photos"][0].labels[0]["text"]="需要重畫"
            payload(state["photos"],state["editor_assets"])
            self.assertEqual(render.call_count,2)


if __name__ == "__main__":
    unittest.main()
