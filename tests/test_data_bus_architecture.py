import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DataBusArchitectureTest(unittest.TestCase):
    def build_and_run(self, top: str, rtl: str, harness: str) -> None:
        verilator = shutil.which(os.environ.get("VERILATOR", "verilator"))
        if verilator is None:
            self.skipTest("verilator is not installed")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "src"
            obj_dir = tmp_path / "obj"
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
                    top,
                    "--Mdir",
                    str(obj_dir),
                    str(src / "rtl" / rtl),
                    str(src / "sim" / harness),
                ],
                cwd=ROOT,
                check=True,
            )
            subprocess.run([str(obj_dir / f"V{top}")], cwd=ROOT, check=True)

    def test_load_store_unit_stalls_and_completes_single_outstanding(self):
        self.build_and_run("load_store_unit", "load_store_unit.sv", "load_store_unit_tb.cpp")

    def test_data_bus_interconnect_routes_sram_mmio_and_errors(self):
        self.build_and_run(
            "data_bus_interconnect",
            "data_bus_interconnect.sv",
            "data_bus_interconnect_tb.cpp",
        )


if __name__ == "__main__":
    unittest.main()
