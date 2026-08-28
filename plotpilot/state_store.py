from __future__ import annotations

import json
from pathlib import Path


class StateStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (
            Path.home()
            / ".plotpilot"
            / "state.json"
        )
        self._data: dict = {}
        self._loaded = False

    def _load(self):
        if self._loaded:
            return

        self._loaded = True

        try:
            self._data = json.loads(
                self.path.read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            self._data = {}

        if not isinstance(self._data, dict):
            self._data = {}

    def get(self, key: str, default=None):
        self._load()
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._load()
        self._data[key] = value
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.path.write_text(
            json.dumps(
                self._data,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
