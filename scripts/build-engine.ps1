param([switch]$Offline)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$core = '38d04c9feb1a26617407091380634c87262fe3f8'
$lua = '6e22fedb74cf0c9b6656e9fce8b7331db847c605'
$env:http_proxy = 'http://127.0.0.1:7897'
$env:https_proxy = 'http://127.0.0.1:7897'
$env:all_proxy = 'socks5://127.0.0.1:7897'
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed: $LASTEXITCODE" } }
if (!$Offline) {
    if (!(Test-Path data/tmp/ocgcore-source/ocgapi.h)) { git clone https://github.com/edo9300/ygopro-core.git data/tmp/ocgcore-source; Check-Exit }
    git -C data/tmp/ocgcore-source checkout $core; Check-Exit
    if (!(Test-Path data/tmp/ocgcore-source/lua/src/lua.h)) { git clone https://github.com/lua/lua.git data/tmp/ocgcore-source/lua/src; Check-Exit }
    git -C data/tmp/ocgcore-source/lua/src checkout $lua; Check-Exit
    py -m pip install --disable-pip-version-check --target data/tmp/build-python meson==1.12.1 ninja==1.13.2; Check-Exit
}
if ((git -C data/tmp/ocgcore-source rev-parse HEAD) -ne $core) { throw 'Core commit mismatch' }
if ((git -C data/tmp/ocgcore-source/lua/src rev-parse HEAD) -ne $lua) { throw 'Lua commit mismatch' }
$vswhere = "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe"
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$vs) { throw 'Visual Studio C++ x64 tools missing' }
# Import the x64 compiler environment in this same process.
$vcvars = Join-Path $vs 'VC/Auxiliary/Build/vcvars64.bat'
cmd /c "`"$vcvars`" >nul && set" | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') }
}
$env:PYTHONPATH = Join-Path $root 'data/tmp/build-python'
$env:PATH = (Join-Path $root 'data/tmp/build-python/bin') + ';' + $env:PATH
py scripts/build_sources.py; Check-Exit
py scripts/prepare-build.py; Check-Exit
py scripts/build_sources.py; Check-Exit
if (!(Test-Path data/tmp/ocgcore-build/build.ninja)) {
    py -m mesonbuild.mesonmain setup data/tmp/ocgcore-build data/tmp/ocgcore-source --buildtype=release -Ddefault_library=shared -Db_vscrt=mt; Check-Exit
}
else { py -m mesonbuild.mesonmain setup --reconfigure data/tmp/ocgcore-build data/tmp/ocgcore-source; Check-Exit }
py -m mesonbuild.mesonmain compile -C data/tmp/ocgcore-build; Check-Exit
New-Item -ItemType Directory -Force data/runtime/engine | Out-Null
Copy-Item -LiteralPath data/tmp/ocgcore-build/ocgcore.dll -Destination data/runtime/engine/ocgcore.dll
cl /nologo /EHsc /std:c++17 /I data/tmp/ocgcore-source scripts/abi-probe.cpp /Fe:data/tmp/abi-probe.exe /Fo:data/tmp/abi-probe.obj; Check-Exit
& ./data/tmp/abi-probe.exe ./data/runtime/engine/ocgcore.dll; Check-Exit
$manifest = [ordered]@{
    core_commit=$core; lua_commit=$lua; architecture='x64'; api='11.0'
    abi_probe_passed=$true; sha256=(Get-FileHash data/runtime/engine/ocgcore.dll -Algorithm SHA256).Hash.ToLower()
    meson=(& py -m mesonbuild.mesonmain --version); ninja=(& ninja --version)
    visual_studio=$vs; build='Meson Release shared b_vscrt=mt'; build_adapter='windows-python-concat-v1'
}
$source=Get-Content data/tmp/source-provenance.json -Raw | ConvertFrom-Json
foreach($property in $source.PSObject.Properties){$manifest[$property.Name]=$property.Value}
$manifest | ConvertTo-Json | Set-Content -Encoding utf8 data/runtime/engine/manifest.json
