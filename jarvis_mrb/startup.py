from __future__ import annotations

import os
import subprocess
import sys


TASK_NAME = "JarvisForMRB"


def main() -> None:
    if sys.platform != "win32":
        print("Startup installation is currently implemented for Windows only.")
        return

    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable

    command = f'"{pythonw}" -m jarvis_mrb.service'
    result = subprocess.run(
        [
            "schtasks",
            "/Create",
            "/TN",
            TASK_NAME,
            "/TR",
            command,
            "/SC",
            "ONLOGON",
            "/F",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print("Jarvis will now start automatically when you log into Windows.")
        print("Starting the service now...")
        subprocess.Popen(
            [pythonw, "-m", "jarvis_mrb.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
    else:
        print("Could not create the startup task.")
        print(result.stderr.strip() or result.stdout.strip())
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
