import copy
from io import BytesIO
import unittest

from PIL import Image
from studio.animation import pose
from studio.models import load_photo, new_label, update_project
from studio.rendering import crop_photo, label_tile, render_frame


def photo():
    data = BytesIO()
    image = Image.new("RGB", (300, 100), "red")
    image.paste(Image.new("RGB", (100, 100), "blue"), (200, 0))
    image.save(data, "PNG")
    return load_photo("test.png", data.getvalue())


class CoreTests(unittest.TestCase):
    def test_timeline_boundaries_and_easing(self):
        label = new_label(4)
        self.assertIsNone(pose(label, -.1))
        self.assertIsNone(pose(label, 4))
        self.assertEqual(pose(label, 0)["alpha"], 0)
        self.assertEqual(pose(label, 1)["x"], 0)
        self.assertAlmostEqual(pose(label, .3)["x"], -.0275)
        label["animation"] = "none"
        self.assertEqual(pose(label, 0)["alpha"], 1)

    def test_crop_selects_correct_original_region(self):
        item = photo()
        item.crop_x = 0
        self.assertEqual(crop_photo(item, 90, 160).getpixel((45, 80))[:3], (255, 0, 0))
        item.crop_x = 1
        self.assertEqual(crop_photo(item, 90, 160).getpixel((45, 80))[:3], (0, 0, 255))
        self.assertEqual(item.original, photo().original)

    def test_invalid_change_is_atomic(self):
        item = photo()
        rows = [copy.deepcopy(item.metadata())]
        rows[0]["duration"] = 0
        with self.assertRaises(ValueError): update_project([item], rows)
        self.assertEqual(item.duration, 4)
        rows[0]["duration"] = 4
        label = new_label(4); label["x"] = float("nan")
        rows[0]["labels"] = [label]
        with self.assertRaises(ValueError): update_project([item], rows)
        self.assertEqual(item.labels, [])

    def test_reorder_keeps_labels_attached(self):
        first, second = photo(), photo()
        first.labels = [new_label()]
        result = update_project([first, second], [second.metadata(), first.metadata()])
        self.assertIs(result[1], first)
        self.assertEqual(len(result[1].labels), 1)

    def test_label_disappears_and_cjk_raster_exists(self):
        item = photo(); label = new_label(); label["text"] = "木紋地板"
        base = crop_photo(item)
        tile = label_tile(label)
        self.assertGreater(tile.width, 100)
        self.assertEqual(render_frame(base, [label], [tile], 4).tobytes(), base.convert("RGB").tobytes())
        self.assertNotEqual(render_frame(base, [label], [tile], 1).tobytes(), base.convert("RGB").tobytes())

    def test_corrupt_upload(self):
        with self.assertRaises(ValueError): load_photo("fake.png", b"bad data")


if __name__ == "__main__":
    unittest.main()
