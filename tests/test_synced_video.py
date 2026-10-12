"""真實 Full HD 輸出：校準 PNG 與解碼影格均反映最新批次草稿。"""
import base64
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from PIL import Image, ImageChops, ImageStat
from studio.component import payload
from studio.export import export_video, ffmpeg_path
from studio.models import load_photo, new_label
from studio.rendering import crop_photo, label_tile, render_frame
from studio.sync import consume_editor_event


class SyncedVideoTests(unittest.TestCase):
    def test_latest_ten_label_snapshot_matches_canonical_assets_and_mp4(self):
        buffer=BytesIO();Image.new("RGB", (1200,675), "#526254").save(buffer,"PNG")
        photo=load_photo("verification.png",buffer.getvalue());photo.duration=1
        state=dict(photos=[photo],editor_session="session",revision=1,pending_export={"id":"request","width":1080})
        row=photo.metadata().copy()
        row["labels"]=[]
        for index in range(10):
            label=new_label(1)
            label.update(text=f"裝修 {index+1}",x=.05+(index%3)*.3,y=.12+(index//3)*.18,
                         line=False,start=0,enter=.2,color="#ffeecc",background="#502b19")
            row["labels"].append(label)
        row["labels"][0].update(text="最新標籤",font_size=60,color="#ffffff",background="#994422")
        consume_editor_event(state,dict(session="session",base_revision=1,nonce="export",seq=30,
                                       action="export",request="request",photos=[row]))
        self.assertTrue(state["editor_response"]["ok"])
        canonical=payload(state["photos"])["photos"][0]
        tiles=[]
        for label in photo.labels:
            encoded=canonical["tiles"][label["id"]]["src"].split(",",1)[1]
            tile=Image.open(BytesIO(base64.b64decode(encoded))).convert("RGBA")
            self.assertEqual(tile.tobytes(),label_tile(label).tobytes())
            tiles.append(tile)
        expected=render_frame(crop_photo(photo),photo.labels,tiles,.8)
        video=export_video(state["photos"])
        with tempfile.TemporaryDirectory(prefix="sync-verification-") as folder:
            target=Path(folder)/"video.mp4";frame=Path(folder)/"frame.png";target.write_bytes(video)
            result=subprocess.run([ffmpeg_path(),"-hide_banner","-i",str(target),"-f","null","-"],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0)
            log=result.stderr.decode("utf8",errors="replace")
            self.assertIn("1080x1920",log);self.assertIn("h264",log);self.assertIn("00:00:01.00",log)
            subprocess.run([ffmpeg_path(),"-y","-ss","0.8","-i",str(target),"-frames:v","1",str(frame)],capture_output=True,check=True)
            decoded=Image.open(frame).convert("RGB")
            for label,tile in zip(photo.labels,tiles):
                x,y=round(label["x"]*1080),round(label["y"]*1920)
                region=(x,y,x+tile.width,y+tile.height)
                difference=ImageStat.Stat(ImageChops.difference(decoded.crop(region),expected.crop(region)))
                self.assertLess(max(difference.mean),8.,label["text"])


if __name__ == "__main__":
    unittest.main()
