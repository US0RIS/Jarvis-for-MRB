from __future__ import annotations

from jarvis_mrb.tools.google import authenticate_google


def main() -> None:
    result = authenticate_google()
    print(result.message)
    raise SystemExit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
