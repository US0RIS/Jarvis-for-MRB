$ErrorActionPreference = "Stop"

Write-Host "Preparing Jarvis persistent-memory and passive-vision models..."

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    throw "Ollama is not available on PATH. Start/install Ollama before running this setup."
}

Write-Host ""
Write-Host "Pulling local embedding model: nomic-embed-text"
ollama pull nomic-embed-text
if ($LASTEXITCODE -ne 0) {
    throw "Could not pull nomic-embed-text."
}

Write-Host ""
Write-Host "Pulling lightweight vision model: moondream"
ollama pull moondream
if ($LASTEXITCODE -ne 0) {
    throw "Could not pull moondream."
}

Write-Host ""
Write-Host "Persistent AI models are ready."
Write-Host "- Episodic memory embeddings: nomic-embed-text"
Write-Host "- Passive vision: moondream"
Write-Host ""
Write-Host "Jarvis runs passive vision with zero GPU layers by default so the RTX 5080 remains available for Qwen and Kokoro."
Write-Host "If you later want to benchmark GPU vision, set JARVIS_VISION_NUM_GPU before starting Jarvis."
