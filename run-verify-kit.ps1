param([string]$KitRoot = 'C:\kit-app-template\_build\windows-x86_64\release\kit')
$ErrorActionPreference = 'Stop'
$output = Join-Path $PSScriptRoot 'verification'
New-Item -ItemType Directory -Path $output -Force | Out-Null
$cache = Join-Path (Split-Path $KitRoot -Parent) 'extscache'
& (Join-Path $KitRoot 'kit.exe') (Join-Path $PSScriptRoot 'tests\project_view_test.kit') `
    --no-window --ext-folder $cache --ext-folder (Split-Path $PSScriptRoot -Parent) `
    --exec (Join-Path $PSScriptRoot 'tests\verify_kit.py') `
    "--/log/file=$output/kit.log" "--/app/userConfigPath=$output/user.config.json" `
    "--/app/cachePath=$output/cache" "--/app/dataPath=$output/data"
exit $LASTEXITCODE
