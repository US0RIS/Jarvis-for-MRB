$ErrorActionPreference = "Stop"

Write-Host "Setting up low-latency Kokoro TTS for Jarvis inside WSL..."
Write-Host "Runtime model: Kokoro-82M on CUDA, voice bm_george"
Write-Host "This replaces Qwen3-TTS as the default because conversational latency matters more than maximum TTS model size."

$bash = @'
set -euo pipefail

ROOT="$HOME/.local/share/jarvis/kokoro-fastapi"
REPO="https://github.com/remsky/Kokoro-FastAPI.git"
LOG="$HOME/.local/share/jarvis/kokoro-fastapi.log"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: NVIDIA GPU is not visible inside WSL." >&2
  exit 20
fi

echo "GPU visible to WSL:"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

sudo apt-get update
sudo apt-get install -y git curl ca-certificates ffmpeg libsndfile1 espeak-ng

UV="$HOME/.local/bin/uv"
if [ ! -x "$UV" ]; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
if [ ! -x "$UV" ]; then
  echo "ERROR: uv installation did not create $UV" >&2
  exit 22
fi

"$UV" python install 3.12
mkdir -p "$(dirname "$ROOT")"
if [ -d "$ROOT/.git" ]; then
  git -C "$ROOT" pull --ff-only
else
  git clone "$REPO" "$ROOT"
fi

rm -rf "$ROOT/.venv"
"$UV" venv --python 3.12 --seed "$ROOT/.venv"
cd "$ROOT"
. "$ROOT/.venv/bin/activate"

# Kokoro-FastAPI has a dedicated cu128 extra for Blackwell / RTX 50-series.
# Use uv so its PyTorch index configuration is honored exactly.
"$UV" pip install --python "$ROOT/.venv/bin/python" -e ".[gpu-cu128]"

python - <<'PY'
import torch
print("PyTorch:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
if not torch.cuda.is_available():
    raise SystemExit("PyTorch cannot see CUDA inside WSL.")
print("CUDA device:", torch.cuda.get_device_name(0))
print("Compute capability:", torch.cuda.get_device_capability(0))
PY

# Download model/voice assets before the first spoken response.
python docker/scripts/download_model.py --output api/src/models/v1_0

# Stop the old Qwen3-TTS service and any previous Kokoro service on Jarvis's
# private TTS port. Do not touch the main Jarvis service on 8765.
pkill -f "qwen3-tts.*api.main" >/dev/null 2>&1 || true
pkill -f "uvicorn api.src.main:app.*8880" >/dev/null 2>&1 || true
sleep 1

nohup env \
  USE_GPU=true \
  PYTHONPATH="$ROOT:$ROOT/api" \
  MODEL_DIR=src/models \
  VOICES_DIR=src/voices/v1_0 \
  WEB_PLAYER_PATH="$ROOT/web" \
  "$ROOT/.venv/bin/python" -m uvicorn api.src.main:app --host 127.0.0.1 --port 8880 \
  > "$LOG" 2>&1 &

echo "Starting Kokoro..."
for i in $(seq 1 120); do
  if curl -fsS http://127.0.0.1:8880/health >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -fsS http://127.0.0.1:8880/health >/dev/null 2>&1; then
  echo "Kokoro did not start. Recent log:" >&2
  tail -n 120 "$LOG" >&2 || true
  exit 21
fi

# Warm the exact Jarvis voice so the first live interaction does not pay model
# initialization / voice loading costs.
echo "Warming Jarvis voice..."
curl -fsS \
  -H 'Content-Type: application/json' \
  -d '{"model":"kokoro","voice":"bm_george","input":"Ready, sir.","response_format":"wav","speed":1.04}' \
  http://127.0.0.1:8880/v1/audio/speech \
  -o /tmp/jarvis-kokoro-warm.wav

if [ ! -s /tmp/jarvis-kokoro-warm.wav ]; then
  echo "Kokoro warm-up returned no audio. Recent log:" >&2
  tail -n 120 "$LOG" >&2 || true
  exit 23
fi

echo "Kokoro is ready on http://127.0.0.1:8880"
echo "Voice: bm_george"
'@

$bash = $bash.Replace("`r`n", "`n").Replace("`r", "`n")
$bashBytes = [System.Text.Encoding]::UTF8.GetBytes($bash)
$bashBase64 = [System.Convert]::ToBase64String($bashBytes)
$runner = "printf '%s' '$bashBase64' | base64 -d > /tmp/jarvis-kokoro-setup.sh && bash -n /tmp/jarvis-kokoro-setup.sh && bash /tmp/jarvis-kokoro-setup.sh"

wsl.exe bash -lc $runner
if ($LASTEXITCODE -ne 0) {
    throw "Kokoro setup failed in WSL (exit code $LASTEXITCODE)."
}

Write-Host ""
Write-Host "Kokoro setup complete."
Write-Host "Jarvis now uses the fast 82M local voice model by default."
Write-Host "Restart the Jarvis backend so it picks up the new TTS client configuration."
