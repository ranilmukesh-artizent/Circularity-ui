# Reset Circularity to the starting demo data: deletes everything you changed, then starts again.
param([switch]$Yes)
. "$PSScriptRoot\lib.ps1"
Test-Docker
if (-not $Yes) {
    $answer = Read-Host 'This deletes all changes and starts from the demo data again. Type yes to go on'
    if ($answer -ne 'yes') { Write-Host 'Nothing changed.'; exit 0 }
}
Invoke-Compose down -v
Import-Images
Write-EnvFile
Wait-Ready