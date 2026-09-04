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
if not ((3, 10) <= sys.version_info[:2] <= (3, 13)):
    raise SystemExit(
        f"Jarvis Qwen3-TTS setup expects Python 3.10-3.13; WSL python3 is {sys.version.split()[0]}. "
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
print("Compute capability:", torch.cuda.get_device_capability(0))
PY

# Download weights now rather than making the first spoken Jarvis response pay the
# network/model-download cost.
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
  if curl -fsS http://127.0.0.1:8880/health 2>/dev/null | python -c '
import json, sys
try:
    payload = json.load(sys.stdin)
    ready = bool((payload.get("backend") or {}).get("ready"))
except Exception:
    ready = False
raise SystemExit(0 if ready else 1)
' >/dev/null 2>&1; then
    echo "Qwen3-TTS model is loaded and ready on http://127.0.0.1:8880"
    exit 0
  fi
  sleep 1
done

echo "Qwen3-TTS did not become ready in time. Recent log:" >&2
tail -n 100 "$HOME/.local/share/jarvis/qwen3-tts.log" >&2 || true
exit 21
'@

# Do not pass the multiline Bash program directly as the `bash -lc` argument.
# Windows PowerShell/native-command quoting can flatten or reinterpret multiline
# here-documents on the way through wsl.exe, which makes Python heredoc bodies get
# parsed as Bash (the failure looked like: syntax error near unexpected token `(`).
# Base64 gives WSL one simple single-line command, then Bash parses the original
# script bytes exactly as authored. `bash -n` catches any real shell syntax error
# before the installer changes the machine.
$bashBytes = [System.Text.Encoding]::UTF8.GetBytes($bash)
$bashBase64 = [System.Convert]::ToBase64String($bashBytes)
$runner = "printf '%s' '$bashBase64' | base64 -d > /tmp/jarvis-qwen3-tts-setup.sh && bash -n /tmp/jarvis-qwen3-tts-setup.sh && bash /tmp/jarvis-qwen3-tts-setup.sh"

wsl.exe bash -lc $runner
if ($LASTEXITCODE -ne 0) {
    throw "Qwen3-TTS setup failed in WSL (exit code $LASTEXITCODE)."
}

Write-Host ""
Write-Host "Qwen3-TTS setup complete."
Write-Host "Jarvis will auto-start this local service in future."
Write-Host "Restart the Jarvis backend after pulling/installing milestone 9."
