$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
& npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw '前端构建失败。' }
$uiData = (Join-Path $taskRoot 'dist') + ';dist'
$iconPath = Join-Path $taskRoot 'assets\app-icon.ico'
& '.\.venv\Scripts\python.exe' -m PyInstaller --noconfirm --clean --windowed --onedir --name RetouchDesk --icon $iconPath --distpath release --workpath build --specpath build --add-data $uiData --paths $taskRoot --collect-data webview --collect-binaries webview --hidden-import webview.platforms.edgechromium --hidden-import scipy.special._special_ufuncs --collect-all rapidocr_onnxruntime --collect-data onnxruntime --collect-binaries onnxruntime backend/server.py
if ($LASTEXITCODE -ne 0) { throw '桌面应用打包失败。' }
$packageNotes = @'
Retouch Desk 0.5

双击 RetouchDesk.exe 打开图片文字精修工作台。
整个 RetouchDesk 文件夹需要放在一起，不能只复制 exe。
无需安装 Node.js、Python 或显卡驱动，运行时无需联网。
需要 Windows 10/11 和 Microsoft Edge WebView2 Runtime；缺少时会尝试使用默认浏览器。
图片在本机处理，不会上传。
支持浅底深字与深底浅字的单行印刷文字，自动判断文字深浅，也可手动切换。
矩形框选或自由画圈后，使用本地 RapidOCR 自动填写原文；始终可手动修正。
OCR 模型随程序提供，首次加载约需数秒，后续小选区通常更快；准确率需人工核对。
人工输入不会被正在返回的识别结果覆盖；点击“使用识别结果”可主动采用候选。
支持多选或拖入多张图片，顶部标签切换；每张图片独立保留选区、输入和最近 5 步修改历史。
点击“取消框选”或按 Esc 清除选区，放弃当前未采用预览，不影响已采用修改。
撤销后可点击重做恢复；快捷键为 Ctrl+Z、Ctrl+Y 或 Ctrl+Shift+Z。
关闭标签会丢弃该图片的会话，请先导出需要保留的结果。
字体从当前 Windows 系统读取，换一台电脑可能匹配到不同候选。
导出 PNG 时使用保存对话框。请在采用结果前检查局部放大图。

本版本采用简约灰白界面与统一应用图标，可通过安装包安装至 Windows。

完整源码、算法边界与测试说明见项目 README.md。
'@
$packageNotes | Set-Content -LiteralPath 'release/RetouchDesk/使用说明.txt' -Encoding utf8
if (Test-Path -LiteralPath 'sample.local.json') { Copy-Item -LiteralPath 'sample.local.json' -Destination 'release/RetouchDesk/sample.local.json' -Force }
Write-Host '已生成 release\RetouchDesk\RetouchDesk.exe'
