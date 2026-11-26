"""Offline selection OCR. Model weights ship with RapidOCR; no runtime downloads."""
from __future__ import annotations

from functools import lru_cache
import importlib.util
import threading
import time

import cv2
import numpy as np
from PIL import Image

from backend.engine import EditError, smooth_background, text_polarity, validate_selection

OCR_LOCK = threading.Lock()


def available():
    return importlib.util.find_spec('rapidocr_onnxruntime') is not None


@lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1,
                    use_cls=False, det_limit_side_len=512, det_limit_type='max')


def warmup():
    try:
        with OCR_LOCK:
            _engine()
    except Exception:
        # A missing optional OCR runtime must never disable manual editing.
        pass


def recognize(image: Image.Image, selection: dict, *, contrast='auto'):
    started = time.monotonic()
    response = {'available': available(), 'text': '', 'confidence': 0,
                'method': 'RapidOCR / PP-OCRv4 CPU', 'alternatives': [], 'needsReview': True}
    if not response['available']:
        return {**response, 'seconds': 0, 'message': '未安装本地 OCR 组件，请手动填写原文字。'}
    bounds, allowed = validate_selection(selection, image.size)
    rgba = np.asarray(image.convert('RGBA').crop(bounds))
    if np.any(rgba[:, :, 3][allowed > 0] != 255):
        raise EditError('请框选不透明的文字区域。')
    rgb = rgba[:, :, :3].copy()
    polarity = text_polarity(rgb, allowed, contrast)
    if polarity == 'light':
        rgb = 255 - rgb
    background, signal, noise = smooth_background(rgb, allowed)
    signal = np.maximum(0, signal) * allowed
    ink = signal > max(12, noise * 3)
    if np.count_nonzero(ink) < 6:
        return {**response, 'seconds': round(time.monotonic() - started, 3),
                'message': '未识别到清晰文字，请调整选区或手动填写。'}
    yy, xx = np.nonzero(ink)
    x0, y0 = max(0, xx.min() - 2), max(0, yy.min() - 2)
    x1, y1 = min(rgb.shape[1], xx.max() + 3), min(rgb.shape[0], yy.max() + 3)
    strength = max(24., float(np.percentile(signal[ink], 95)))
    normalized = np.round(255 - np.clip(signal * 255 / strength, 0, 255)).astype(np.uint8)
    normalized = cv2.cvtColor(normalized, cv2.COLOR_GRAY2BGR)[y0:y1, x0:x1]
    raw = rgb.copy()
    raw[allowed == 0] = np.round(background[allowed == 0]).astype(np.uint8)
    raw = raw[y0:y1, x0:x1, ::-1].copy()
    scale = min(4., max(1., 56. / max(1, y1-y0)), 2400. / max(1, x1-x0))

    def prepare(array):
        if scale != 1:
            array = cv2.resize(array, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        return cv2.copyMakeBorder(array, 6, 6, 8, 8, cv2.BORDER_CONSTANT, value=(255, 255, 255))

    candidates = []
    try:
        with OCR_LOCK:
            engine = _engine()
            crop = prepare(normalized)
            result, _ = engine(crop, use_det=False, use_cls=False)
            if result:
                candidates.append((str(result[0][0]).strip(), float(result[0][1])))
            # Keep the common single-line case fast; use detection and the source
            # appearance as fallbacks when the first recognition is uncertain.
            if not candidates or candidates[0][1] < .92:
                source = prepare(raw)
                fallback, _ = engine(source, use_det=True, use_cls=False)
                if fallback:
                    fallback.sort(key=lambda item: (min(p[1] for p in item[0]), min(p[0] for p in item[0])))
                    candidates.append((''.join(str(item[1]).strip() for item in fallback),
                                       float(np.mean([item[2] for item in fallback]))))
                direct, _ = engine(source, use_det=False, use_cls=False)
                if direct:
                    candidates.append((str(direct[0][0]).strip(), float(direct[0][1])))
    except Exception as exc:
        return {**response, 'available': False, 'seconds': round(time.monotonic()-started, 3),
                'message': f'本地识别暂不可用（{type(exc).__name__}），可以手动填写原文字。'}
    candidates = sorted(((text, score) for text, score in candidates if text), key=lambda c: c[1], reverse=True)
    if not candidates:
        return {**response, 'seconds': round(time.monotonic()-started, 3),
                'message': '未识别到清晰文字，请调整选区或手动填写。'}
    text, confidence = candidates[0]
    alternatives = list(dict.fromkeys(t for t, s in candidates[1:] if t != text))
    needs_review = confidence < .9 or bool(alternatives) or len(text) > 40
    return {**response, 'text': text, 'confidence': round(max(0., min(1., confidence)), 4),
            'alternatives': alternatives, 'needsReview': needs_review,
            'polarity': polarity, 'seconds': round(time.monotonic()-started, 3),
            'message': '识别存在不确定，请核对并手动修正。' if needs_review else '已识别，可手动修改后再生成预览。'}
