param([switch]$Browser)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$pythonPath = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw '未找到项目 Python 环境。请运行已打包的 RetouchDesk.exe，或按 README 创建 .venv 并安装 requirements.txt。'
}
if (-not (Test-Path -LiteralPath (Join-Path $taskRoot 'dist\index.html'))) {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw '前端构建失败。' }
}
Write-Host '正在启动 Retouch Desk，本地 CPU 处理，无需显卡。'
$launchArgs = @('backend/server.py')
if ($Browser) { $launchArgs += '--browser' }
& $pythonPath @launchArgs
if ($LASTEXITCODE -ne 0) { throw "应用退出，错误码：$LASTEXITCODE" }
