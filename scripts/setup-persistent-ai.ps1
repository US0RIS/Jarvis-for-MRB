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
Write-Host "- Episodic memory embeddings: nomic-embed-text (CPU by default so it cannot evict the planner)"
Write-Host "- Passive vision: moondream (Ollama automatic GPU offload)"
Write-Host ""
Write-Host "Moondream is small enough to coexist with Qwen3 8B on the target RTX 5080, so passive vision now uses normal Ollama GPU acceleration by default."
Write-Host "Set JARVIS_VISION_NUM_GPU=0 before starting Jarvis only if you explicitly want to force vision back to CPU."
