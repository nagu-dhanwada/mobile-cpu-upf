import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DataflowUnitRtlTest(unittest.TestCase):
    def test_mmio_command_status_and_repeat_mode(self):
        verilator = shutil.which(os.environ.get("VERILATOR", "verilator"))
        if verilator is None:
            self.skipTest("verilator is not installed")

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            obj_dir = Path(tmp) / "obj"
            src.symlink_to(ROOT, target_is_directory=True)
            subprocess.run(
                [
                    verilator,
                    "--cc",
                    "--exe",
                    "--build",
                    "--sv",
                    "-Wall",
                    "-Wno-UNUSEDSIGNAL",
                    "-Wno-DECLFILENAME",
                    "-CFLAGS",
                    "-std=c++17 -Wno-unknown-warning-option",
                    "--top-module",
                    "dataflow_unit",
                    "--Mdir",
                    str(obj_dir),
                    str(src / "rtl" / "dataflow_unit.sv"),
                    str(src / "sim" / "dataflow_unit_tb.cpp"),
                ],
                cwd=ROOT,
                check=True,
            )
            subprocess.run([str(obj_dir / "Vdataflow_unit")], cwd=ROOT, check=True)


if __name__ == "__main__":
    unittest.main()
