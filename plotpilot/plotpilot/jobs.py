from __future__ import annotations

import math
import re
from pathlib import Path

from .models import (
    GCodeStats,
    Job,
    JobSourceType,
)


_MOVE_RE = re.compile(
    r"([XYZF])\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def parse_gcode(text: str) -> GCodeStats:
    stats = GCodeStats()

    x = y = z = 0.0
    feed = 0.0

    for raw in text.splitlines():
        line = raw.split(";", 1)[0].strip()

        if not line:
            continue

        command = line.upper()

        if not (
            command.startswith("G0")
            or command.startswith("G1")
            or command.startswith("G00")
            or command.startswith("G01")
        ):
            continue

        values = {}

        for axis, value in _MOVE_RE.findall(command):
            try:
                values[axis.upper()] = float(value)
            except ValueError:
                pass

        nx = values.get("X", x)
        ny = values.get("Y", y)
        nz = values.get("Z", z)

        dx = nx - x
        dy = ny - y
        dz = nz - z

        distance = math.sqrt(
            dx * dx + dy * dy + dz * dz
        )

        if "F" in values:
            feed = values["F"]

        rapid = command.startswith("G0")

        if rapid:
            stats.travel_distance += distance
            stats.travel_moves += 1
        else:
            stats.drawing_distance += distance
            stats.drawing_moves += 1

        if feed > 0:
            stats.estimated_seconds += (
                distance / feed * 60.0
            )

        x, y, z = nx, ny, nz

    return stats


class JobManager:
    def __init__(self):
        self.jobs: list[Job] = []

    def add_file(self, path: Path) -> Job:
        suffix = path.suffix.lower()

        if suffix == ".svg":
            source_type = JobSourceType.SVG
        elif suffix in {".gcode", ".nc", ".ngc"}:
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
            job.stats = parse_gcode(job.gcode)

        self.jobs.append(job)
        return job

    def create_gcode_job(
        self,
        source_svg: Job,
        output: Path,
        profile: str,
        parameters: dict,
    ) -> Job:
        gcode = output.read_text(
            encoding="utf-8"
        )

        job = Job(
            name=output.name,
            source=output,
            source_type=JobSourceType.GCODE,
            origin=source_svg.origin,
            repeat_anchors=source_svg.repeat_anchors,
            repeated_anchors=list(
                source_svg.repeated_anchors
            ),
            transform=source_svg.transform,
            gcode=gcode,
            source_svg_id=source_svg.id,
            generated_from_svg=True,
            conversion_profile=profile,
            conversion_parameters=dict(parameters),
        )

        job.stats = parse_gcode(gcode)

        source_svg.active = False
        source_svg.visible = False

        self.jobs.append(job)

        return job

    def get(self, job_id):
        return next(
            (j for j in self.jobs if j.id == job_id),
            None,
        )

    def remove(self, job_id):
        self.jobs = [
            j for j in self.jobs
            if j.id != job_id
        ]
