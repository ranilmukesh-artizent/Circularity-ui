# Stop Circularity. Your data is kept; start brings it back as you left it.
. "$PSScriptRoot\lib.ps1"
Test-Docker
Invoke-Compose down
Write-Step 'Stopped. Your data is kept.'