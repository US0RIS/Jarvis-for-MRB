"""``jarvis-horus``: inspect which code implements each future.md idea."""
from __future__ import annotations

import argparse
import json
import sys

from jarvis_mrb.horus import registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis-horus", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("summary", help="count mapped ideas by kind")
    lk = sub.add_parser("lookup", help="find ideas whose title contains TEXT")
    lk.add_argument("text")
    ls = sub.add_parser("list", help="list mapped ideas")
    ls.add_argument("--kind", choices=["implemented", "harness", "catalog", "naming"])
    sub.add_parser("check", help="verify every reference resolves")
    args = parser.parse_args(argv)

    if args.cmd == "summary":
        print(json.dumps(registry.summary(), indent=2))
    elif args.cmd == "lookup":
        print(json.dumps(registry.lookup(args.text), indent=2, ensure_ascii=False))
    elif args.cmd == "list":
        for title, (kind, refs) in {**registry.IDEAS, **registry.PROSE_IDEAS}.items():
            if args.kind is None or kind == args.kind:
                print(f"[{kind}] {title} -> {', '.join(refs)}")
    elif args.cmd == "check":
        bad = []
        for title, (_, refs) in {**registry.IDEAS, **registry.PROSE_IDEAS}.items():
            for ref in refs:
                try:
                    registry.resolve(ref)
                except Exception as exc:  # noqa: BLE001
                    bad.append(f"{title}: {ref}: {exc}")
        print("\n".join(bad) if bad else "all references resolve")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
