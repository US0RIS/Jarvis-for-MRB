from __future__ import annotations

import time

from jarvis_mrb.tools.browser import browser_status, launch_opera_debug


def main() -> None:
    status = browser_status()
    if status.ok:
        print(status.message)
        return

    print("Opera browser-tab control is not connected.")
    print("Jarvis will try to start Opera with Chrome DevTools Protocol enabled on port 9222.")
    result = launch_opera_debug()
    print(result.message)

    for _ in range(20):
        time.sleep(0.25)
        status = browser_status()
        if status.ok:
            print(status.message)
            print("Browser tab control is ready.")
            return

    print("Browser control is still unavailable.")
    print("If Opera was already open, fully exit Opera, then run this command again:")
    print("  py -3.14 -m jarvis_mrb.browser_setup")


if __name__ == "__main__":
    main()
