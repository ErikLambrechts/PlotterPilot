from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plotpilot.jobs import JobManager


class JobManagerTests(unittest.TestCase):
    def test_generated_gcode_job_deactivates_svg_and_copies_transform(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg = root / "shape.svg"
            gcode = root / "shape.gcode"

            svg.write_text("<svg/>", encoding="utf-8")
            gcode.write_text("G1 X10 Y0 F1000\n", encoding="utf-8")

            manager = JobManager()
            source = manager.add_file(svg)

            source.repeat_anchors = True
            source.repeated_anchors = ["A"]
            source.transform.offset_x = 12
            source.transform.offset_y = 34

            generated = manager.create_gcode_job(
                source,
                gcode,
                "demo",
                {"feed_rate": 1000},
            )

            self.assertFalse(source.active)
            self.assertFalse(source.visible)
            self.assertTrue(generated.active)
            self.assertEqual(
                source.repeated_anchors,
                generated.repeated_anchors,
            )
            self.assertEqual(
                source.repeat_anchors,
                generated.repeat_anchors,
            )
            self.assertIsNot(
                source.transform,
                generated.transform,
            )
            self.assertEqual(
                12,
                generated.transform.offset_x,
            )

    def test_metrics_uses_parsed_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "line.gcode"
            path.write_text(
                "G1 X10 Y0 F600\nG0 X0 Y0 F600\n",
                encoding="utf-8",
            )

            manager = JobManager()
            job = manager.add_file(path)

            metrics = manager.metrics(job)

            self.assertGreater(
                metrics["time"],
                0,
            )
            self.assertGreater(
                metrics["draw_distance"],
                0,
            )
            self.assertGreater(
                metrics["travel_distance"],
                0,
            )


if __name__ == "__main__":
    unittest.main()
