$ErrorActionPreference = "Stop"

function Find-Tailscale {
    $command = Get-Command tailscale.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $common = @(
        "$env:ProgramFiles\Tailscale\tailscale.exe",
        "${env:ProgramFiles(x86)}\Tailscale\tailscale.exe"
    )
    foreach ($path in $common) {
        if ($path -and (Test-Path $path)) { return $path }
    }
    return $null
}

$tailscale = Find-Tailscale
if (-not $tailscale) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "Tailscale is not installed and winget is unavailable. Install Tailscale for Windows, sign in, then rerun this script."
    }

    Write-Host "Installing Tailscale for Windows..."
    winget install --id Tailscale.Tailscale --exact --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Tailscale installation failed."
    }
    $tailscale = Find-Tailscale
    if (-not $tailscale) {
        throw "Tailscale was installed but tailscale.exe could not be located. Open a new PowerShell window and rerun this script."
    }
}

Write-Host "Tailscale CLI: $tailscale"

$status = $null
try {
    $status = (& $tailscale status --json 2>$null | ConvertFrom-Json)
} catch {
    $status = $null
}

if (-not $status -or $status.BackendState -ne "Running") {
    Write-Host "Tailscale is not connected. Starting sign-in..."
    & $tailscale up
    if ($LASTEXITCODE -ne 0) {
        throw "Tailscale did not connect. Complete the sign-in flow, then rerun this script."
    }
}

Write-Host ""
Write-Host "Publishing Jarvis to your tailnet with Tailscale Serve (private HTTPS only)..."
# Serve is tailnet-only; this is deliberately NOT Tailscale Funnel and does not
# make Jarvis public. --bg persists across terminal closure and Tailscale restarts.
& $tailscale serve --bg --yes 8765
if ($LASTEXITCODE -ne 0) {
    throw "Tailscale Serve could not proxy Jarvis. Ensure HTTPS certificates/MagicDNS are enabled for the tailnet, then rerun."
}

$status = (& $tailscale status --json | ConvertFrom-Json)
$dnsName = [string]$status.Self.DNSName
$dnsName = $dnsName.Trim().TrimEnd('.')
$ip = (& $tailscale ip -4 | Select-Object -First 1).Trim()

Write-Host ""
Write-Host "Jarvis remote access is configured."
if ($dnsName) {
    Write-Host "Use this in the iPhone Jarvis Settings -> Tailscale URL:"
    Write-Host "  https://$dnsName"
} else {
    Write-Host "Tailscale did not report a MagicDNS hostname. Tailscale IPv4 is: $ip"
    Write-Host "Enable MagicDNS/HTTPS certificates in the Tailscale admin console and rerun this script."
}
Write-Host ""
Write-Host "The iPhone must also have Tailscale installed and be signed into the same tailnet."
Write-Host "Do not configure Tailscale Funnel and do not forward TCP 8765 on your router."
