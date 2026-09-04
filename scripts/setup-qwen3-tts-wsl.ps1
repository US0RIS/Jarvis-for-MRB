$ErrorActionPreference = "Stop"

Write-Host "Setting up local Qwen3-TTS for Jarvis inside WSL..."
Write-Host "Runtime model: Qwen3-TTS 0.6B CustomVoice (Ryan), BF16/CUDA"
Write-Host "This model is intentionally small enough to coexist with the 27B Ollama planner on a 16 GB RTX 5080."

$bash = @'
set -euo pipefail

ROOT="$HOME/.local/share/jarvis/qwen3-tts"
REPO="https://github.com/oseibonsu/qwen3-tts.git"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: NVIDIA GPU is not visible inside WSL. Update the NVIDIA Windows driver/WSL GPU support first." >&2
  exit 20
fi

echo "GPU visible to WSL:"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip curl libsndfile1 ffmpeg

PY=python3
"$PY" - <<'PY'
import sys
if not ((3, 10) <= sys.version_info[:2] <= (3, 12)):
    raise SystemExit(
        f"Qwen3-TTS requires Python 3.10-3.12; WSL python3 is {sys.version.split()[0]}. "
        "Install Python 3.12 in WSL and rerun using that interpreter."
    )
print("Using Python", sys.version.split()[0])
PY

mkdir -p "$(dirname "$ROOT")"
if [ -d "$ROOT/.git" ]; then
  git -C "$ROOT" pull --ff-only
else
  git clone "$REPO" "$ROOT"
fi

"$PY" -m venv "$ROOT/.venv"
. "$ROOT/.venv/bin/activate"
python -m pip install --upgrade pip setuptools wheel

# Blackwell (RTX 50-series) support requires a recent CUDA/PyTorch wheel. Install
# it before the server's Python dependencies so an older transitive torch build
# cannot win dependency resolution.
python -m pip install --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

cd "$ROOT"
python -m pip install -e ".[api]"

python - <<'PY'
import torch
print("PyTorch:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
if not torch.cuda.is_available():
    raise SystemExit("PyTorch cannot see CUDA inside WSL.")
print("CUDA device:", torch.cuda.get_device_name(0))
cap = torch.cuda.get_device_capability(0)
print("Compute capability:", cap)
PY

# Download weights now rather than making the first spoken Jarvis response pay the
# network/model-download cost. The model file is ~1.8 GB plus tokenizer assets.
python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download("Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")
print("Qwen3-TTS model cached.")
PY

# Restart any previous Jarvis TTS process installed by this setup.
pkill -f "python -m api.main" >/dev/null 2>&1 || true
nohup env \
  HOST=127.0.0.1 \
  PORT=8880 \
  TTS_BACKEND=official \
  TTS_MODEL_NAME=Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice \
  TTS_WARMUP_ON_START=true \
  TTS_MAX_CONCURRENT=1 \
  python -m api.main > "$HOME/.local/share/jarvis/qwen3-tts.log" 2>&1 &

echo "Starting/warming Qwen3-TTS..."
for i in $(seq 1 240); do
  if curl -fsS http://127.0.0.1:8880/health >/dev/null 2>&1; then
    echo "Qwen3-TTS is ready on http://127.0.0.1:8880"
    exit 0
  fi
  sleep 1
done

echo "Qwen3-TTS did not become healthy in time. Recent log:" >&2
tail -n 80 "$HOME/.local/share/jarvis/qwen3-tts.log" >&2 || true
exit 21
'@

wsl.exe bash -lc $bash
if ($LASTEXITCODE -ne 0) {
    throw "Qwen3-TTS setup failed in WSL (exit code $LASTEXITCODE)."
}

Write-Host ""
Write-Host "Qwen3-TTS setup complete."
Write-Host "Jarvis will auto-start this local service in future."
Write-Host "Restart the Jarvis backend after pulling/installing milestone 9."
