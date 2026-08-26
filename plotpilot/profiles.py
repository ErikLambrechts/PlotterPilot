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


class ProfileManager:

    def __init__(
        self,
        directories,
    ):
        self.directories = [
            Path(directory)
            for directory in directories
        ]
        self.profiles: list[ConversionProfile] = []

    def discover(self):
        self.profiles.clear()

        for directory in self.directories:
            directory = directory.resolve()

            if not directory.is_dir():
                continue

            for script in sorted(
                directory.glob("*.sh")
            ):
                if not script.is_file():
                    continue

                try:
                    spec = self._query_json(script)
                except Exception as exc:
                    print(
                        f"Profile ignored: "
                        f"{script}: {exc}"
                    )
                    continue

                raw_parameters = spec.get(
                    "parameters",
                    {},
                )

                if not isinstance(
                    raw_parameters,
                    dict,
                ):
                    raw_parameters = {}

                parameters = []

                for name, value in raw_parameters.items():

                    if not isinstance(value, dict):
                        continue

                    parameters.append(
                        ProfileParameter(
                            name=name,
                            type=value.get(
                                "type",
                                "string",
                            ),
                            default=value.get(
                                "default"
                            ),
                            description=value.get(
                                "description",
                                "",
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

                name = script.stem.replace(
                    "_",
                    "-",
                )

                profile_parameter = (
                    raw_parameters.get(
                        "profile"
                    )
                )

                if isinstance(
                    profile_parameter,
                    dict,
                ):
                    default_name = (
                        profile_parameter.get(
                            "default"
                        )
                    )

                    if default_name:
                        name = str(
                            default_name
                        )

                self.profiles.append(
                    ConversionProfile(
                        name=name,
                        path=script,
                        description=spec.get(
                            "description",
                            "",
                        ),
                        parameters=parameters,
                        spec=spec,
                    )
                )

        return self.profiles

    @staticmethod
    def _query_json(script: Path) -> dict:
        result = subprocess.run(
            [
                str(script),
                "--json",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or result.stdout.strip()
                or "--json failed"
            )

        try:
            data = json.loads(
                result.stdout
            )
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"invalid JSON: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise RuntimeError(
                "JSON root must be an object"
            )

        return data

    def get(
        self,
        name: str,
    ) -> ConversionProfile | None:

        for profile in self.profiles:
            if profile.name == name:
                return profile

        return None
