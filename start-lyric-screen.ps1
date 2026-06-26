Set-StrictMode -Version Latest
$ErrorActionPreference = 'SilentlyContinue'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

try {
  $service = Get-Service -Name 'SignalRgb.Service' -ErrorAction SilentlyContinue
  if ($null -ne $service -and $service.Status -eq 'Running') {
    Stop-Service -Name 'SignalRgb.Service' -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
  }
} catch {
}

$electron = Join-Path $root 'node_modules\electron\dist\electron.exe'
if (-not (Test-Path $electron)) {
  exit 1
}

Start-Process -FilePath $electron -ArgumentList '.' -WorkingDirectory $root
