"""實際大照片與縮圖處理；小容量／記憶體錯誤分支使用 Mock 門檻。"""
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops, ImageStat
from studio.component import payload
from studio.export import export_video, ffmpeg_path
from studio.models import load_photo, new_label
from studio.photo_processing import fit_session, preview_data, read_upload
from studio.rendering import crop_photo
import base64


def picture(size=(6000,4000)):
    out=BytesIO()
    with Image.new('RGB',size,'#ff0000') as image:
        image.paste('#0000ff',(size[0]//2,0,size[0],size[1]))
        image.save(out,'JPEG',quality=95)
    return out.getvalue()


class PhotoProcessingTests(unittest.TestCase):
    def test_normal_keeps_original_preview_is_smaller_and_cached(self):
        data=picture();photo=load_photo('原圖.jpg',data)
        self.assertIs(photo.original,data)
        self.assertFalse(photo.optimization_note)
        cache={};row=payload([photo],cache)['photos'][0]
        preview=base64.b64decode(row['image'].split(',')[1])
        with Image.open(BytesIO(preview)) as image:
            self.assertLessEqual(image.width*image.height,4_000_000)
            self.assertLessEqual(max(image.size),2560)
            self.assertAlmostEqual(image.width/image.height,1.5,places=3)
        self.assertEqual(photo.original,data)
        with patch('studio.component.preview_data',side_effect=AssertionError('不應重建未改變照片的預覽')):
            self.assertEqual(payload([photo],cache)['photos'][0]['image'],row['image'])

    def test_real_48_megapixel_jpeg_auto_resizes_instead_of_rejecting(self):
        data=picture((8000,6000));photo=load_photo('4800萬.jpg',data)
        self.assertLessEqual(photo.width*photo.height,32_000_000)
        self.assertAlmostEqual(photo.width/photo.height,4/3,places=3)
        self.assertTrue(photo.optimization_note)
        self.assertNotEqual(photo.original,data)
        with Image.open(BytesIO(photo.original)) as image:
            self.assertGreater(image.getpixel((0,image.height//2))[0],240)
            self.assertGreater(image.getpixel((image.width-1,image.height//2))[2],240)

    def test_real_72_megapixel_batch_fits_and_keeps_ids_edits_and_input(self):
        data=picture();photos=[load_photo(f'{i}.jpg',data) for i in range(3)]
        photos[0].labels=[new_label()];photos[0].zoom=2;photos[0].fit='cover'
        rows=fit_session(photos)
        self.assertLessEqual(sum(p.width*p.height for p in rows),60_000_000)
        self.assertEqual([p.id for p in rows],[p.id for p in photos])
        self.assertEqual(rows[0].metadata(),photos[0].metadata())
        self.assertTrue(all(p.optimization_note for p in rows))
        self.assertTrue(all(p.original==data for p in photos),'不修改尚未成功提交的舊資料')
        self.assertEqual(sum(p.width*p.height for p in photos),72_000_000)

    def test_file_over_old_15_mb_limit_is_reencoded_not_rejected(self):
        data=picture((400,300))+b'\0'*(16*1024*1024)
        photo=load_photo('大檔.jpg',data)
        self.assertLess(len(photo.original),15*1024*1024)
        self.assertEqual((photo.width,photo.height),(400,300))
        self.assertTrue(photo.optimization_note)

    def test_mock_byte_budget_and_memory_retry(self):
        out=BytesIO();Image.effect_noise((500,400),90).convert('RGB').save(out,'PNG')
        photos=[load_photo('noise.png',out.getvalue()) for _ in range(3)]
        with patch('studio.photo_processing.SESSION_BYTES',100_000):
            rows=fit_session(photos)
            self.assertLessEqual(sum(len(p.original) for p in rows),100_000)
        fallback=Image.new('RGB',(400,300),'red')
        with patch('studio.photo_processing._decode',side_effect=[MemoryError(),(fallback,(8000,6000))]) as decoder:
            working,w,h,note=read_upload(b'valid-image-placeholder')
            self.assertEqual((w,h),(400,300));self.assertIn('記憶體不足',note)
            self.assertEqual(decoder.call_count,2);self.assertGreater(len(working),1000)

    def test_preview_alpha_and_exif_orientation(self):
        out=BytesIO();Image.new('RGBA',(100,200),(255,0,0,0)).save(out,'PNG')
        photo=load_photo('透明.png',out.getvalue())
        with Image.open(BytesIO(preview_data(photo))) as image:
            self.assertEqual(image.getpixel((50,100)),(0,0,0))
        exif=Image.Exif();exif[274]=6
        out=BytesIO();Image.new('RGB',(400,200),'red').save(out,'JPEG',exif=exif)
        photo=load_photo('旋轉.jpg',out.getvalue())
        self.assertEqual((photo.width,photo.height),(200,400))
        self.assertEqual(photo.original,out.getvalue())
        with Image.open(BytesIO(preview_data(photo))) as image:self.assertEqual(image.size,(200,400))

    def test_real_full_hd_export_uses_original_after_preview_generation(self):
        photo=load_photo('高解析.jpg',picture());photo.duration=1
        payload([photo])
        data=export_video([photo])
        with tempfile.TemporaryDirectory(prefix='photo-preview-') as folder:
            video=Path(folder)/'case.mp4';video.write_bytes(data)
            frame=Path(folder)/'frame.png'
            result=subprocess.run([ffmpeg_path(),'-hide_banner','-i',str(video),'-f','null','-'],capture_output=True,timeout=60)
            self.assertEqual(result.returncode,0)
            self.assertIn('1080x1920',result.stderr.decode('utf8',errors='replace'))
            subprocess.run([ffmpeg_path(),'-y','-ss','0.5','-i',str(video),'-frames:v','1',str(frame)],capture_output=True,check=True)
            with Image.open(frame) as actual:
                diff=ImageStat.Stat(ImageChops.difference(crop_photo(photo).convert('RGB'),actual.convert('RGB')))
                self.assertLess(max(diff.mean),5)


if __name__=='__main__':unittest.main()
