import unittest
from modules.utils import Utils

class TestUtils(unittest.TestCase):
    def setUp(self):
        self.utils = Utils()

    def test_is_image_request(self):
        self.assertTrue(self.utils.is_image_request("Fotoğraf gönder"))
        self.assertFalse(self.utils.is_image_request("Merhaba"))

    def test_extract_image_keyword(self):
        # assistant: "Kamiq"
        result = self.utils.extract_image_keyword("Kamiq resim paylaşır mısın?", "Kamiq")
        self.assertEqual(result, "paylaşır mısın")

    def test_parse_color_names(self):
        text = "Aracın ay beyazı ve kadife kırmızısı renkleri var."
        found_colors = self.utils.parse_color_names(text)
        self.assertIn("ay beyazı", found_colors)
        self.assertIn("kadife kırmızısı", found_colors)
