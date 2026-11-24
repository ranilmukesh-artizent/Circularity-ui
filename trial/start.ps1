# Start Circularity (Windows). The first start loads the images and writes .env. Double-click start.cmd to run it.
. "$PSScriptRoot\lib.ps1"
Test-Docker
Import-Images
Write-EnvFile
Wait-Ready