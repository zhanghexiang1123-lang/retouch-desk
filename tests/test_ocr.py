"""Real CPU-model integration tests on selected glyphs, never mocked OCR output."""
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from backend.ocr import recognize


class OcrTests(unittest.TestCase):
    def image(self, text, dark=False):
        image = Image.new('RGB', (500, 100), (25, 35, 55) if dark else (245, 243, 235))
        ImageDraw.Draw(image).text((20, 12), text, font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 32),
                                  fill=(238,239,242) if dark else (30,35,40))
        return image

    def test_chinese_and_digits_on_both_backgrounds(self):
        selection = {'x':10,'y':10,'w':360,'h':65,'mode':'rectangle'}
        for text in ['张祥 2026', '20261113', '001023.50']:
            for dark in [False, True]:
                with self.subTest(text=text, dark=dark):
                    result = recognize(self.image(text, dark), selection)
                    self.assertTrue(result['available'], result)
                    self.assertEqual(result['text'], text, result)
                    self.assertEqual(result['polarity'], 'light' if dark else 'dark')

    def test_freehand_excludes_other_text_inside_bounding_rectangle(self):
        image = self.image('2025')
        ImageDraw.Draw(image).text((150,15), '999', font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 30), fill=(30,35,40))
        selection = {'x':10,'y':5,'w':260,'h':75,'mode':'freehand', 'points':[
            {'x':10,'y':5}, {'x':120,'y':5}, {'x':120,'y':65}, {'x':270,'y':78}, {'x':10,'y':78}]}
        result = recognize(image, selection)
        self.assertEqual(result['text'], '2025', result)

    def test_blank_has_no_fabricated_text(self):
        result = recognize(Image.new('RGB',(120,50),'white'), {'x':0,'y':0,'w':120,'h':50})
        self.assertEqual(result['text'], '')
        self.assertEqual(result['confidence'], 0)

    def test_missing_runtime_keeps_manual_path_available(self):
        with patch('backend.ocr.available', return_value=False):
            result = recognize(self.image('2025'), {'x':0,'y':0,'w':120,'h':70})
        self.assertFalse(result['available'])
        self.assertEqual(result['text'], '')


if __name__ == '__main__':
    unittest.main()
