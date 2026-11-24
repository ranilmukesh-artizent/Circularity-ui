# Show whether each part of Circularity is running and healthy.
. "$PSScriptRoot\lib.ps1"
Test-Docker
Invoke-Compose ps
if (Test-Path "$Here\.env") { Write-Host "App address: http://localhost:$(Get-Port)" }