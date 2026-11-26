from pathlib import Path
import argparse,json,sys
import numpy as np
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.engine import edit_image
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--source',type=Path)
args=parser.parse_args()
source=args.source or Path(json.loads((root/'sample.local.json').read_text(encoding='utf-8-sig'))['path'])
original=Image.open(source).convert('RGBA')
result=edit_image(original,{'x':139,'y':174,'w':40,'h':25},'2025','2026',progress=lambda *args: print(args,flush=True))
output=root/'artifacts';output.mkdir(exist_ok=True)
Image.fromarray(result['image']).save(output/'验收样图-2026.png')
for k in ['originalCrop','resultCrop','reconstructionCrop']:
 Image.fromarray(result[k]).resize((800,500)).save(output/(k+'.png'))
Image.fromarray(result['mask']).save(output/'edit-mask.png')
# Independently verify the exported PNG, including the unchanged 202 prefix.
source_array=np.array(original)
exported=np.array(Image.open(output/'验收样图-2026.png').convert('RGBA'))
diff=np.any(source_array!=exported,axis=2)
assert exported.shape==source_array.shape
assert not diff[:,:166].any(),'The original 202 prefix or left side changed'
assert not diff[:179,:].any() and not diff[193:,:].any()
assert not diff[:,176:].any()
assert result['report']['outsideChangedPixels']==0
result['report']['independentChecks']={'exportDimensionsUnchanged':True,'prefix202Unchanged':True,'outsideChangedBoundsUnchanged':True}
(output/'验收报告.json').write_text(json.dumps(result['report'],ensure_ascii=False,indent=2),encoding='utf8')
# Present original and result at the same scale and include adjacent text.
left,top,right,bottom=(122,168,230,204)
canvas=Image.new('RGB',(864,2*180+70),'#f7f6ee')
draw=ImageDraw.Draw(canvas)
fontpath=Path('C:/Windows/Fonts/msyh.ttc')
face=ImageFont.truetype(str(fontpath),18)
for y,label,array in [(0,'修改前 · 2025',source_array),(215,'修改后 · 2026',exported)]:
 draw.text((12,y+3),label,font=face,fill='#646952')
 crop=Image.fromarray(array).crop((left,top,right,bottom)).convert('RGB').resize((864,180),Image.Resampling.LANCZOS)
 canvas.paste(crop,(0,y+35))
canvas.save(output/'验收局部对照.png')
print(json.dumps(result['report'],ensure_ascii=False,indent=2))
