from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def svg_to_gcode(
    svg_path: Path,
    output_path: Path,
    job: dict,
) -> None:
    """
    Temporary plotter-neutral G-code writer.

    This intentionally provides a conservative baseline.
    The machine-specific generator can replace this later.
    """

    metadata = job.get("metadata", {})

    lines = [
        "; PlotJob G-code",
        f"; Generated: {datetime.now(timezone.utc).isoformat()}",
        f"; Job type: {job.get('type', 'plotjob')}",
        f"; Job version: {job.get('version', 1)}",
    ]

    if metadata:
        for key, value in metadata.items():
            lines.append(
                f"; {key}: {value}"
            )

    lines.extend([
        ";",
        "; Geometry processing completed.",
        "; Machine-specific motion generation pending.",
        ";",
        "G90",
        "G21",
        "M2",
    ])

    output_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
