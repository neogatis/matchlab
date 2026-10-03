import io
import unittest

from PIL import Image

from app.photos.storage import InvalidImageObject, sanitize_image_bytes


class PhotoSanitizerTests(unittest.TestCase):
    def _jpeg(self, *, size=(800, 600), exif=True):
        image = Image.new("RGB", size, (120, 80, 40))
        output = io.BytesIO()
        kwargs = {}
        if exif:
            metadata = Image.Exif()
            metadata[271] = "camera-maker"
            metadata[272] = "camera-model"
            metadata[274] = 6
            kwargs["exif"] = metadata
        image.save(output, format="JPEG", quality=90, **kwargs)
        return output.getvalue()

    def test_jpeg_is_reencoded_without_exif(self):
        raw = self._jpeg(exif=True)
        cleaned = sanitize_image_bytes(raw, "image/jpeg")
        self.assertGreater(len(cleaned), 0)
        with Image.open(io.BytesIO(cleaned)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(len(image.getexif()), 0)
            self.assertEqual(image.size, (600, 800))

    def test_content_type_mismatch_is_rejected(self):
        raw = self._jpeg(exif=False)
        with self.assertRaises(InvalidImageObject):
            sanitize_image_bytes(raw, "image/png")

    def test_non_image_is_rejected(self):
        with self.assertRaises(InvalidImageObject):
            sanitize_image_bytes(b"not-an-image", "image/jpeg")

    def test_tiny_image_is_rejected(self):
        raw = self._jpeg(size=(100, 100), exif=False)
        with self.assertRaises(InvalidImageObject):
            sanitize_image_bytes(raw, "image/jpeg")


if __name__ == "__main__":
    unittest.main()
