from __future__ import annotations

import copy
import html
import math
import re
from pathlib import Path
from xml.etree import ElementTree as ET


SVG_NS = "http://www.w3.org/2000/svg"


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def parse_viewbox(svg: ET.Element):
    value = svg.get("viewBox")

    if not value:
        return 0.0, 0.0, 100.0, 100.0

    values = [
        float(x)
        for x in re.split(r"[,\s]+", value.strip())
        if x
    ]

    if len(values) != 4:
        return 0.0, 0.0, 100.0, 100.0

    return tuple(values)


def read_svg(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def transform_svg(
    svg_text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    rotation: float,
) -> str:
    """
    Wrap an SVG in a transformed group.

    Coordinates are expressed in the PlotJob page coordinate system.
    """

    root = ET.fromstring(svg_text)

    min_x, min_y, source_w, source_h = parse_viewbox(root)

    if source_w == 0:
        source_w = 100

    if source_h == 0:
        source_h = 100

    scale_x = width / source_w
    scale_y = height / source_h

    group = ET.Element(
        f"{{{SVG_NS}}}g",
        {
            "transform": (
                f"translate({x} {y}) "
                f"rotate({rotation}) "
                f"translate({-width / 2} {-height / 2}) "
                f"scale({scale_x} {scale_y}) "
                f"translate({-min_x} {-min_y})"
            )
        },
    )

    children = list(root)

    for child in children:
        group.append(copy.deepcopy(child))

    root[:] = []

    root.append(group)

    root.set(
        "viewBox",
        f"0 0 {width} {height}",
    )

    root.set(
        "width",
        str(width),
    )

    root.set(
        "height",
        str(height),
    )

    return ET.tostring(
        root,
        encoding="unicode",
    )


def build_svg(job: dict, base_dir: Path) -> str:
    page = job.get("page", {})

    width = float(page.get("width", 210))
    height = float(page.get("height", 297))

    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}mm" height="{height}mm" '
            f'viewBox="0 0 {width} {height}">'
        )
    ]

    for obj in job.get("objects", []):
        obj_type = obj.get("type")

        if obj_type == "svg":
            source = obj.get("source")

            if not source:
                svg_text = obj.get("svg", "")
            else:
                source_path = Path(source)

                if not source_path.is_absolute():
                    source_path = base_dir / source_path

                svg_text = read_svg(source_path)

            if not svg_text:
                continue

            transformed = transform_svg(
                svg_text,
                float(obj.get("x", width / 2)),
                float(obj.get("y", height / 2)),
                float(obj.get("width", 50)),
                float(obj.get("height", 50)),
                float(obj.get("rotation", 0)),
            )

            inner = transformed[
                transformed.find(">") + 1:
                transformed.rfind("</svg>")
            ]

            parts.append(inner)

        elif obj_type == "text":
            text = html.escape(str(obj.get("text", "")))

            x = float(obj.get("x", width / 2))
            y = float(obj.get("y", height / 2))

            size = float(obj.get("fontSize", 12))

            font = html.escape(
                str(obj.get("font", "Arial"))
            )

            weight = (
                "bold"
                if obj.get("bold")
                else "normal"
            )

            rotation = float(
                obj.get("rotation", 0)
            )

            parts.append(
                f'<text x="{x}" y="{y}" '
                f'font-family="{font}" '
                f'font-size="{size}" '
                f'font-weight="{weight}" '
                f'transform="rotate({rotation} {x} {y})">'
                f'{text}</text>'
            )

        elif obj_type == "vpype-text":
            # This remains a semantic object.
            #
            # vpype-font processing will be added as a dedicated
            # operation rather than silently converting it here.
            text = html.escape(
                str(obj.get("text", ""))
            )

            x = float(obj.get("x", width / 2))
            y = float(obj.get("y", height / 2))

            parts.append(
                f'<text x="{x}" y="{y}" '
                f'data-plotjob-vpype-text="true">'
                f'{text}</text>'
            )

    parts.append("</svg>")

    return "\n".join(parts)
