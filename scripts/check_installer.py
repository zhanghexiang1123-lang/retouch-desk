"""Install the production installer in an isolated folder, exercise it, then uninstall.
Refuses to touch a pre-existing install or desktop shortcut.
"""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
import winreg

root = Path(__file__).resolve().parents[1]
version = json.loads((root / 'package.json').read_text(encoding='utf-8'))['version']
setup = root / f'release/installer/RetouchDesk-{version}-Setup-x64.exe'
key_name = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{DB2F07BA-521C-49AF-939D-DA097745F905}_is1'
access = winreg.KEY_READ | winreg.KEY_WOW64_64KEY

def installed():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name, 0, access) as key:
            return {name: winreg.QueryValueEx(key, name)[0] for name in ('DisplayName','DisplayVersion','InstallLocation','UninstallString')}
    except FileNotFoundError:
        return None

assert installed() is None, 'Existing installation found. Test aborted to preserve it.'
with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
    desktop = Path(os.path.expandvars(winreg.QueryValueEx(key,'Desktop')[0]))
shortcut = desktop / 'Retouch Desk.lnk'
assert not shortcut.exists(), 'Existing desktop shortcut found. Test aborted to preserve it.'
expected_hash = Path(str(setup)+'.sha256').read_text().split()[0]
assert hashlib.sha256(setup.read_bytes()).hexdigest() == expected_hash
run_id = uuid.uuid4().hex[:8]
target = root / 'artifacts' / f'安装包验证 {run_id}'
group_name = 'Retouch Desk'
group = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs' / group_name
assert not target.exists() and not group.exists()
install_log = root / 'artifacts/installer-0.5-install.log'
uninstall_log = root / 'artifacts/installer-0.5-uninstall.log'
evidence = {'version':version,'installer':str(setup),'sha256':expected_hash,'testDirectory':str(target)}
created = False
try:
    subprocess.run([str(setup),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/CURRENTUSER','/LANG=chinesesimplified',
                    '/DIR='+str(target),'/GROUP='+group_name,'/TASKS=desktopicon','/LOG='+str(install_log)], check=True, timeout=120)
    created = True
    exe = target / 'RetouchDesk.exe'
    uninstaller = target / 'unins000.exe'
    assert exe.is_file() and uninstaller.is_file(), 'Installed executable missing'
    assert shortcut.is_file() and (group/'Retouch Desk.lnk').is_file() and (group/'卸载 Retouch Desk.lnk').is_file(), 'Missing shortcut'
    entry = installed()
    assert entry and entry['DisplayVersion'] == version, entry
    assert Path(entry['InstallLocation']).resolve() == target.resolve(), entry
    assert not (target/'sample.local.json').exists(), 'Local sample config should not ship in installer'
    evidence.update(installed=True,shortcuts=True,uninstallEntry=entry)
    # Verify the desktop shortcut resolves to this installation.
    env = dict(os.environ, RETOUCH_QA_SHORTCUT=str(shortcut))
    # PowerShell redirected output encoding depends on the host; use JSON file for Unicode path verification.
    verify_file = root/'artifacts/installer-shortcut-target.json'
    cmd = "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut($env:RETOUCH_QA_SHORTCUT); @{target=$s.TargetPath;workingDirectory=$s.WorkingDirectory} | ConvertTo-Json | Set-Content -LiteralPath $env:RETOUCH_QA_TARGET -Encoding UTF8"
    subprocess.run(['powershell.exe','-NoProfile','-Command',cmd],env=dict(env,RETOUCH_QA_TARGET=str(verify_file)),check=True,timeout=15)
    shortcut_data=json.loads(verify_file.read_text(encoding='utf-8-sig'))
    assert Path(shortcut_data['target']).resolve()==exe.resolve(),shortcut_data
    evidence['shortcutTarget']=shortcut_data
    subprocess.run([sys.executable,str(root/'scripts/check_packaged.py'),'--app',str(exe),'--ui'],check=True,cwd=root,timeout=240)
    evidence['ocrEditAndUI']=True
    # Open the actual native window and confirm its title and visible bounds.
    native = subprocess.Popen([str(exe)],cwd=target)
    try:
        user32=ctypes.WinDLL('user32',use_last_error=True)
        callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
        user32.IsWindowVisible.argtypes=[wintypes.HWND]
        user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowTextLengthW.argtypes=[wintypes.HWND]
        user32.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
        user32.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
        user32.EnumWindows.argtypes=[callback_type,wintypes.LPARAM]
        windows=[]
        @callback_type
        def visit(hwnd, _):
            pid=wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            if pid.value==native.pid and user32.IsWindowVisible(hwnd):
                text=ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd)+1)
                user32.GetWindowTextW(hwnd,text,len(text))
                if 'Retouch Desk' in text.value:
                    rect=wintypes.RECT();user32.GetWindowRect(hwnd,ctypes.byref(rect))
                    windows.append({'title':text.value,'width':rect.right-rect.left,'height':rect.bottom-rect.top})
            return True
        deadline=time.monotonic()+35
        while not windows:
            assert native.poll() is None,'Native application exited early'
            user32.EnumWindows(visit,0)
            if time.monotonic()>deadline:raise RuntimeError('Native application window did not appear')
            time.sleep(.15)
        assert windows[0]['width']>=820 and windows[0]['height']>=650,windows
        evidence['nativeWindow']=windows[0]
        print('PASS native desktop window:',windows[0],flush=True)
    finally:
        native.terminate();native.wait(timeout=15)
finally:
    # Only uninstall an app created by this test at the verified exact target.
    if created and (target/'unins000.exe').exists():
        entry=installed()
        assert entry and Path(entry['InstallLocation']).resolve()==target.resolve(),'Refusing to uninstall an unrelated application'
        subprocess.run([str(target/'unins000.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/LOG='+str(uninstall_log)],check=True,timeout=90)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline and (target.exists() or installed() is not None):time.sleep(.2)
        assert not target.exists(),'Install directory remains after uninstall'
        assert installed() is None and not shortcut.exists() and not group.exists(),'Installation entries remain after uninstall'
        evidence['uninstalledCleanly']=True
        print('PASS clean uninstall; temporary installation and shortcuts removed',flush=True)
evidence['passed']=True
(root/'artifacts/installer-0.5-qa.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(evidence,ensure_ascii=False,indent=2),flush=True)
