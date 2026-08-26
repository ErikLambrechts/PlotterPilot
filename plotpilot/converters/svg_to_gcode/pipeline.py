from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .gcode import svg_to_gcode
from .svg_builder import build_svg
from .vpype_runner import run_vpype


def load_job(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        job = json.load(f)

    if not isinstance(job, dict):
        raise ValueError("Job must be a JSON object")

    if job.get("type") != "plotjob":
        raise ValueError(
            "Unsupported job type: "
            + repr(job.get("type"))
        )

    return job


def process_job(
    job_path: Path,
    output_path: Path,
    *,
    keep_intermediate: bool = False,
) -> Path:

    job_path = job_path.resolve()
    output_path = output_path.resolve()

    job = load_job(job_path)

    base_dir = job_path.parent

    operations = (
        job.get("processing", {})
        .get("operations", [])
    )

    with tempfile.TemporaryDirectory(
        prefix="plotjob_"
    ) as temp:

        temp_dir = Path(temp)

        source_svg = temp_dir / "source.svg"
        processed_svg = temp_dir / "processed.svg"

        source_svg.write_text(
            build_svg(job, base_dir),
            encoding="utf-8",
        )

        current_svg = source_svg

        if operations:
            run_vpype(
                current_svg,
                processed_svg,
                operations,
            )

            current_svg = processed_svg

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        svg_to_gcode(
            current_svg,
            output_path,
            job,
        )

        if keep_intermediate:
            retained = (
                output_path.parent /
                f"{output_path.stem}.processed.svg"
            )

            retained.write_text(
                current_svg.read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )

    return output_path
