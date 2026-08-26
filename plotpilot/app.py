#!/usr/bin/env python3

from pathlib import Path

from .config import load_config
from .ui import run


def main():
    root = Path(__file__).resolve().parent.parent
    config = load_config(
        root / "config" / "default.json"
    )
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
