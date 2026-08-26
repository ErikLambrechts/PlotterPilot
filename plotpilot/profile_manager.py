from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProfileParameter:
    name: str
    type: str = "string"
    default: object = None
    description: str = ""
    minimum: float | None = None
    maximum: float | None = None
    options: list[str] = field(default_factory=list)


@dataclass
class ConversionProfile:
    name: str
    path: Path
    description: str = ""
    parameters: list[ProfileParameter] = field(
        default_factory=list
    )
    spec: dict = field(default_factory=dict)

    @property
    def command(self) -> str:
        return str(self.path)


def discover_profiles(
    directory: Path,
) -> list[ConversionProfile]:
    """
    Discover conversion profiles.

    Every *.sh file is queried with:

        script --json

    The returned JSON defines the profile interface.
    """

    directory = Path(directory).resolve()

    profiles: list[ConversionProfile] = []

    if not directory.is_dir():
        return profiles

    for script in sorted(directory.glob("*.sh")):

        if not script.is_file():
            continue

        try:
            result = subprocess.run(
                [str(script), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            continue

        if result.returncode != 0:
            continue

        try:
            spec = json.loads(result.stdout)
        except json.JSONDecodeError:
            continue

        if not isinstance(spec, dict):
            continue

        raw_parameters = spec.get(
            "parameters",
            {},
        )

        if not isinstance(raw_parameters, dict):
            raw_parameters = {}

        parameters = []

        for name, value in raw_parameters.items():

            if not isinstance(value, dict):
                continue

            parameters.append(
                ProfileParameter(
                    name=str(name),
                    type=str(
                        value.get(
                            "type",
                            "string",
                        )
                    ),
                    default=value.get(
                        "default"
                    ),
                    description=str(
                        value.get(
                            "description",
                            "",
                        )
                    ),
                    minimum=value.get(
                        "minimum"
                    ),
                    maximum=value.get(
                        "maximum"
                    ),
                    options=value.get(
                        "options",
                        [],
                    ),
                )
            )

        # Profile name comes from the profile parameter's default.
        #
        # This matches the current CLI contract:
        #
        # parameters:
        #   profile:
        #     default: single-color

        profile_parameter = raw_parameters.get(
            "profile"
        )

        if isinstance(
            profile_parameter,
            dict,
        ):
            name = profile_parameter.get(
                "default"
            )
        else:
            name = None

        if not name:
            name = script.stem.replace(
                "_",
                "-",
            )

        description = spec.get(
            "description",
            "",
        )

        profiles.append(
            ConversionProfile(
                name=str(name),
                path=script,
                description=str(
                    description
                ),
                parameters=parameters,
                spec=spec,
            )
        )

    return profiles


def profile_to_json(
    profile: ConversionProfile,
) -> dict:

    return {
        "name": profile.name,
        "path": str(profile.path),
        "description": profile.description,
        "parameters": {
            parameter.name: {
                "type": parameter.type,
                "default": parameter.default,
                "description": parameter.description,
                **(
                    {
                        "minimum":
                            parameter.minimum
                    }
                    if parameter.minimum is not None
                    else {}
                ),
                **(
                    {
                        "maximum":
                            parameter.maximum
                    }
                    if parameter.maximum is not None
                    else {}
                ),
                **(
                    {
                        "options":
                            parameter.options
                    }
                    if parameter.options
                    else {}
                ),
            }
            for parameter in profile.parameters
        },
    }


def convert_svg(
    profile: ConversionProfile,
    input_file: Path,
    output_file: Path,
    parameters: dict | None = None,
) -> Path:
    """
    Execute a conversion profile.

    input and output are always supplied by PlotPilot.
    """

    parameters = parameters or {}

    command = [
        str(profile.path),
        "--input",
        str(input_file),
        "--output",
        str(output_file),
    ]

    for parameter in profile.parameters:

        if parameter.name not in parameters:
            continue

        value = parameters[
            parameter.name
        ]

        if parameter.type == "boolean":

            if bool(value):
                command.append(
                    f"--{parameter.name}"
                )

        else:
            command.extend(
                [
                    f"--{parameter.name}",
                    str(value),
                ]
            )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or "Conversion failed"
        )

    if not output_file.exists():
        raise RuntimeError(
            "Conversion completed but did not "
            "create the output file"
        )

    return output_file
