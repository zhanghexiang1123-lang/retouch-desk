"""Loopback-only application server, serving the packaged UI and CPU edit jobs."""
from __future__ import annotations
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.engine import EditError, decode_image, edit_image, font_catalog, image_url
from backend.ocr import available as ocr_available, recognize, warmup as warmup_ocr

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
UI_ROOT = ROOT / 'dist'
SESSION_TOKEN = secrets.token_urlsafe(32)
JOBS = {}
JOBS_LOCK = threading.Lock()
EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1)
SAMPLE_PATH = None


def run_job(job_id, payload):
    def progress(phase, message, ratio):
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job or job.get('cancelled'):
                raise EditError('处理已取消。')
            job.update(phase=phase, message=message, progress=ratio)
    try:
        progress('analyzing','分析原字、背景与选区',.06)
        image=decode_image(payload.get('image'))
        result=edit_image(image,payload.get('selection'),payload.get('original',''),payload.get('replacement',''),
                          preferred_font=payload.get('font','auto'),contrast=payload.get('contrast','auto'),adjustments=payload.get('adjustments'),progress=progress)
        progress('checking','核对修改范围与原字重建误差',.94)
        data={'image':image_url(result['image']),'report':result['report'],
              'originalCrop':image_url(result['originalCrop']),'resultCrop':image_url(result['resultCrop']),
              'reconstructionCrop':image_url(result['reconstructionCrop'])}
        with JOBS_LOCK:
            job=JOBS.get(job_id)
            if job and not job.get('cancelled'):
                job.update(status='done',phase='done',message='预览已生成，请检查后保存',progress=1,result=data)
    except Exception as exc:
        with JOBS_LOCK:
            job=JOBS.get(job_id)
            if job:
                job.update(status='cancelled' if job.get('cancelled') else 'error',message=str(exc) if isinstance(exc,EditError) else '处理失败，请调整选区后重试。',progress=0)
        if not isinstance(exc,EditError):
            traceback.print_exc()


class Handler(BaseHTTPRequestHandler):
    server_version='RetouchDesk/0.5'
    def log_message(self, fmt, *args):
        if sys.stdout is not None:
            print(fmt%args,flush=True)

    def send_json(self, value, status=200):
        raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        try: self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError): pass

    def valid_host(self):
        host=self.headers.get('Host','')
        return host in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')

    def do_GET(self):
        if not self.valid_host():
            return self.send_json({'error':'不接受此主机来源。'},403)
        path=urlparse(self.path).path
        if path=='/api/session':
            return self.send_json({'token':SESSION_TOKEN,'engine':'cpu','version':'0.5.0','ocrAvailable':ocr_available(),
                  'fonts':[{'key':f.key,'name':f.name} for f in font_catalog()],
                  'sampleAvailable':bool(SAMPLE_PATH and SAMPLE_PATH.is_file())})
        if path.startswith('/api/jobs/'):
            if not secrets.compare_digest(self.headers.get('X-Retouch-Token',''),SESSION_TOKEN):
                return self.send_json({'error':'会话已失效，请刷新页面。'},403)
            with JOBS_LOCK:
                job=JOBS.get(path.rsplit('/',1)[-1])
                data=dict(job) if job else None
            return self.send_json(data,200) if data else self.send_json({'error':'任务不存在。'},404)
        if path=='/api/sample':
            if not secrets.compare_digest(self.headers.get('X-Retouch-Token',''),SESSION_TOKEN):
                return self.send_json({'error':'会话已失效。'},403)
            if not SAMPLE_PATH or not SAMPLE_PATH.is_file():
                return self.send_json({'error':'验收图片未配置，请手动上传。'},404)
            from PIL import Image,ImageOps
            with Image.open(SAMPLE_PATH) as image:
                data=image_url(ImageOps.exif_transpose(image).convert('RGBA'))
            return self.send_json({'image':data,'name':SAMPLE_PATH.name,
                'selection':{'x':139,'y':174,'w':40,'h':25,'mode':'rectangle'},'original':'2025','replacement':'2026'})
        if path.startswith('/api/'):
            return self.send_json({'error':'接口不存在。'},404)
        try:
            file=(UI_ROOT/unquote(path).lstrip('/')).resolve()
            if not file.is_relative_to(UI_ROOT.resolve()):
                return self.send_json({'error':'路径无效。'},403)
            if path=='/' or not file.is_file(): file=UI_ROOT/'index.html'
            if not file.is_file(): return self.send_json({'error':'界面未构建，请先运行 npm run build。'},503)
            import mimetypes
            mime=mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
            if file.suffix=='.js': mime='application/javascript'
            if file.suffix=='.css': mime='text/css'
            raw=file.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-cache')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError): pass

    def do_POST(self):
        if not self.valid_host() or not secrets.compare_digest(self.headers.get('X-Retouch-Token',''),SESSION_TOKEN):
            return self.send_json({'error':'会话已失效，请刷新页面。'},403)
        origin=self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
            return self.send_json({'error':'不接受跨站请求。'},403)
        path=urlparse(self.path).path
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=40_000_000:
                return self.send_json({'error':'请求过大，请选择小于 28MB 的图片。'},413)
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict): raise ValueError()
        except (ValueError,UnicodeDecodeError):
            return self.send_json({'error':'请求格式错误。'},400)
        if path=='/api/ocr':
            try:
                result = recognize(decode_image(payload.get('image')), payload.get('selection'),
                                   contrast=payload.get('contrast','auto'))
                return self.send_json(result)
            except EditError as exc:
                return self.send_json({'error':str(exc)},400)
            except Exception:
                traceback.print_exc()
                return self.send_json({'error':'识别暂不可用，请手动填写原文字。'},500)
        if path=='/api/edit':
            with JOBS_LOCK:
                if any(j['status']=='running' for j in JOBS.values()):
                    return self.send_json({'error':'已有处理任务，请等待完成或先取消。'},409)
                # Retain only two recent completed jobs; images stay in memory, never on the server disk.
                for key in list(JOBS)[:-2]: JOBS.pop(key,None)
                job_id=secrets.token_hex(12)
                JOBS[job_id]={'id':job_id,'status':'running','phase':'queued','message':'准备本地处理','progress':.02,'created':time.time()}
            EXECUTOR.submit(run_job,job_id,payload)
            return self.send_json({'id':job_id},202)
        if path=='/api/cancel':
            with JOBS_LOCK:
                job=JOBS.get(payload.get('id'))
                if job and job['status']=='running': job.update(cancelled=True,status='cancelled',message='处理已取消。')
            return self.send_json({'ok':True})
        return self.send_json({'error':'接口不存在。'},404)


def make_server(port=0):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True
    threading.Thread(target=warmup_ocr, daemon=True, name='ocr-warmup').start()
    return server


def main():
    global SAMPLE_PATH
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--browser',action='store_true')
    parser.add_argument('--no-open',action='store_true')
    parser.add_argument('--sample',type=Path)
    args=parser.parse_args()
    SAMPLE_PATH=args.sample
    config=(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1])/'sample.local.json'
    if not SAMPLE_PATH and config.is_file():
        try: SAMPLE_PATH=Path(json.loads(config.read_text(encoding='utf-8-sig'))['path'])
        except (ValueError,KeyError): pass
    server=make_server(args.port)
    url=f'http://127.0.0.1:{server.server_port}'
    if sys.stdout is not None: print('Retouch Desk ready: '+url,flush=True)
    if args.no_open:
        try: server.serve_forever()
        except KeyboardInterrupt: pass
    else:
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        if not args.browser:
            try:
                import webview
                webview.settings['ALLOW_DOWNLOADS']=True
                webview.create_window('Retouch Desk · 图片文字精修',url,width=1440,height=960,min_size=(820,650),background_color='#f2f3f5')
                webview.start(gui='edgechromium')
                server.shutdown()
                return
            except Exception:
                if sys.stderr is not None: traceback.print_exc()
        import webbrowser
        webbrowser.open(url)
        try:
            while thread.is_alive(): thread.join(1)
        except KeyboardInterrupt: pass
    server.server_close()
    EXECUTOR.shutdown(wait=False,cancel_futures=True)

if __name__=='__main__': main()
