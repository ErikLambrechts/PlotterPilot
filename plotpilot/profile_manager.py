#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import subprocess
import tempfile
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
    def command(self):
        return str(self.path)


def _extract_json_spec(script: Path) -> dict:
    """
    Extract the JSON specification from a conversion script.

    The preferred format is:

        PROFILE_JSON='
        {
          ...
        }
        '

    The fallback is:

        PROFILE_JSON = <<'JSON'
        {
          ...
        }
        JSON
    """

    text = script.read_text(encoding="utf-8")

    patterns = [
        r"PROFILE_JSON\s*=\s*['\"]\s*(\{.*?\})\s*['\"]",
        r"PROFILE_JSON\s*=\s*<<['\"]?JSON['\"]?\s*\n(.*?)\nJSON",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            re.DOTALL,
        )

        if not match:
            continue

        raw = match.group(1)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            continue

    return {}


def discover_profiles(directory: Path) -> list[ConversionProfile]:
    profiles = []

    if not directory.exists():
        return profiles

    for script in sorted(directory.glob("*.sh")):
        if not script.is_file():
            continue

        try:
            spec = _extract_json_spec(script)
        except OSError:
            continue

        parameters = []

        for name, value in spec.items():
            if not isinstance(value, dict):
                continue

            parameters.append(
                ProfileParameter(
                    name=name,
                    type=value.get("type", "string"),
                    default=value.get("default"),
                    description=value.get(
                        "description",
                        "",
                    ),
                    minimum=value.get("minimum"),
                    maximum=value.get("maximum"),
                    options=value.get(
                        "options",
                        [],
                    ),
                )
            )

        profiles.append(
            ConversionProfile(
                name=spec.get(
                    "_name",
                    script.stem,
                ),
                path=script,
                description=spec.get(
                    "_description",
                    "",
                ),
                parameters=parameters,
                spec=spec,
            )
        )

    return profiles


def profile_to_json(profile: ConversionProfile) -> dict:
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
                    {"minimum": parameter.minimum}
                    if parameter.minimum is not None
                    else {}
                ),
                **(
                    {"maximum": parameter.maximum}
                    if parameter.maximum is not None
                    else {}
                ),
                **(
                    {"options": parameter.options}
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
    Run a conversion profile.

    input/output are deliberately always supplied by PlotPilot.
    Profile-specific parameters are appended as --name value.
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

        value = parameters[parameter.name]

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
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or "Conversion failed"
        )

    return output_file
