# Remove Circularity from Docker: the containers, the data and the images. This folder stays; delete it yourself.
param([switch]$Yes)
. "$PSScriptRoot\lib.ps1"
Test-Docker
if (-not $Yes) {
    $answer = Read-Host 'This deletes the app, its data and its images from Docker. Type yes to go on'
    if ($answer -ne 'yes') { Write-Host 'Nothing changed.'; exit 0 }
}
Invoke-Compose down -v --remove-orphans
foreach ($img in $Images) { docker image rm "${img}:$Version" *> $null }
Write-Step 'Removed. postgres:16-alpine is left in place in case other projects use it (docker image rm postgres:16-alpine).'