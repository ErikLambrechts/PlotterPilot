"""
Plotbot processing layer.

The editor produces a Job.

This module turns that Job into processing stages.

vpype is optional at this stage so the editor can run without
requiring the complete processing environment.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from job_model import Job


SUPPORTED_OPERATIONS = {
    "linesort": {
        "label": "Line sort",
    },
    "linemerge": {
        "label": "Line merge",
    },
    "reloop": {
        "label": "Reloop",
    },
    "linesimplify": {
        "label": "Line simplify",
    },
    "multipass": {
        "label": "Multipass",
    },
    "occult": {
        "label": "Occlude",
    },
    "duplicate": {
        "label": "Duplicate",
    },
    "cfill": {
        "label": "Cfill",
    },
    "font": {
        "label": "Font",
    },
}


def vpype_available():
    return shutil.which("vpype") is not None


def build_vpype_command(job: Job):
    """
    Build a conservative vpype command.

    More sophisticated command generation can be added later.
    """

    commands = []

    for step in job.processing:
        if not step.enabled:
            continue

        operation = step.operation
        params = step.parameters

        if operation == "linesort":
            commands.append("linesort")

        elif operation == "linemerge":
            tolerance = params.get(
                "tolerance",
                0,
            )

            commands.extend([
                "linemerge",
                str(tolerance),
            ])

        elif operation == "reloop":
            commands.append("reloop")

        elif operation == "linesimplify":
            tolerance = params.get(
                "tolerance",
                0.1,
            )

            commands.extend([
                "linesimplify",
                str(tolerance),
            ])

        elif operation == "multipass":
            count = int(
                params.get(
                    "count",
                    2,
                )
            )

            commands.extend([
                "multipass",
                str(count),
            ])

        elif operation == "duplicate":
            count = int(
                params.get(
                    "count",
                    2,
                )
            )

            commands.extend([
                "dup",
                str(count),
            ])

        elif operation == "cfill":
            # cfill command syntax can depend on the installed
            # vpype-gcode/plugin version. Keep parameters explicit.
            density = params.get(
                "density",
                1.0,
            )

            commands.extend([
                "cfill",
                str(density),
            ])

    return commands


def process_svg(
    input_svg,
    output_svg,
    job: Job,
):
    """
    Run the configured processing pipeline.

    Returns a result dictionary rather than hiding failures.
    """

    if not vpype_available():
        return {
            "ok": False,
            "error": (
                "vpype is not installed or is not "
                "available on PATH"
            ),
        }

    command = [
        "vpype",
    ]

    command.extend([
        "read",
        str(input_svg),
    ])

    command.extend(
        build_vpype_command(job)
    )

    command.extend([
        "write",
        str(output_svg),
    ])

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": command,
    }
