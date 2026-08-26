from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConversionProfile:
    name: str
    path: Path
    spec: dict = field(default_factory=dict)

    def load_spec(self):
        try:
            result = subprocess.run(
                [str(self.path), "--json"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return

            self.spec = json.loads(result.stdout)
        except Exception:
            self.spec = {}


class ConversionProfiles:
    def __init__(self, directory: Path):
        self.directory = directory
        self.profiles: list[ConversionProfile] = []
        self.reload()

    def reload(self):
        self.profiles.clear()

        if not self.directory.exists():
            return

        for path in sorted(self.directory.glob("*.sh")):
            profile = ConversionProfile(
                path.stem,
                path,
            )

            profile.load_spec()
            self.profiles.append(profile)

    def get(self, name):
        return next(
            (p for p in self.profiles if p.name == name),
            None,
        )

    def convert(
        self,
        profile: ConversionProfile,
        input_path: Path,
        output_path: Path,
        parameters: dict,
    ):
        command = [
            str(profile.path),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]

        for key, value in parameters.items():
            if key in {"input", "output"}:
                continue

            if isinstance(value, bool):
                if value:
                    command.append(f"--{key}")
            else:
                command.extend([
                    f"--{key}",
                    str(value),
                ])

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or "Conversion failed"
            )

        if not output_path.exists():
            raise RuntimeError(
                "Conversion completed without creating G-code"
            )
