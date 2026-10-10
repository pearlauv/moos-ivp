"""Production Route clock/deadline tests; requires a configured pShare build."""

import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

SHARE = Path(__file__).resolve().parents[1]
ROOT = SHARE.parents[3]
BUILD = Path(
    os.environ.get(
        "PSHARE_BUILD_DIR", ROOT / "build/MOOS/MOOSEssentials/Essentials/pShare"
    )
)


class RateClockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="pshare-rate-clock-unit-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.binary = Path(cls.directory.name) / "test_rate_clock"
        flags = {}
        for line in (
            (BUILD / "CMakeFiles/pShare.dir/flags.make").read_text().splitlines()
        ):
            if " = " in line:
                key, value = line.split(" = ", 1)
                flags[key] = shlex.split(value)
        link = shlex.split((BUILD / "CMakeFiles/pShare.dir/link.txt").read_text())
        libraries = link[link.index("-o") + 2 :]
        subprocess.run(
            [
                os.environ.get("CXX", "c++"),
                "-std=c++11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wno-error=type-limits",  # Existing unsigned max_shares >= 0 check.
                *flags["CXX_DEFINES"],
                *flags["CXX_INCLUDES"],
                "-I" + str(SHARE),
                str(Path(__file__).with_suffix(".cpp")),
                str(SHARE / "Route.cpp"),
                *libraries,
                "-pthread",
                "-o",
                str(cls.binary),
            ],
            cwd=BUILD,
            check=True,
            timeout=30,
        )

    def check_case(self, name):
        subprocess.run([str(self.binary), name], check=True, timeout=5)

    def test_deadline_and_clock_rewind_preserve_pending(self):
        self.check_case("gates")

    def test_moos_default_and_explicit_wall_clock(self):
        self.check_case("clocks")

    def test_duration_and_share_count_are_clock_independent(self):
        self.check_case("lifetime")


if __name__ == "__main__":
    unittest.main()
