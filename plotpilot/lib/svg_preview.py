from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .geometry import Segment


NUMBER = r"-?(?:\d+(?:\.\d*)?|\.\d+)"
PAIR_RE = re.compile(
    rf"({NUMBER})[,\s]+({NUMBER})"
)


def _points_from_polyline(value: str):
    return [
        (float(a), float(b))
        for a, b in PAIR_RE.findall(value)
    ]


def parse_svg(path) -> list[Segment]:
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return []

    segments = []

    def tag(element):
        return element.tag.split("}")[-1].lower()

    for element in root.iter():
        kind = tag(element)

        if kind == "line":
            try:
                x1 = float(element.attrib.get("x1", 0))
                y1 = float(element.attrib.get("y1", 0))
                x2 = float(element.attrib.get("x2", 0))
                y2 = float(element.attrib.get("y2", 0))
                segments.append(
                    Segment(x1, y1, x2, y2, True)
                )
            except ValueError:
                pass

        elif kind in {"polyline", "polygon"}:
            points = _points_from_polyline(
                element.attrib.get("points", "")
            )

            if kind == "polygon" and len(points) > 2:
                points.append(points[0])

            for a, b in zip(points, points[1:]):
                segments.append(
                    Segment(a[0], a[1], b[0], b[1], True)
                )

        elif kind == "rect":
            try:
                x = float(element.attrib.get("x", 0))
                y = float(element.attrib.get("y", 0))
                w = float(element.attrib.get("width", 0))
                h = float(element.attrib.get("height", 0))

                points = [
                    (x, y),
                    (x + w, y),
                    (x + w, y + h),
                    (x, y + h),
                    (x, y),
                ]

                for a, b in zip(points, points[1:]):
                    segments.append(
                        Segment(a[0], a[1], b[0], b[1], True)
                    )
            except ValueError:
                pass

        elif kind == "path":
            d = element.attrib.get("d", "")
            commands = re.findall(
                rf"[MLHVZmlhvz]|{NUMBER}",
                d,
            )

            if not commands:
                continue

            current = (0.0, 0.0)
            start = current
            i = 0
            command = None

            while i < len(commands):
                token = commands[i]

                if re.fullmatch(r"[MLHVZmlhvz]", token):
                    command = token
                    i += 1

                    if command.lower() == "z":
                        segments.append(
                            Segment(
                                current[0],
                                current[1],
                                start[0],
                                start[1],
                                True,
                            )
                        )
                        current = start

                    continue

                if command is None:
                    i += 1
                    continue

                try:
                    if command in ("M", "m", "L", "l"):
                        if i + 1 >= len(commands):
                            break

                        nx = float(commands[i])
                        ny = float(commands[i + 1])
                        i += 2

                        if command.islower():
                            nx += current[0]
                            ny += current[1]

                        if command.lower() == "m":
                            start = (nx, ny)

                        segments.append(
                            Segment(
                                current[0],
                                current[1],
                                nx,
                                ny,
                                True,
                            )
                        )

                        current = (nx, ny)

                        if command in ("M", "m"):
                            command = "L" if command == "M" else "l"

                    elif command in ("H", "h"):
                        nx = float(commands[i])
                        i += 1

                        if command == "h":
                            nx += current[0]

                        segments.append(
                            Segment(
                                current[0],
                                current[1],
                                nx,
                                current[1],
                                True,
                            )
                        )

                        current = (nx, current[1])

                    elif command in ("V", "v"):
                        ny = float(commands[i])
                        i += 1

                        if command == "v":
                            ny += current[1]

                        segments.append(
                            Segment(
                                current[0],
                                current[1],
                                current[0],
                                ny,
                                True,
                            )
                        )

                        current = (current[0], ny)

                    else:
                        i += 1

                except (ValueError, IndexError):
                    i += 1

    return segments
