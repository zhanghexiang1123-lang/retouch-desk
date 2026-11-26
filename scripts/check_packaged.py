"""Exercise the shipped executable from a folder without source code or a venv."""
from pathlib import Path
import argparse
import base64
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from PIL import Image

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--app', type=Path, default=root / 'release/RetouchDesk/RetouchDesk.exe')
parser.add_argument('--ui', action='store_true')
args = parser.parse_args()
exe = args.app.resolve()
expected_version = json.loads((root / 'package.json').read_text(encoding='utf-8'))['version']
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
base = f'http://127.0.0.1:{port}'
env = {k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}
process = subprocess.Popen([str(exe), '--no-open', '--port', str(port)], cwd=tempfile.gettempdir(), env=env)
token = ''

def request(path, data=None):
    headers = {'X-Retouch-Token':token}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(base+path, None if data is None else json.dumps(data).encode(), headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)

try:
    deadline=time.monotonic()+30
    while True:
        try:
            session=request('/api/session'); break
        except OSError:
            if process.poll() is not None or time.monotonic()>deadline:
                raise RuntimeError('Packaged server did not start')
            time.sleep(.15)
    assert session['version']==expected_version, session
    token=session['token']
    data='data:image/png;base64,'+base64.b64encode((root/'artifacts/dark-background-ocr-source.png').read_bytes()).decode()
    selection={'x':10,'y':10,'w':280,'h':70,'mode':'rectangle'}
    ocr=request('/api/ocr',{'image':data,'selection':selection})
    assert ocr['text']=='20261113',ocr
    task=request('/api/edit',{'image':data,'selection':selection,'original':ocr['text'],
                             'replacement':'20261114','font':'auto'})
    deadline=time.monotonic()+30
    while True:
        job=request('/api/jobs/'+task['id'])
        if job['status']!='running':break
        assert time.monotonic()<deadline,'Packaged edit timed out'
        time.sleep(.1)
    assert job['status']=='done',job
    report=job['result']['report']
    assert report['polarity']=='light',report
    assert report['outsideChangedPixels']==0,report
    result_bytes=base64.b64decode(job['result']['image'].split(',',1)[1])
    (root/'artifacts/local-0.5-packaged-result.png').write_bytes(result_bytes)
    verified=request('/api/ocr',{'image':job['result']['image'],'selection':selection})
    assert verified['text']=='20261114',verified
    evidence={'version':session['version'],'executable':str(exe),'startedOutsideProject':True,'ocr':ocr,
              'editReport':report,'resultOcr':verified,'passed':True}
    (root/'artifacts/local-0.5-packaged-check.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(evidence,ensure_ascii=False,indent=2),flush=True)
    if args.ui:
        subprocess.run(['node',str(root/'scripts/ui-workspace-check.mjs'),base],cwd=root,check=True,timeout=120)
        subprocess.run(['node',str(root/'scripts/ui-async-check.mjs'),base],cwd=root,check=True,timeout=120)
        subprocess.run(['node',str(root/'scripts/ui-appearance-check.mjs'),base],cwd=root,check=True,timeout=120)
finally:
    process.terminate()
    process.wait(timeout=10)
