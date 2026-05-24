import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


TINY_VCD = """$version test $end
$timescale 1ps $end
$scope module TOP $end
 $scope module mobile_cpu_power_top $end
  $scope module u_dut $end
   $var wire 1 ! clk $end
   $var wire 1 " core_clk $end
   $var wire 1 # mem_clk $end
   $var wire 1 $ reset_n $end
   $var wire 2 % dvfs_level [1:0] $end
   $var wire 3 & power_mode [2:0] $end
   $var wire 1 ' cpu_power_gate_n $end
   $var wire 1 ( mem_power_gate_n $end
   $var wire 16 ) instr [15:0] $end
   $var wire 1 * retired $end
   $var wire 1 + branch_taken $end
  $upscope $end
 $upscope $end
$upscope $end
$enddefinitions $end
#0
0!
0"
0#
0$
b01 %
b000 &
1'
1(
b0101000100000001 )
1*
0+
#1
1$
#2
1!
1"
1#
#3
0!
0"
0#
#4
b1111000000000000 )
#5
1!
1"
1#
#6
0!
0"
0#
"""


class IEEE2416FlowTest(unittest.TestCase):
    def test_schema_characterization_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            schema = tmp_path / "ieee2416-2025.xsd"
            models = tmp_path / "models"

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "gen_2416_xsd.py"),
                    "--spec",
                    str(ROOT / "spec_model" / "ieee2416_2025_schema.json"),
                    "--out",
                    str(schema),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "characterize_2416.py"),
                    "--tech",
                    str(ROOT / "configs" / "tech" / "generic_7nm.json"),
                    "--out",
                    str(models),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "validate_2416.py"),
                    str(models),
                    "--xsd",
                    str(schema),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            execute_model = (models / "execute_unit.xml").read_text(encoding="utf-8")
            self.assertIn("IEEE2416-2025", execute_model)
            self.assertIn("alu_addi", execute_model)
            self.assertIn("powerContributors", execute_model)
            self.assertIn('componentRef="alu_addi"', execute_model)

    def test_vcd_activity_and_power_estimator(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            vcd = tmp_path / "tiny.vcd"
            models = tmp_path / "models"
            out = tmp_path / "reports"
            vcd.write_text(TINY_VCD, encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "characterize_2416.py"),
                    "--tech",
                    str(ROOT / "configs" / "tech" / "generic_7nm.json"),
                    "--out",
                    str(models),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "estimate_power_2416.py"),
                    "--models",
                    str(models),
                    "--tech",
                    str(ROOT / "configs" / "tech" / "generic_7nm.json"),
                    "--vcd",
                    str(vcd),
                    "--out",
                    str(out),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            activity = json.loads((out / "2416_activity.json").read_text(encoding="utf-8"))
            estimate = json.loads((out / "2416_power_estimate.json").read_text(encoding="utf-8"))
            self.assertEqual(activity["event_counts"]["execute_unit.alu_addi"], 1)
            self.assertEqual(activity["event_counts"]["execute_unit.wait_for_interrupt"], 1)
            self.assertGreater(len(activity["state_timeline"]), 0)
            self.assertGreater(estimate["total_energy_pj"], 0.0)
            self.assertGreater(len(estimate["power_timeline"]), 0)
            self.assertIn("2416 XML macro power models", (out / "2416_power_summary.md").read_text(encoding="utf-8"))
            self.assertTrue((out / "2416_power_waveform.svg").exists())
            self.assertTrue((out / "2416_power_by_block.svg").exists())
            self.assertTrue((out / "2416_power_by_domain.svg").exists())

    def test_comparison_report_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "results"
            out = tmp_path / "compare"
            for label, energy in (("case_a", 1.0), ("case_b", 2.0)):
                result_dir = root / label
                result_dir.mkdir(parents=True)
                (result_dir / "2416_power_estimate.json").write_text(
                    json.dumps(
                        {
                            "technology": "generic_7nm",
                            "scheme": label,
                            "duration_ns": 10.0,
                            "total_energy_pj": energy,
                            "average_power_mw": energy / 10.0,
                            "domains": [],
                            "blocks": [],
                        }
                    ),
                    encoding="utf-8",
                )

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "compare_2416.py"),
                    "--result-root",
                    str(root),
                    "--labels",
                    "case_a",
                    "case_b",
                    "--out",
                    str(out),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertTrue((out / "2416_compare_summary.md").exists())
            self.assertTrue((out / "2416_compare_energy.svg").exists())
            self.assertIn("case_b", (out / "2416_compare.csv").read_text(encoding="utf-8"))

    def test_dvfs_exploration_report_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            vcd = tmp_path / "tiny.vcd"
            models = tmp_path / "models"
            opps = tmp_path / "opps.json"
            out = tmp_path / "dvfs"
            vcd.write_text(TINY_VCD, encoding="utf-8")
            opps.write_text(
                json.dumps(
                    {
                        "name": "test_opps",
                        "opps": [
                            {
                                "name": "LOW",
                                "dvfs_level": "0",
                                "cpu_voltage_v": 0.60,
                                "cpu_frequency_mhz": 300.0,
                                "mem_voltage_v": 0.80,
                                "mem_frequency_mhz": 300.0,
                            },
                            {
                                "name": "NOMINAL",
                                "dvfs_level": "1",
                                "cpu_voltage_v": 0.80,
                                "cpu_frequency_mhz": 900.0,
                                "mem_voltage_v": 0.80,
                                "mem_frequency_mhz": 900.0,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "characterize_2416.py"),
                    "--tech",
                    str(ROOT / "configs" / "tech" / "generic_7nm.json"),
                    "--out",
                    str(models),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "dvfs_explore_2416.py"),
                    "--models",
                    str(models),
                    "--tech",
                    str(ROOT / "configs" / "tech" / "generic_7nm.json"),
                    "--opps",
                    str(opps),
                    "--vcd",
                    str(vcd),
                    "--out",
                    str(out),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertTrue((out / "dvfs_summary.md").exists())
            self.assertTrue((out / "dvfs_energy.svg").exists())
            self.assertTrue((out / "dvfs_contributors.svg").exists())
            points = (out / "dvfs_points.csv").read_text(encoding="utf-8")
            self.assertIn("LOW", points)
            self.assertIn("NOMINAL", points)


if __name__ == "__main__":
    unittest.main()
