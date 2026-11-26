"""CPU-only text reconstruction and local compositing. No cloud calls or GPU."""
from __future__ import annotations

import base64
import io
import math
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy.optimize import least_squares

MAX_PIXELS = 24_000_000
SCALE = 4


class EditError(ValueError):
    pass


@dataclass
class FontEntry:
    key: str
    name: str
    path: str
    index: int = 0


def font_catalog():
    windows = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    definitions = [
        ('times-bold', 'Times New Roman · 粗体', 'timesbd.ttf'),
        ('times', 'Times New Roman', 'times.ttf'),
        ('simsun', '宋体', 'simsun.ttc'),
        ('georgia-bold', 'Georgia · 粗体', 'georgiab.ttf'),
        ('georgia', 'Georgia', 'georgia.ttf'),
        ('cambria-bold', 'Cambria · 粗体', 'cambriab.ttf'),
        ('cambria', 'Cambria', 'cambria.ttc'),
        ('arial-bold', 'Arial · 粗体', 'arialbd.ttf'),
        ('arial', 'Arial', 'arial.ttf'),
        ('yahei', '微软雅黑', 'msyh.ttc'),
        ('yahei-bold', '微软雅黑 · 粗体', 'msyhbd.ttc'),
        ('simhei', '黑体', 'simhei.ttf'),
        ('fangsong', '仿宋', 'simfang.ttf'),
        ('kaiti', '楷体', 'simkai.ttf'),
        ('calibri', 'Calibri', 'calibri.ttf'),
        ('calibri-bold', 'Calibri · 粗体', 'calibrib.ttf'),
    ]
    entries = [FontEntry(key, name, str(windows / filename))
               for key, name, filename in definitions if (windows / filename).is_file()]
    for folder in [Path.home() / 'AppData/Local/Microsoft/Windows/Fonts', Path('/usr/share/fonts/truetype/dejavu')]:
        if folder.exists():
            for file in list(folder.glob('*.ttf'))[:32]:
                entries.append(FontEntry('user-' + file.stem, file.stem, str(file)))
    return entries


@lru_cache(maxsize=128)
def get_font(path, index=0):
    return ImageFont.truetype(path, 96, index=index)


def decode_image(value):
    if not isinstance(value, str) or not value.startswith('data:image/') or ',' not in value:
        raise EditError('请上传 PNG、JPEG 或 WebP 图片。')
    try:
        raw = base64.b64decode(value.split(',', 1)[1], validate=True)
        im = Image.open(io.BytesIO(raw))
        if im.width * im.height > MAX_PIXELS:
            raise EditError('图片超过 2400 万像素，请先缩小。')
        return ImageOps.exif_transpose(im).convert('RGBA')
    except EditError:
        raise
    except Exception as exc:
        raise EditError('图片无法解码，请重新选择文件。') from exc


def image_url(array):
    image = array if isinstance(array, Image.Image) else Image.fromarray(np.asarray(array, np.uint8))
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


def validate_selection(selection, image_size):
    try:
        values = [float(selection[k]) for k in ('x', 'y', 'w', 'h')]
    except (TypeError, KeyError, ValueError):
        raise EditError('请先框选完整的原文字。')
    if not all(math.isfinite(value) for value in values):
        raise EditError('选区坐标无效。')
    x, y, w, h = values
    iw, ih = image_size
    left, top = max(0, math.floor(x)), max(0, math.floor(y))
    right, bottom = min(iw, math.ceil(x+w)), min(ih, math.ceil(y+h))
    if right-left < 4 or bottom-top < 5:
        raise EditError('选区太小，请包含完整文字及少量空白。')
    if right-left > 1200 or bottom-top > 400:
        raise EditError('一次请处理一行或一处文字，选区宽度不超过 1200、高度不超过 400 像素。')
    if (right-left)*(bottom-top) > 200_000:
        raise EditError('精修选区过大，请缩小到一行文字。')
    mask = np.ones((bottom-top, right-left), np.uint8)
    points = selection.get('points')
    if selection.get('mode') == 'freehand':
        if not isinstance(points, list) or not 3 <= len(points) <= 10000:
            raise EditError('自由画圈需要形成一个完整区域。')
        try:
            pts = np.array([[float(p['x'])-left, float(p['y'])-top] for p in points], np.float64)
        except (KeyError, TypeError, ValueError):
            raise EditError('自由选区坐标无效。')
        if not np.isfinite(pts).all() or np.abs(pts).max() > 1e7:
            raise EditError('自由选区坐标无效。')
        mask[:] = 0
        cv2.fillPoly(mask, [np.round(pts).astype(np.int32)], 1)
    return (left, top, right, bottom), mask


def text_polarity(rgb, allowed, mode='auto'):
    """Return a contrast direction; the larger Otsu cluster estimates the background."""
    if mode not in ('auto', 'dark', 'light'):
        raise EditError('文字颜色策略无效，请选择自动、深色字或浅色字。')
    if mode != 'auto':
        return mode
    values = np.round(rgb.mean(axis=2)[allowed > 0]).astype(np.uint8)
    if values.size < 15:
        raise EditError('选区缺少背景参考，请为文字留出少量空白。')
    _, classes = cv2.threshold(values.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return 'dark' if np.count_nonzero(classes) >= values.size / 2 else 'light'


def smooth_background(rgb, allowed):
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[-1:1:complex(h), -1:1:complex(w)]
    design = np.stack([np.ones_like(xx), xx, yy, xx*yy, xx*xx, yy*yy], axis=-1).reshape(-1, 6)
    flat = rgb.reshape(-1, 3).astype(float)
    gray = flat.mean(axis=1)
    valid = allowed.ravel() > 0
    if np.count_nonzero(valid) < 15:
        raise EditError('选区缺少背景参考，请为文字留出少量空白。')
    keep = valid & (gray >= np.percentile(gray[valid], 40))
    for _ in range(5):
        if np.count_nonzero(keep) < 15:
            raise EditError('选区缺少背景参考，请为文字留出少量空白。')
        coefficients = np.linalg.lstsq(design[keep], flat[keep], rcond=None)[0]
        residual = (design @ coefficients-flat).mean(axis=1)
        noise = max(1.0, np.std(residual[keep]))
        keep = valid & (residual < max(5.0, noise*2.2)) & (residual > -max(7.0, noise*3))
    background = np.clip((design @ coefficients).reshape(h, w, 3), 0, 255)
    residual = background.mean(axis=2)-rgb.mean(axis=2)
    return background, residual, float(noise)


class GlyphRun:
    def __init__(self, entry, text, reference=None):
        self.entry, self.text = entry, text
        self.font = get_font(entry.path, entry.index)
        self.reference = reference or text
        refbox = self.font.getbbox(self.reference)
        self.refbox = refbox
        self.refwidth = max(1, refbox[2]-refbox[0])
        self.refheight = max(1, refbox[3]-refbox[1])
        self.pad = 32
        maxwidth = max(self.font.getlength(text), self.font.getlength(self.reference))
        self.shape = (int(maxwidth)+2*self.pad+20, 210)
        self.origin = (self.pad-refbox[0], self.pad-refbox[1])
        self.alpha = self.draw()

    def draw(self, indexes=None):
        im = Image.new('L', self.shape, 0)
        painter = ImageDraw.Draw(im)
        if indexes is None:
            painter.text(self.origin, self.text, font=self.font, fill=255)
        else:
            for index in indexes:
                if index >= len(self.text):
                    continue
                x = self.origin[0]+self.font.getlength(self.text[:index])
                painter.text((x, self.origin[1]), self.text[index], font=self.font, fill=255)
        return np.asarray(im, np.float32)/255

    def transform(self, params, shape, alpha=None):
        x, y, width, height, shear, angle, blur, darkness = params
        sx, sy = width/self.refwidth, height/self.refheight
        theta = math.radians(angle)
        rot = np.array([[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]])
        linear = rot @ np.array([[sx, shear*sy], [0, sy]])
        translate = np.array([x, y])-linear @ np.array([self.pad, self.pad])
        affine = np.column_stack([linear, translate])*SCALE
        h, w = shape
        big = cv2.warpAffine(self.alpha if alpha is None else alpha, affine, (w*SCALE, h*SCALE), flags=cv2.INTER_LINEAR)
        low = cv2.resize(big, (w, h), interpolation=cv2.INTER_AREA)
        if blur > .025:
            low = cv2.GaussianBlur(low, (0, 0), blur)
        return np.clip(low, 0, 1)


def fit_one(entry, text, target, allowed, initial_bbox, noise):
    run = GlyphRun(entry, text)
    h, w = target.shape
    x, y, iw, ih = initial_bbox
    start = np.array([x, y, iw, ih, 0, 0, .35, min(220, max(30, target.max()*1.35))], float)
    lower = np.array([-w*.3, -h*.3, max(2, iw*.65), max(3, ih*.65), -.4, -25, .03, 15])
    upper = np.array([w, h, max(4, iw*1.45), max(5, ih*1.45), .4, 25, 2.2, 254])
    start = np.clip(start, lower+.001, upper-.001)
    # Weight dark pixels and their neighborhoods, keeping enough background to penalize spurious strokes.
    weights = np.where(cv2.dilate((target>max(10, noise*3)).astype(np.uint8), np.ones((3,3),np.uint8))>0, 1.0, .45)
    weights *= allowed
    def residual(p):
        return ((run.transform(p, (h,w))*p[7]-target)*weights).ravel()/100
    increments = np.array([.04,.04,.05,.05,.002,.06,.018,.3])
    def jac(p):
        cols=[]
        for i, step in enumerate(increments):
            plus, minus = p.copy(), p.copy()
            plus[i]+=step
            minus[i]-=step
            cols.append((residual(plus)-residual(minus))/(2*step))
        return np.column_stack(cols)
    fit = least_squares(residual, start, jac=jac, bounds=(lower,upper), max_nfev=80,
                        loss='soft_l1', f_scale=.17, ftol=1e-5, xtol=2e-5, gtol=1e-5)
    prediction = run.transform(fit.x, (h,w))*fit.x[7]
    signal = target>max(8, noise*2.5)
    rmse = float(np.sqrt(np.mean((prediction[allowed>0]-target[allowed>0])**2)))
    ink_rmse = float(np.sqrt(np.mean((prediction[signal]-target[signal])**2))) if signal.any() else 255
    error = float(np.mean((prediction-target)**2*weights))
    return {'font':entry, 'run':run, 'params':fit.x, 'rmse':rmse, 'inkRmse':ink_rmse, 'error':error}


def changed_indexes(original, replacement):
    if len(original)==len(replacement):
        return [i for i, (a,b) in enumerate(zip(original,replacement)) if a!=b]
    return list(range(max(len(original),len(replacement))))


def edit_image(image, selection, original_text, replacement_text, *, preferred_font='auto', contrast='auto', adjustments=None, progress=None):
    started = time.monotonic()
    original_text, replacement_text = str(original_text).strip(), str(replacement_text).strip()
    if not original_text or not replacement_text:
        raise EditError('请填写选区内的原文字和替换文字。')
    if any(c in original_text+replacement_text for c in '\r\n') or max(len(original_text),len(replacement_text))>40:
        raise EditError('一次支持一行、最多 40 个字符。')
    indexes = changed_indexes(original_text,replacement_text)
    if not indexes:
        raise EditError('新旧文字相同，无需修改。')
    rgba = np.asarray(image.convert('RGBA')).copy()
    bounds, allowed = validate_selection(selection,image.size)
    left,top,right,bottom = bounds
    rgb = rgba[top:bottom,left:right,:3].copy()
    if (rgba[top:bottom,left:right,3] != 255).any():
        raise EditError('当前精修引擎需要不透明背景，请先处理透明区域。')
    original_rgb = rgb.copy()
    polarity = text_polarity(rgb, allowed, contrast)
    if polarity == 'light':
        rgb = 255 - rgb
    background,target,noise = smooth_background(rgb,allowed)
    target *= allowed
    ink = (target>max(16,noise*4)).astype(np.uint8)
    count = int(ink.sum())
    if count<6:
        raise EditError('没有检测到足够清晰的文字笔画。请框住完整文字并留少量背景，或切换文字颜色策略。')
    ys,xs = np.nonzero(ink)
    bbox = [float(xs.min()),float(ys.min()),float(xs.max()-xs.min()+1),float(ys.max()-ys.min()+1)]
    entries=font_catalog()
    if preferred_font!='auto':
        entries=[f for f in entries if f.key==preferred_font]
        if not entries:
            raise EditError('当前字体在此电脑上不可用，请重新选择。')
    if not entries:
        raise EditError('没有可用字体，请先安装常用字体。')
    fits=[]
    for i,entry in enumerate(entries):
        if progress:
            progress('fitting',f'原字重建 · {entry.name}',.12+.56*i/len(entries))
        # Exclude fonts whose missing-glyph box would otherwise look like a valid candidate.
        face=get_font(entry.path,entry.index)
        missing=face.getmask('\uffff')
        if any(char.strip() and face.getmask(char).size==missing.size and bytes(face.getmask(char))==bytes(missing) for char in set(original_text+replacement_text)):
            continue
        fit=fit_one(entry,original_text,target,allowed,bbox,noise)
        fits.append(fit)
    if not fits:
        raise EditError('所选字体缺少所需字符，请选择含这些文字的字体。')
    fits.sort(key=lambda f:f['error'])
    best=fits[0]
    params=best['params'].copy()
    adjustment=adjustments or {}
    def numeric(key,lo,hi,default=0):
        try:
            value=float(adjustment.get(key,default))
        except (TypeError,ValueError):
            raise EditError('微调参数必须为数字。')
        if not math.isfinite(value) or not lo<=value<=hi:
            raise EditError(f'微调参数 {key} 超出范围。')
        return value
    params[0]+=numeric('x',-30,30)
    params[1]+=numeric('y',-30,30)
    params[2]*=numeric('width',.5,1.5,1)
    params[3]*=numeric('height',.5,1.5,1)
    params[5]+=numeric('angle',-15,15)
    params[6]=max(.03,params[6]+numeric('blur',-1,1))
    params[7]*=numeric('darkness',.5,1.5,1)
    if progress: progress('compositing','只修复变更字符，保留其余原始像素',.75)
    run=best['run']
    newrun=GlyphRun(best['font'],replacement_text,reference=original_text)
    old_alpha=run.transform(best['params'],target.shape,run.draw(indexes))
    new_alpha=newrun.transform(params,target.shape,newrun.draw(indexes))
    union=(old_alpha>.012)|(new_alpha>.012)
    # The selection is a hard boundary, including freehand paths.
    if np.any((new_alpha>.15)&(allowed==0)):
        raise EditError('新字超出自由选区，请扩大圈选范围或减小宽高。')
    if (new_alpha[[0,-1],:]>.12).any() or (new_alpha[:,[0,-1]]>.12).any():
        raise EditError('新文字贴近选区边界，请扩大选区。')
    # Protect the original raster pixels of unchanged character cells.
    ownership = np.ones(target.shape, bool)
    if len(original_text)==len(replacement_text):
        x0,y0,ww,hh,ss,aa,bb,dd = best['params']
        theta=math.radians(aa)
        matrix=np.array([[math.cos(theta),-math.sin(theta)],[math.sin(theta),math.cos(theta)]]) @ np.array([[ww/run.refwidth,ss*hh/run.refheight],[0,hh/run.refheight]])
        yy,xx=np.mgrid[:target.shape[0],:target.shape[1]]
        local=np.linalg.inv(matrix) @ np.stack([xx.ravel()+.5-x0,yy.ravel()+.5-y0])
        glyph_x=local[0].reshape(target.shape)+run.refbox[0]
        # A half-pixel tolerance captures edge antialiasing without entering the neighboring glyph.
        ownership[:]=False
        for index in indexes:
            lo=-1e9 if index==0 else run.font.getlength(original_text[:index])-.5*run.refwidth/ww
            hi=1e9 if index==len(original_text)-1 else run.font.getlength(original_text[:index+1])-.5*run.refwidth/ww
            ownership |= (glyph_x>=lo)&(glyph_x<hi)
        if np.any((new_alpha>.2)&~ownership):
            raise EditError('新字进入了相邻原字的位置，请减小位置或字宽微调。')
    original_ink=(target>max(4,noise*1.5))&(cv2.dilate((old_alpha>.035).astype(np.uint8),np.ones((3,3),np.uint8))>0)
    erase_mask=cv2.dilate(original_ink.astype(np.uint8),np.ones((3,3),np.uint8))
    erase_mask*=allowed
    erase_mask*=ownership.astype(np.uint8)
    repaired=cv2.inpaint(rgb,erase_mask*255,3,cv2.INPAINT_TELEA).astype(float)
    # For flat paper, use the fitted illumination plus local texture from the inpainted neighborhood.
    repair=background+(repaired-background)*.65
    cleaned=rgb.astype(float).copy()
    cleaned[erase_mask>0]=repair[erase_mask>0]
    # Estimate an ink RGB vector from actual source strokes and the fitted alpha, preserving tint.
    all_alpha=run.transform(best['params'],target.shape)
    usable=(all_alpha>.13)&(allowed>0)
    alpha=all_alpha[usable,None]
    delta=(background-rgb)[usable]
    ink_rgb=np.mean(background[usable],axis=0)-np.sum(delta*alpha,axis=0)/max(.001,float(np.sum(alpha*alpha)))
    ink_rgb=np.clip(ink_rgb,0,255)
    # Only replacement glyphs are composited. Unchanged glyphs retain their exact source pixels.
    darkness_ratio=params[7]/best['params'][7]
    replacement_ink=np.clip(np.mean(background[usable],axis=0)-(np.mean(background[usable],axis=0)-ink_rgb)*darkness_ratio,0,255)
    composite=cleaned*(1-new_alpha[:,:,None])+replacement_ink*new_alpha[:,:,None]
    editmask=((erase_mask>0)|(new_alpha>.002))&(allowed>0)&ownership
    patch=rgb.copy()
    patch[editmask]=np.round(np.clip(composite[editmask],0,255)).astype(np.uint8)
    if polarity == 'light':
        patch = 255 - patch
    result=rgba.copy()
    result[top:bottom,left:right,:3]=patch
    diff=np.any(result!=rgba,axis=2)
    boundary=np.zeros(diff.shape,np.uint8)
    boundary[top:bottom,left:right]=allowed
    outside=int(np.count_nonzero(diff&(boundary==0)))
    # Source reconstruction is presented separately from the replacement result.
    reconstruction=background-all_alpha[:,:,None]*(np.mean(background[usable],axis=0)-ink_rgb)
    candidates=[{'key':f['font'].key,'name':f['font'].name,'rmse':round(f['rmse'],2),'inkRmse':round(f['inkRmse'],2)} for f in fits[:6]]
    global_mask=np.zeros(diff.shape,np.uint8)
    global_mask[top:bottom,left:right]=editmask.astype(np.uint8)*255
    warnings=[]
    if best['inkRmse']>22:
        warnings.append('原字重建仍有明显差异，建议切换字体候选或人工微调；此结果不视为通过观感验收。')
    if len(original_text)!=len(replacement_text):
        warnings.append('字符数量变化，本次重排整组选区，请检查字距和两侧留白。')
    if max(abs(params[5]),abs(params[4])*30)>15:
        warnings.append('选区倾斜较大，当前只拟合仿射变换，无法恢复纸张弯曲。')
    ys,xs=np.nonzero(diff)
    changed_bounds=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)] if len(xs) else None
    report={
        'engine':'CPU · 原字重建 / OpenCV 局部修复', 'font':best['font'].name,'fontKey':best['font'].key,
        'original':original_text,'replacement':replacement_text,'changedCharacters':len(indexes),
        'polarity':polarity,'textColorMode':'浅色字 / 深色背景' if polarity == 'light' else '深色字 / 浅色背景',
        'changedPixels':int(diff.sum()),'outsideChangedPixels':outside,'sourceRmse':round(best['rmse'],2),
        'sourceInkRmse':round(best['inkRmse'],2),'noise':round(noise,2),
        'angle':round(float(params[5]),2),'blur':round(float(params[6]),2),
        'inkHeight':round(float(params[3]),2),'seconds':round(time.monotonic()-started,2),
        'bounds':list(bounds),'changedBounds':changed_bounds,'candidates':candidates,'warnings':warnings,
        'acceptance':'像素范围检查通过；文字与观感待人工确认' if outside==0 else '范围检查失败',
        'contentVerified':False,
    }
    if polarity == 'light':
        reconstruction = 255 - reconstruction
    return {'image':result,'report':report,'originalCrop':original_rgb,'resultCrop':patch,
            'reconstructionCrop':np.round(np.clip(reconstruction,0,255)).astype(np.uint8),'mask':global_mask}
