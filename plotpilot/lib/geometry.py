from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Segment:
    x1: float
    y1: float
    x2: float
    y2: float
    draw: bool = True


def transform_point(
    x: float,
    y: float,
    *,
    scale: float = 1.0,
    rotation: float = 0.0,
    flip_x: bool = False,
    flip_y: bool = False,
) -> tuple[float, float]:

    x *= scale
    y *= scale

    if flip_x:
        x = -x

    if flip_y:
        y = -y

    angle = math.radians(rotation)

    rx = x * math.cos(angle) - y * math.sin(angle)
    ry = x * math.sin(angle) + y * math.cos(angle)

    return rx, ry


def transform_segments(
    segments: list[Segment],
    *,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    scale: float = 1.0,
    rotation: float = 0.0,
    flip_x: bool = False,
    flip_y: bool = False,
) -> list[Segment]:

    result = []

    for segment in segments:
        x1, y1 = transform_point(
            segment.x1,
            segment.y1,
            scale=scale,
            rotation=rotation,
            flip_x=flip_x,
            flip_y=flip_y,
        )

        x2, y2 = transform_point(
            segment.x2,
            segment.y2,
            scale=scale,
            rotation=rotation,
            flip_x=flip_x,
            flip_y=flip_y,
        )

        result.append(
            Segment(
                x1 + offset_x,
                y1 + offset_y,
                x2 + offset_x,
                y2 + offset_y,
                segment.draw,
            )
        )

    return result
