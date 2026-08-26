from __future__ import annotations

import json
from pathlib import Path

from .models import Anchor, MachineConfig, Workspace


def load_config(path: Path) -> MachineConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    machine = data["machine"]
    workspace = machine["workspace"]

    anchors = [
        Anchor(
            name=str(a["name"]),
            x=float(a["x"]),
            y=float(a["y"]),
        )
        for a in workspace.get("anchors", [])
    ]

    profiles = [
        (path.parent.parent / p).resolve()
        for p in machine.get("profiles", [])
    ]

    return MachineConfig(
        host=str(machine.get("host", "")),
        port=int(machine.get("port", 80)),
        workspace=Workspace(
            width=float(workspace["width"]),
            height=float(workspace["height"]),
            depth=float(workspace.get("depth", 0)),
            anchors=anchors,
        ),
        profiles=profiles,
    )
