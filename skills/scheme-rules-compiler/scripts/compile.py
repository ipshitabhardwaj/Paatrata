"""Skill entry point: thin wrapper over the paatrata_core CLI.

    python compile.py SOURCE [--backend gemini] [--out rules.json]
    python compile.py --check rules.json --profile '{...}'
    python compile.py --tests rules.json [--reference gold.json]
"""
import sys

from paatrata_core.cli import main

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--check":
        args = ["check", args[1], *args[2:]]
    elif args and args[0] == "--tests":
        args = ["tests", args[1], *args[2:]]
    else:
        args = ["compile", *[("-o" if a == "--out" else a) for a in args]]
    raise SystemExit(main(args))
