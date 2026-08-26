from __future__ import annotations

import re

from .geometry import Segment


AXIS_RE = re.compile(
    r"([XYZ])\s*(-?(?:\d+(?:\.\d*)?|\.\d+))",
    re.IGNORECASE,
)


def parse_gcode(text: str) -> list[Segment]:
    segments = []

    x = 0.0
    y = 0.0
    z = 0.0

    motion = None

    for raw in text.splitlines():
        line = raw.split(";", 1)[0].strip()

        if not line:
            continue

        upper = line.upper()

        if "G0" in upper or "G00" in upper:
            motion = "rapid"

        elif "G1" in upper or "G01" in upper:
            motion = "draw"

        if motion is None:
            continue

        old_x = x
        old_y = y
        old_z = z

        for axis, value in AXIS_RE.findall(line):
            value = float(value)

            if axis.upper() == "X":
                x = value

            elif axis.upper() == "Y":
                y = value

            elif axis.upper() == "Z":
                z = value

        if x != old_x or y != old_y:
            segments.append(
                Segment(
                    old_x,
                    old_y,
                    x,
                    y,
                    motion == "draw",
                )
            )

    return segments
