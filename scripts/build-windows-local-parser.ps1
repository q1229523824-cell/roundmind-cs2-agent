param(
    [string]$Python = "python",
    [string]$ArtifactDirectory = "release"
)

$ErrorActionPreference = "Stop"
$repository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$spec = Join-Path $repository "packaging\roundmind_local.spec"
$dist = Join-Path $repository "build\windows-dist"
$work = Join-Path $repository "build\windows-work"
$bundle = Join-Path $dist "RoundMind-Local-Parser"
$artifactRoot = Join-Path $repository $ArtifactDirectory
$archive = Join-Path $artifactRoot "RoundMind-Local-Parser-win-x64.zip"

Write-Output "[1/3] Building Windows bundle..."
& $Python -m PyInstaller --noconfirm --clean --distpath $dist --workpath $work $spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败。" }

Copy-Item -LiteralPath (Join-Path $repository "packaging\README-WINDOWS.txt") -Destination $bundle -Force

Write-Output "[2/3] Smoke-testing packaged executable..."
& (Join-Path $bundle "RoundMind-Local-Parser.exe") --help
if ($LASTEXITCODE -ne 0) { throw "打包后的程序无法启动。" }

Write-Output "[3/3] Creating release archive..."
New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
Compress-Archive -Path $bundle -DestinationPath $archive -CompressionLevel Optimal
if (-not (Test-Path -LiteralPath $archive)) { throw "Windows 发布压缩包未生成。" }

Write-Output $archive
