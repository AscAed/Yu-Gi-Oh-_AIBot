param([switch]$BuildEngine, [switch]$Offline, [switch]$FrozenRuntime, [string]$Ignis='C:/ProjectIgnis')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location $root
$env:http_proxy='http://127.0.0.1:7897'
$env:https_proxy='http://127.0.0.1:7897'
$env:all_proxy='socks5://127.0.0.1:7897'
function Check-Exit {if($LASTEXITCODE -ne 0){throw "Command failed: $LASTEXITCODE"}}
$packageReadme=[IO.File]::ReadAllText((Join-Path $root 'docs/LOCAL_PACKAGE_README.md'))
$packageReadmeLinks=@{
    '(INDEX.md)'='(../../docs/INDEX.md)'
    '(../TASKS.md)'='(../../TASKS.md)'
    '(DEPLOYMENT.md)'='(../../docs/DEPLOYMENT.md)'
    '(TESTING.md)'='(../../docs/TESTING.md)'
}
foreach($link in $packageReadmeLinks.Keys){
    if(([regex]::Matches($packageReadme,[regex]::Escape($link))).Count -ne 1){throw "Package README link missing or duplicated: $link"}
    $packageReadme=$packageReadme.Replace($link,$packageReadmeLinks[$link])
}
if($BuildEngine){& "$PSScriptRoot/build-engine.ps1" -Offline:$Offline; Check-Exit}
if(!(Test-Path data/runtime/engine/manifest.json)){throw 'Run scripts/build-engine.ps1 first'}
if($FrozenRuntime){
    foreach($asset in @('data/runtime/cards.cdb','data/runtime/scripts.json','data/runtime/script/official')){if(!(Test-Path -LiteralPath $asset)){throw "Frozen asset missing: $asset"}}
} else {py scripts/prepare-runtime.py --ignis $Ignis; Check-Exit}
if($Offline){cargo build --release --workspace --locked --offline; Check-Exit}
else {cargo build --release --workspace --locked; Check-Exit}
$commit='1051a65ab853fd84521aa919d1859f9468816c56'
if(!(Test-Path data/tmp/lflists-source/OCG.lflist.conf)){
    if($Offline){throw 'LFLists checkout missing in offline mode'}
    git clone https://github.com/ProjectIgnis/LFLists.git data/tmp/lflists-source; Check-Exit
}
git -C data/tmp/lflists-source checkout $commit; Check-Exit
if((git -C data/tmp/lflists-source rev-parse HEAD) -ne $commit){throw 'LFLists commit mismatch'}
$dest=Join-Path $root 'dist/ygo-local'
New-Item -ItemType Directory -Force "$dest/configs","$dest/fixtures","$dest/knowledge" | Out-Null
Copy-Item target/release/ygo-cli.exe "$dest/ygo.exe"
Copy-Item target/release/ygo-engine-worker.exe "$dest/ygo-engine-worker.exe"
Copy-Item configs/engine.example.toml "$dest/configs/engine.example.toml"
Copy-Item configs/scoring.toml "$dest/configs/scoring.toml"
Copy-Item tests/fixtures/rabbit.request.json "$dest/fixtures/rabbit.request.json"
Copy-Item tests/fixtures/phantom.request.json "$dest/fixtures/phantom.request.json"
Copy-Item knowledge/phantom-v1.json "$dest/knowledge/phantom-v1.json"
Copy-Item knowledge/phantom-v2.json "$dest/knowledge/phantom-v2.json"
Copy-Item tests/fixtures/break-sword.request.json "$dest/fixtures/break-sword.request.json"
Copy-Item tests/fixtures/phantom.engine-cases.json "$dest/fixtures/phantom.engine-cases.json"
Copy-Item tests/fixtures/phantom.fixed-hands.json "$dest/fixtures/phantom.fixed-hands.json"
[IO.File]::WriteAllText("$dest/README.md",$packageReadme,[Text.UTF8Encoding]::new($false))
Copy-Item docs/DEPLOYMENT.md "$dest/DEPLOYMENT.md"
Copy-Item docs/SEMANTIC_PLANNING.md "$dest/SEMANTIC_PLANNING.md"
Copy-Item docs/TESTING.md "$dest/TESTING.md"
Copy-Item docs/TESTING_HISTORY.md "$dest/TESTING_HISTORY.md"
Copy-Item docs/BREAK_SWORD_VERIFICATION.md "$dest/BREAK_SWORD_VERIFICATION.md"
Copy-Item docs/GOAL_PLANNING.md "$dest/GOAL_PLANNING.md"
Copy-Item tests/fixtures/goal-*.request.json "$dest/fixtures/"
Copy-Item tests/fixtures/ash-recovery.request.json "$dest/fixtures/"
Copy-Item tests/fixtures/ash-recovery.cases.json "$dest/fixtures/"
Copy-Item docs/RECOVERY_PLANNING.md "$dest/RECOVERY_PLANNING.md"
Copy-Item tests/fixtures/ash-strategy.request.json "$dest/fixtures/"
Copy-Item docs/ASH_STRATEGY_PLANNING.md "$dest/ASH_STRATEGY_PLANNING.md"
New-Item -ItemType Directory -Force "$dest/schemas" | Out-Null
Copy-Item schemas/*.json "$dest/schemas/"
$config=@"
worker_path = '$($dest.Replace('\','/'))/ygo-engine-worker.exe'
ocgcore_path = '$($root.Replace('\','/'))/data/runtime/engine/ocgcore.dll'
catalog_path = '$($root.Replace('\','/'))/data/runtime/cards.cdb'
scripts_path = '$($root.Replace('\','/'))/data/runtime/script'
script_manifest_path = '$($root.Replace('\','/'))/data/runtime/scripts.json'
engine_manifest_path = '$($root.Replace('\','/'))/data/runtime/engine/manifest.json'
timeout_ms = 30000
"@
[IO.File]::WriteAllText("$dest/configs/engine.toml",$config)
Copy-Item "$dest/configs/engine.toml" configs/engine.toml
$launcher=@"
@echo off
set "YGO_ENGINE_CONFIG=%~dp0configs\engine.toml"
set "YGO_SNAPSHOT_STORE=$root\data\snapshots"
set "YGO_ACTIVE_SNAPSHOT=$root\data\snapshots\active.json"
set "YGO_SCORING_CONFIG=%~dp0configs\scoring.toml"
set "YGO_SMOKE_REQUEST=%~dp0fixtures\rabbit.request.json"
set "YGO_KNOWLEDGE_CONFIG=%~dp0knowledge\phantom-v1.json"
set "YGO_KNOWLEDGE_V2_CONFIG=%~dp0knowledge\phantom-v2.json"
"%~dp0ygo.exe" %*
"@
[IO.File]::WriteAllText("$dest/ygo.cmd",$launcher,[Text.UTF8Encoding]::new($false))
& "$dest/ygo.cmd" catalog import --input "$root/data/runtime/cards.cdb"; Check-Exit
& "$dest/ygo.cmd" banlist import --input "$root/data/tmp/lflists-source/OCG.lflist.conf" --commit $commit; Check-Exit
& "$dest/ygo.cmd" engine doctor; Check-Exit
& "$dest/ygo.cmd" knowledge validate; Check-Exit
Get-FileHash "$dest/ygo.exe","$dest/ygo-engine-worker.exe" -Algorithm SHA256 | Select-Object Path,Hash | ConvertTo-Json | Set-Content "$dest/build-hashes.json"
Write-Output "Local package: $dest (external engine/data referenced by local config)"
