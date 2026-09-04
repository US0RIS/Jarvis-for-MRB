from __future__ import annotations

import getpass
import json
import os
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
CONFIG_PATH = APP_DIR / "serper.json"


def main() -> None:
    print("Configure Serper web search for Jarvis.")
    print("The key is stored locally under your user AppData and is never committed to GitHub.")
    key = getpass.getpass("Serper API key: ").strip()
    if not key:
        raise SystemExit("No API key entered; nothing changed.")

    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps({"api_key": key}, indent=2), encoding="utf-8")
    print(f"Saved Serper configuration to: {CONFIG_PATH}")
    print("Restart the Jarvis service before using web search.")


if __name__ == "__main__":
    main()
