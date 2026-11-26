param([switch]$SkipAppBuild, [string]$CompilerPath)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
if (-not $SkipAppBuild) {
    & (Join-Path $PSScriptRoot 'package.ps1')
    if ($LASTEXITCODE -ne 0) { throw '应用打包失败。' }
}
if (-not (Test-Path -LiteralPath 'release\RetouchDesk\RetouchDesk.exe')) { throw '未找到便携应用，请先运行 npm run package:windows。' }
if (-not $CompilerPath) {
    $compilerCandidates = @(
        (Join-Path $taskRoot '.tools\InnoSetup\ISCC.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
    )
    $CompilerPath = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $CompilerPath) {
        $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($command) { $CompilerPath = $command.Source }
    }
}
if (-not $CompilerPath -or -not (Test-Path -LiteralPath $CompilerPath)) { throw '未找到 Inno Setup 编译器。请安装 Inno Setup 6 或指定 -CompilerPath。' }
$version = (Get-Content -LiteralPath 'package.json' -Raw | ConvertFrom-Json).version
& $CompilerPath "/DAppVersion=$version" (Join-Path $taskRoot 'installer\RetouchDesk.iss')
if ($LASTEXITCODE -ne 0) { throw 'Windows 安装包构建失败。' }
$installerPath = Join-Path $taskRoot "release\installer\RetouchDesk-$version-Setup-x64.exe"
if (-not (Test-Path -LiteralPath $installerPath)) { throw '安装包输出文件缺失。' }
$hash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText("$installerPath.sha256", "$hash  $([System.IO.Path]::GetFileName($installerPath))`n", [System.Text.UTF8Encoding]::new($false))
Write-Host "已生成安装包：$installerPath"
