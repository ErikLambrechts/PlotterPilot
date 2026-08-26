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
    choices: list[str] = field(default_factory=list)


@dataclass
class ConversionProfile:
    path: Path
    name: str
    parameters: list[ProfileParameter] = field(default_factory=list)


class ProfileManager:
    def __init__(self, paths):
        self.paths = list(paths)
        self.profiles: list[ConversionProfile] = []

    def discover(self):
        self.profiles.clear()

        for path in self.paths:
            if not path.exists():
                continue

            if not path.is_file():
                continue

            try:
                result = subprocess.run(
                    [str(path), "--json"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=True,
                )

                data = json.loads(result.stdout)

                params = []

                for name, spec in data.items():
                    if name in {"input", "output"}:
                        continue

                    params.append(
                        ProfileParameter(
                            name=name,
                            type=spec.get("type", "string"),
                            default=spec.get("default"),
                            description=spec.get(
                                "description", ""
                            ),
                            minimum=spec.get("minimum"),
                            maximum=spec.get("maximum"),
                            choices=spec.get("choices", []),
                        )
                    )

                self.profiles.append(
                    ConversionProfile(
                        path=path,
                        name=data.get(
                            "_name",
                            path.stem.replace("_", " ").title(),
                        ),
                        parameters=params,
                    )
                )

            except Exception as exc:
                print(
                    f"Profile ignored: {path}: {exc}"
                )

        return self.profiles
