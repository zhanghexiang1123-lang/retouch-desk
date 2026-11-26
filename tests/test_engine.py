import json
import threading
import time
import unittest
import urllib.request
import urllib.error
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from backend.engine import EditError, decode_image, edit_image, image_url, font_catalog
from backend import server


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = next(f for f in font_catalog() if f.key == 'simsun')
        yy, xx = np.mgrid[:60,:180]
        bg = np.stack([220+xx*.015+yy*.02,216+xx*.015+yy*.02,210+xx*.015+yy*.02],axis=-1)
        cls.image=Image.fromarray(np.round(bg).astype(np.uint8))
        draw=ImageDraw.Draw(cls.image)
        draw.text((25,12),'2025',font=ImageFont.truetype(cls.font.path,24),fill=(55,54,50))
        cls.selection={'x':20,'y':9,'w':65,'h':38,'mode':'rectangle'}

    def test_reconstruction_and_minimal_change(self):
        result=edit_image(self.image,self.selection,'2025','2026',preferred_font='simsun')
        source=np.array(self.image.convert('RGBA')); output=result['image']
        changed=np.any(source!=output,axis=2)
        self.assertEqual(result['report']['outsideChangedPixels'],0)
        self.assertTrue(changed.any())
        self.assertFalse(changed[:,:60].any(),'The first three glyphs must retain their source pixels')
        self.assertLess(result['report']['sourceRmse'],15)
        # Sharp small-font hinting differs from high-resolution rasterization; the user must see that uncertainty.
        if result['report']['sourceInkRmse'] > 22:
            self.assertTrue(result['report']['warnings'])
        self.assertEqual(result['report']['changedCharacters'],1)
        self.assertFalse(result['report']['contentVerified'])
        roundtrip=np.array(decode_image(image_url(output)))
        self.assertTrue(np.array_equal(roundtrip,output))

    def test_freehand_hard_boundary(self):
        selection={**self.selection,'mode':'freehand','points':[{'x':20,'y':9},{'x':85,'y':9},{'x':85,'y':47},{'x':20,'y':47}]}
        result=edit_image(self.image,selection,'2025','2026',preferred_font='simsun')
        self.assertEqual(result['report']['outsideChangedPixels'],0)

    def test_light_text_on_dark_gradient(self):
        image = ImageOps.invert(self.image)
        result = edit_image(image, self.selection, '2025', '2026', preferred_font='simsun')
        source = np.asarray(image.convert('RGBA'))
        changed = np.any(source != result['image'], axis=2)
        self.assertEqual(result['report']['polarity'], 'light')
        self.assertEqual(result['report']['outsideChangedPixels'], 0)
        self.assertTrue(changed.any())
        self.assertFalse(changed[:, :60].any(), 'Unchanged digits must remain exact, on dark backgrounds too')
        self.assertGreater(np.max(result['resultCrop'][changed[9:47, 20:85]]), 170)
        # Inverting both source and result must produce the same edit geometry.
        normal = edit_image(self.image, self.selection, '2025', '2026', preferred_font='simsun')
        self.assertTrue(np.array_equal(result['image'][:, :, :3], 255-normal['image'][:, :, :3]))

    def test_light_text_freehand_and_manual_contrast(self):
        image = ImageOps.invert(self.image)
        selection = {**self.selection, 'mode':'freehand', 'points':[
            {'x':20,'y':9}, {'x':85,'y':9}, {'x':85,'y':47}, {'x':20,'y':47}]}
        result = edit_image(image, selection, '2025', '2026', preferred_font='simsun', contrast='light')
        self.assertEqual(result['report']['outsideChangedPixels'], 0)
        with self.assertRaises(EditError):
            edit_image(image, selection, '2025', '2026', contrast='unknown')

    def test_invalid_requests_are_rejected(self):
        for original,replacement in [('', '6'),('2025','2025'),('2025','2026\nxx\nyy')]:
            with self.assertRaises(EditError): edit_image(self.image,self.selection,original,replacement)
        with self.assertRaises(EditError): edit_image(self.image,{'x':0,'y':0,'w':30,'h':8},'2025','2026')
        with self.assertRaises(EditError): edit_image(self.image,{'x':float('nan'),'y':0,'w':30,'h':20},'2025','2026')
        with self.assertRaises(EditError): edit_image(self.image,self.selection,'2025','2026',adjustments={'x':float('inf')})
        with self.assertRaises(EditError): decode_image('not-an-image')

    def test_transparent_patch_is_rejected(self):
        image=self.image.convert('RGBA');image.putpixel((30,20),(0,0,0,0))
        with self.assertRaises(EditError): edit_image(image,self.selection,'2025','2026')


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        EngineTests.setUpClass()
        cls.server=server.make_server(0)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(2)

    def request(self,path,data=None,token=True):
        headers={'X-Retouch-Token':server.SESSION_TOKEN} if token else {}
        if data is not None: headers['Content-Type']='application/json'
        request=urllib.request.Request(self.base+path,None if data is None else json.dumps(data).encode(),headers)
        with urllib.request.urlopen(request,timeout=20) as response: return json.load(response)

    def test_api_auth_and_job_roundtrip(self):
        session=self.request('/api/session',token=False);self.assertEqual(session['engine'],'cpu')
        with self.assertRaises(urllib.error.HTTPError) as failure: self.request('/api/edit',{},False)
        self.assertEqual(failure.exception.code,403)
        data={'image':image_url(EngineTests.image),'selection':EngineTests.selection,'original':'2025','replacement':'2026','font':'simsun'}
        task=self.request('/api/edit',data)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            job=self.request('/api/jobs/'+task['id'])
            if job['status']!='running': break
            time.sleep(.05)
        self.assertEqual(job['status'],'done',job)
        self.assertEqual(job['result']['report']['outsideChangedPixels'],0)
        self.assertEqual(decode_image(job['result']['image']).size,EngineTests.image.size)
        with self.assertRaises(urllib.error.HTTPError): self.request('/api/jobs/'+task['id'],token=False)

    def test_ocr_auth_and_selection_validation(self):
        with self.assertRaises(urllib.error.HTTPError) as failure:
            self.request('/api/ocr', {}, token=False)
        self.assertEqual(failure.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as failure:
            self.request('/api/ocr', {'image':image_url(EngineTests.image), 'selection':{'x':0,'y':0,'w':1,'h':1}})
        self.assertEqual(failure.exception.code, 400)

    def test_ocr_roundtrip(self):
        result = self.request('/api/ocr', {'image': image_url(EngineTests.image), 'selection': EngineTests.selection})
        self.assertTrue(result['available'], result)
        self.assertEqual(result['text'], '2025')
        self.assertGreater(result['confidence'], .9)

    def test_bad_host_is_rejected(self):
        request=urllib.request.Request(self.base+'/api/session',headers={'Host':'example.com'})
        with self.assertRaises(urllib.error.HTTPError) as failure: urllib.request.urlopen(request)
        self.assertEqual(failure.exception.code,403)


if __name__=='__main__': unittest.main()
