# Shared model compatibility imports.
import math
import re
import uuid
from pathlib import Path
from dataclasses import dataclass, field


"""
PlotPilot module extracted from plotpilot.py.

This module is intentionally conservative.
The first refactor keeps the existing implementation intact.
"""

from enum import Enum


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
    anchors: list[Anchor] = field(
        default_factory=list
    )

    # Preview settings shared by the workspace view
    # and Job Properties.
    preview_limit: int = 20000
    show_drawing: bool = True
    show_travel: bool = True


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

    flip_x_keep_bbox: bool = False
    flip_y_keep_bbox: bool = False


@dataclass
class Job:
    name: str
    source: Path
    source_type: JobSourceType

    id: str = field(
        default_factory=lambda: str(
            uuid.uuid4()
        )
    )

    active: bool = True
    visible: bool = True

    origin: str = "machine"
    repeat_anchors: bool = False

    transform: Transform = field(
        default_factory=Transform
    )

    repeated_anchors: list[str] = field(
        default_factory=list
    )

    gcode: str | None = None

    source_svg_id: str | None = None
    generated_from_svg: bool = False

    conversion_profile: str | None = None
    conversion_parameters: dict = field(
        default_factory=dict
    )

    preview_limit: int = 15000

    stats: "GCodeStats | None" = None


@dataclass
class GCodeStats:
    drawing_distance: float = 0.0
    travel_distance: float = 0.0
    drawing_moves: int = 0
    travel_moves: int = 0
    estimated_seconds: float = 0.0


class JobManager:

    def __init__(self):
        self.jobs: list[Job] = []

    def add_file(self, path: Path) -> Job:
        suffix = path.suffix.lower()

        if suffix == ".svg":
            source_type = JobSourceType.SVG

        elif suffix in (
            ".gcode",
            ".nc",
            ".ngc",
        ):
            source_type = JobSourceType.GCODE

        else:
            raise ValueError(
                f"Unsupported file type: {suffix}"
            )

        job = Job(
            name=path.name,
            source=path,
            source_type=source_type,
        )

        if source_type == JobSourceType.GCODE:
            job.gcode = path.read_text(
                encoding="utf-8"
            )
            job.stats = analyze_gcode(
                job.gcode
            )

        self.jobs.append(job)

        return job

    def create_generated_gcode(
        self,
        source_svg: Job,
        gcode: str,
        profile: str,
        parameters: dict,
    ) -> Job:

        job = Job(
            name=(
                Path(
                    source_svg.name
                ).stem
                + ".gcode"
            ),
            source=Path(
                source_svg.name
            ).with_suffix(".gcode"),
            source_type=JobSourceType.GCODE,
        )

        job.gcode = gcode
        job.source_svg_id = source_svg.id
        job.generated_from_svg = True
        job.conversion_profile = profile
        job.conversion_parameters = dict(
            parameters
        )

        job.transform = Transform(
            offset_x=source_svg.transform.offset_x,
            offset_y=source_svg.transform.offset_y,
            offset_z=source_svg.transform.offset_z,
            scale=source_svg.transform.scale,
            rotation=source_svg.transform.rotation,
            flip_x=source_svg.transform.flip_x,
            flip_y=source_svg.transform.flip_y,
        )

        job.origin = source_svg.origin
        job.repeated_anchors = list(
            source_svg.repeated_anchors
        )

        job.stats = analyze_gcode(
            gcode
        )

        source_svg.active = False
        source_svg.visible = False

        self.jobs.append(job)

        return job

    def get(self, job_id):
        return next(
            (
                j
                for j in self.jobs
                if j.id == job_id
            ),
            None,
        )

    def remove(self, job_id):
        self.jobs = [
            j
            for j in self.jobs
            if j.id != job_id
        ]



class MachineState:

    def __init__(self):

        self.connected = False
        self.state = "Disconnected"

        self.x = 0.0
        self.y = 0.0
        self.z = 0.0

        self.feed = 0.0
        self.spindle = 0.0

        self.message = ""
