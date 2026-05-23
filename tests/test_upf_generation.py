import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UpfGenerationTest(unittest.TestCase):
    def test_all_schemes_generate_expected_upf(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "gen_upf.py"),
                    "--schemes",
                    str(ROOT / "power_schemes"),
                    "--out",
                    str(out_dir)
                ],
                check=True,
                capture_output=True,
                text=True
            )

            upf_files = sorted(out_dir.glob("*.upf"))
            self.assertEqual(len(upf_files), 4)

            core_sleep = (out_dir / "core_power_gated_sleep.upf").read_text(encoding="utf-8")
            self.assertIn("create_power_switch SW_CPU", core_sleep)
            self.assertIn("set_isolation ISO_CPU", core_sleep)
            self.assertIn("set_retention RET_CPU_REGS", core_sleep)
            self.assertIn("add_pst_state DEEP_SLEEP", core_sleep)

            dvfs = (out_dir / "dvfs_retention_domains.upf").read_text(encoding="utf-8")
            self.assertIn("add_power_state SS_CPU -state TURBO", dvfs)
            self.assertIn("set_level_shifter LS_MEM_BOUNDARY", dvfs)


if __name__ == "__main__":
    unittest.main()

