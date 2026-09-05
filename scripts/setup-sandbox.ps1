$ErrorActionPreference = "Stop"

Write-Host "Preparing the optional Jarvis Docker code sandbox..."

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker CLI is not installed or not on PATH."
    Write-Host "Install/start Docker Desktop, then run this script again."
    exit 2
}

try {
    docker version --format '{{.Server.Version}}' | Out-Null
} catch {
    Write-Host "Docker Desktop is installed but its engine is not running. Start Docker Desktop and rerun."
    exit 3
}

Write-Host "Pulling the small sandbox runtime image..."
docker pull python:3.12-alpine
if ($LASTEXITCODE -ne 0) {
    throw "Could not pull python:3.12-alpine."
}

Write-Host ""
Write-Host "Jarvis sandbox is ready."
Write-Host "Generated Python runs with no network, a read-only filesystem, dropped Linux capabilities,"
Write-Host "a 256 MB memory limit, one CPU, and a hard timeout. Host shell access is not exposed to the model."
