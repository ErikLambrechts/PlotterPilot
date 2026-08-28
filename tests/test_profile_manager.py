from __future__ import annotations

import stat
import tempfile
import textwrap
import unittest
from pathlib import Path

from plotpilot.profile_manager import (
    ConversionProfile,
    ProfileParameter,
    convert_svg,
    discover_profiles,
)


class ProfileManagerTests(unittest.TestCase):
    def test_discover_profiles_from_directory_and_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            bash_profile = root / "linework.sh"
            bash_profile.write_text(
                "#!/usr/bin/env bash\n"
                "cat <<'JSON'\n"
                '{"description":"bash profile","input":{"type":"svg"},"output":{"type":"gcode"},"parameters":{"profile":{"default":"linework"}}}\n'
                "JSON\n",
                encoding="utf-8",
            )
            bash_profile.chmod(
                bash_profile.stat().st_mode
                | stat.S_IXUSR
            )

            python_profile = root / "clean.py"
            python_profile.write_text(
                textwrap.dedent(
                    """
                    import json, sys
                    if "--json" in sys.argv:
                        print(json.dumps({
                            "name": "clean-svg",
                            "description": "python profile",
                            "input": {"type": "svg"},
                            "output": {"type": "svg"},
                            "parameters": {}
                        }))
                    """
                ),
                encoding="utf-8",
            )

            profiles = discover_profiles(root)

            self.assertEqual(2, len(profiles))
            names = {p.name for p in profiles}
            self.assertIn("linework", names)
            self.assertIn("clean", names)

            single = discover_profiles(python_profile)
            self.assertEqual(1, len(single))
            self.assertEqual("clean", single[0].name)
            self.assertEqual("svg", single[0].input_type)
            self.assertEqual("svg", single[0].output_type)

    def test_convert_svg_uses_python_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "in.svg"
            target = root / "out.gcode"
            source.write_text("<svg/>", encoding="utf-8")

            converter = root / "convert.py"
            converter.write_text(
                textwrap.dedent(
                    """
                    import pathlib
                    import sys

                    argv = sys.argv[1:]
                    if "--json" in argv:
                        print('{"description":"convert","parameters":{"pen":{"type":"string"}}}')
                        raise SystemExit(0)

                    input_file = pathlib.Path(argv[argv.index("--input") + 1])
                    output_file = pathlib.Path(argv[argv.index("--output") + 1])
                    pen = argv[argv.index("--pen") + 1]
                    output_file.write_text(f"G1 X1 Y1 ; {pen} ; {input_file.read_text()}", encoding="utf-8")
                    """
                ),
                encoding="utf-8",
            )

            profile = ConversionProfile(
                name="convert",
                path=converter,
                parameters=[],
            )
            profile.parameters = [
                ProfileParameter(
                    name="pen",
                    type="string",
                )
            ]

            output = convert_svg(
                profile,
                source,
                target,
                {"pen": "blue"},
            )

            self.assertEqual(target, output)
            self.assertIn(
                "blue",
                target.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
