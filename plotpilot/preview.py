from __future__ import annotations

import math
import re
from dataclasses import dataclass


@dataclass
class Segment:
    x1: float
    y1: float
    x2: float
    y2: float
    drawing: bool


_RE = re.compile(
    r"([XYZ])\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def gcode_segments(
    text: str,
    limit: int = 100000,
):
    segments = []

    x = y = z = 0.0

    lines = text.splitlines()

    if len(lines) > limit:
        step = max(
            1,
            math.ceil(len(lines) / limit),
        )
        lines = lines[::step]

    for raw in lines:
        line = raw.split(";", 1)[0].strip()
        upper = line.upper()

        if not (
            upper.startswith("G0")
            or upper.startswith("G1")
            or upper.startswith("G00")
            or upper.startswith("G01")
        ):
            continue

        values = {}

        for axis, value in _RE.findall(upper):
            try:
                values[axis] = float(value)
            except ValueError:
                pass

        nx = values.get("X", x)
        ny = values.get("Y", y)
        nz = values.get("Z", z)

        if nx != x or ny != y:
            segments.append(
                Segment(
                    x,
                    y,
                    nx,
                    ny,
                    not upper.startswith("G0"),
                )
            )

        x, y, z = nx, ny, nz

    return segments
