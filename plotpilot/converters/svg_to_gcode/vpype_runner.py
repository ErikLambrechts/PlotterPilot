from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class VpypeError(RuntimeError):
    pass


def find_vpype() -> str | None:
    return shutil.which("vpype")


def run_vpype(
    svg_path: Path,
    output_path: Path,
    operations: list[dict],
) -> None:
    vpype = find_vpype()

    if not vpype:
        raise VpypeError(
            "vpype is not installed or is not available on PATH"
        )

    command = [vpype, "read", str(svg_path)]

    for operation in operations:
        name = operation.get("name")

        if not name:
            continue

        command.append(name)

        parameters = operation.get("parameters", {})

        for key, value in parameters.items():
            if isinstance(value, bool):
                if value:
                    command.append(f"--{key}")
            else:
                command.extend([
                    f"--{key}",
                    str(value),
                ])

    command.extend([
        "write",
        str(output_path),
    ])

    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        raise VpypeError(
            "vpype failed:\n\n"
            + (result.stderr or result.stdout)
        )
