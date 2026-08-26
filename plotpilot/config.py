from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import Anchor, Workspace
from .profile_manager import (
    ConversionProfile,
    discover_profiles,
)


@dataclass
class MachineConfig:
    host: str
    port: int
    workspace: Workspace
    profiles: list[ConversionProfile] = field(
        default_factory=list
    )


def _as_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _load_anchors(workspace_data: dict) -> list[Anchor]:
    anchors: list[Anchor] = []

    raw = workspace_data.get(
        "anchors",
        [],
    )

    if isinstance(raw, dict):

        for name, value in raw.items():

            if not isinstance(value, dict):
                continue

            anchors.append(
                Anchor(
                    name=str(
                        value.get(
                            "name",
                            name,
                        )
                    ),
                    x=_as_float(
                        value.get("x", 0)
                    ),
                    y=_as_float(
                        value.get("y", 0)
                    ),
                )
            )

    elif isinstance(raw, list):

        for value in raw:

            if not isinstance(value, dict):
                continue

            name = value.get("name")

            if name is None:
                continue

            anchors.append(
                Anchor(
                    name=str(name),
                    x=_as_float(
                        value.get("x", 0)
                    ),
                    y=_as_float(
                        value.get("y", 0)
                    ),
                )
            )

    return anchors


def _profile_directory(
    config_path: Path,
    machine: dict,
) -> Path:

    configured = machine.get(
        "conversion_profiles",
        "conversion_profiles",
    )

    configured = Path(str(configured))

    if configured.is_absolute():
        return configured

    # default.json lives in:
    #
    #   plotpilot/config/default.json
    #
    # and the profiles live in:
    #
    #   plotpilot/conversion_profiles/
    #
    # Therefore a configured value of "conversion_profiles"
    # is relative to the plotpilot directory, not config/.

    plotpilot_dir = config_path.parent.parent

    return (
        plotpilot_dir / configured
    ).resolve()


def load_config(path: Path) -> MachineConfig:

    path = Path(path).resolve()

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(
            f"Configuration root must be an object: {path}"
        )

    machine = data.get("machine")

    if not isinstance(machine, dict):
        raise ValueError(
            "Configuration is missing 'machine' "
            "or 'machine' is not an object."
        )

    workspace_data = machine.get(
        "workspace",
        {},
    )

    if not isinstance(workspace_data, dict):
        raise ValueError(
            "'machine.workspace' must be an object."
        )

    anchors = _load_anchors(
        workspace_data
    )

    host = str(
        machine.get(
            "host",
            "192.168.4.1",
        )
    )

    port = _as_int(
        machine.get("port", 80),
        80,
    )

    workspace = Workspace(
        width=_as_float(
            workspace_data.get(
                "width",
                300,
            ),
            300,
        ),
        height=_as_float(
            workspace_data.get(
                "height",
                300,
            ),
            300,
        ),
        depth=_as_float(
            workspace_data.get(
                "depth",
                0,
            ),
            0,
        ),
        anchors=anchors,
    )

    profile_dir = _profile_directory(
        path,
        machine,
    )

    profiles = discover_profiles(
        profile_dir
    )

    return MachineConfig(
        host=host,
        port=port,
        workspace=workspace,
        profiles=profiles,
    )
