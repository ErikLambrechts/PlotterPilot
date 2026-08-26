from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


@dataclass
class Anchor:
    name: str
    x: float
    y: float


@dataclass
class Workspace:
    width: float
    height: float
    depth: float = 0.0
    anchors: list[Anchor] = field(default_factory=list)


@dataclass
class MachineConfig:
    host: str
    port: int
    workspace: Workspace
    profiles: list[Path] = field(default_factory=list)


class JobSourceType(str, Enum):
    SVG = "svg"
    GCODE = "gcode"


@dataclass
class Transform:
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0

    scale: float = 1.0
    rotation: float = 0.0

    flip_x: bool = False
    flip_y: bool = False


@dataclass
class GCodeStats:
    drawing_distance: float = 0.0
    travel_distance: float = 0.0
    drawing_moves: int = 0
    travel_moves: int = 0
    estimated_seconds: float = 0.0


@dataclass
class Job:
    name: str
    source: Path
    source_type: JobSourceType

    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    active: bool = True
    visible: bool = True

    origin: str = "machine"
    repeat_anchors: bool = False
    repeated_anchors: list[str] = field(default_factory=list)

    transform: Transform = field(default_factory=Transform)

    gcode: str | None = None

    source_svg_id: str | None = None
    generated_from_svg: bool = False

    conversion_profile: str | None = None
    conversion_parameters: dict = field(default_factory=dict)

    stats: GCodeStats | None = None

    preview_limit: int = 100000
    preview_mode: str = "auto"
