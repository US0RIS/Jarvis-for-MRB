from __future__ import annotations

import shlex

from jarvis_mrb.tools.pc import launch_minecraft, minecraft_status


HELP = """Commands:
  open minecraft      Launch Minecraft if it is not already running.
  status minecraft    Check whether Minecraft appears to be running.
  help                Show this help.
  quit / exit         Exit Jarvis.
"""


def handle_command(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""

    try:
        parts = [part.lower() for part in shlex.split(text)]
    except ValueError as exc:
        return f"Could not parse command: {exc}"

    if parts in (["quit"], ["exit"]):
        raise EOFError

    if parts == ["help"]:
        return HELP.rstrip()

    if parts in (["open", "minecraft"], ["launch", "minecraft"], ["start", "minecraft"]):
        return launch_minecraft().message

    if parts in (["status", "minecraft"], ["is", "minecraft", "running"]):
        return minecraft_status().message

    return "I don't have a tool for that yet. Type 'help' to see the current milestone commands."


def main() -> None:
    print("Jarvis for MRB — milestone 1")
    print("Type 'help' for commands.")

    while True:
        try:
            raw = input("jarvis> ")
            response = handle_command(raw)
            if response:
                print(response)
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return


if __name__ == "__main__":
    main()
