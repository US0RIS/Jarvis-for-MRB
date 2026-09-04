$ErrorActionPreference = "Stop"

$bash = @'
set -euo pipefail
ROOT="$HOME/.local/share/jarvis/qwen3-tts"
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "Qwen3-TTS is not installed. Run scripts/setup-qwen3-tts-wsl.ps1 first." >&2
  exit 2
fi
cd "$ROOT"
. .venv/bin/activate
exec env \
  HOST=127.0.0.1 \
  PORT=8880 \
  TTS_BACKEND=official \
  TTS_MODEL_NAME=Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice \
  TTS_WARMUP_ON_START=true \
  TTS_MAX_CONCURRENT=1 \
  python -m api.main
'@

wsl.exe bash -lc $bash
if ($LASTEXITCODE -ne 0) {
    throw "Qwen3-TTS exited with code $LASTEXITCODE."
}
