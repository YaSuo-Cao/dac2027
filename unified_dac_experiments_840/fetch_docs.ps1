param([string]$Uri,[string]$Destination)
$ErrorActionPreference='Stop'
Invoke-WebRequest -Uri $Uri -OutFile $Destination -TimeoutSec 120
