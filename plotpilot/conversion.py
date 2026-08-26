from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConversionProfile:
    name: str
    command: str
    parameters: dict = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return Path(self.command)


def convert(
    profile: ConversionProfile,
    input_file: Path,
    output_file: Path,
    parameters: dict | None = None,
) -> Path:
    """
    Execute a conversion profile.

    The profile script owns the conversion logic.

    PlotPilot always supplies:
        --input
        --output

    Parameters declared by the profile's --json specification
    are passed through as command-line arguments.
    """

    parameters = parameters or {}

    command = [
        str(profile.path),
        "--input",
        str(input_file),
        "--output",
        str(output_file),
    ]

    profile_parameters = profile.parameters

    if not isinstance(profile_parameters, dict):
        profile_parameters = {}

    for name, specification in profile_parameters.items():

        if name not in parameters:
            continue

        value = parameters[name]

        if not isinstance(specification, dict):
            continue

        parameter_type = specification.get(
            "type",
            "string",
        )

        if parameter_type == "boolean":
            if bool(value):
                command.append(
                    f"--{name}"
                )
        else:
            command.extend(
                [
                    f"--{name}",
                    str(value),
                ]
            )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or "Conversion failed"
        )

    if not output_file.exists():
        raise RuntimeError(
            "Conversion completed but did not create "
            f"output file: {output_file}"
        )

    return output_file
