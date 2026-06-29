import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPENLOWPOWER_XSD = Path.home() / "Downloads" / "2416.xsd"


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

TINY_GATE_VCD = """$version test $end
$timescale 1ps $end
$scope module TOP $end
 $scope module mobile_cpu_top $end
  $scope module u_execute $end
   $var wire 1 ! n1 $end
  $upscope $end
 $upscope $end
$upscope $end
$enddefinitions $end
#0
0!
#1
1!
#2
0!
"""

TINY_LIBERTY = """
library (tiny) {
  leakage_power_unit : "1nW";
  capacitive_load_unit (1,ff);
  nom_voltage : 1.10;
  cell (AND2_X1) {
    area : 1.0;
    cell_leakage_power : 10.0;
    pin (A1) { direction : input; capacitance : 1.0; }
    pin (A2) { direction : input; capacitance : 1.0; }
    pin (ZN) { direction : output; function : "(A1 & A2)"; }
    internal_power () {
      values ("1.0,2.0");
    }
  }
  cell (DFFR_X1) {
    area : 4.0;
    cell_leakage_power : 40.0;
    ff (IQ, IQN) { clocked_on : "CK"; next_state : "D"; }
    pin (D) { direction : input; capacitance : 1.0; }
    pin (CK) { direction : input; capacitance : 2.0; }
    pin (RN) { direction : input; capacitance : 1.0; }
    pin (Q) { direction : output; function : "IQ"; }
    internal_power () {
      values ("3.0,5.0");
    }
  }
}
"""


class IEEE2416FlowTest(unittest.TestCase):
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

    def test_openlowpower_ieee2416_library_generation_and_estimation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            library = tmp_path / "mobile_cpu_library.xml"
            report_dir = tmp_path / "reports"
            vcd = tmp_path / "tiny.vcd"
            vcd.write_text(TINY_VCD, encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "ieee2416" / "characterize.py"),
                    "--tech",
                    str(ROOT / "configs" / "tech" / "generic_7nm.json"),
                    "--out",
                    str(library),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "ieee2416" / "validate.py"),
                    str(library),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            if OPENLOWPOWER_XSD.exists():
                subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "tools" / "ieee2416" / "validate.py"),
                        str(library),
                        "--xsd",
                        str(OPENLOWPOWER_XSD),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )

            xml = library.read_text(encoding="utf-8")
            self.assertIn('xmlns="OpenLowPower"', xml)
            self.assertIn('<Cell name="execute_unit"', xml)
            self.assertIn('<Cell name="dataflow_unit"', xml)
            self.assertIn('<Events>', xml)
            self.assertIn('<States units="mW"', xml)

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "ieee2416" / "estimate.py"),
                    "--model",
                    str(library),
                    "--tech",
                    str(ROOT / "configs" / "tech" / "generic_7nm.json"),
                    "--vcd",
                    str(vcd),
                    "--out",
                    str(report_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            estimate = json.loads((report_dir / "2416_power_estimate.json").read_text(encoding="utf-8"))
            self.assertEqual(estimate["model_format"], "OpenLowPower IEEE 2416 Library")
            self.assertGreater(estimate["total_energy_pj"], 0.0)
            self.assertTrue((report_dir / "2416_power_waveform.svg").exists())

    def test_dvfs_exploration_report_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            vcd = tmp_path / "tiny.vcd"
            model = tmp_path / "mobile_cpu_library.xml"
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
                    str(ROOT / "tools" / "ieee2416" / "characterize.py"),
                    "--tech",
                    str(ROOT / "configs" / "tech" / "generic_7nm.json"),
                    "--out",
                    str(model),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "dvfs_explore_2416.py"),
                    "--model",
                    str(model),
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

    def test_synth_rom_and_metrics_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            memh = tmp_path / "program.memh"
            rom = tmp_path / "instr_rom_synth.sv"
            yosys_json = tmp_path / "mobile_cpu_synth.json"
            metrics = tmp_path / "metrics.json"
            summary = tmp_path / "metrics.md"

            memh.write_text("5101\nf000\n", encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "gen_synth_rom.py"),
                    "--memh",
                    str(memh),
                    "--out",
                    str(rom),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("16'h5101", rom.read_text(encoding="utf-8"))

            yosys_json.write_text(
                json.dumps(
                    {
                        "modules": {
                            "execute_unit": {
                                "cells": {
                                    "u1": {"type": "$_AND_"},
                                    "u2": {"type": "$_DFF_PN0_"},
                                }
                            },
                            "fetch_unit": {"cells": {"u1": {"type": "$_DFF_PN0_"}}},
                            "instr_rom": {"cells": {"u1": {"type": "$_MUX_"}, "u2": {"type": "$_MUX_"}}},
                            "decode_unit": {"cells": {"u1": {"type": "$_OR_"}}},
                            "regfile": {"cells": {"u1": {"type": "$_DFF_PN0_"}}},
                            "data_sram": {"cells": {"u1": {"type": "$_DFF_PN0_"}}},
                            "power_controller": {"cells": {"u1": {"type": "$_DFF_PN0_"}}},
                        }
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "synth_metrics.py"),
                    "--json",
                    str(yosys_json),
                    "--out",
                    str(metrics),
                    "--summary",
                    str(summary),
                    "--workload",
                    "unit",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            metric_data = json.loads(metrics.read_text(encoding="utf-8"))
            self.assertEqual(metric_data["blocks"]["execute_unit"]["sequential_cells"], 1)
            self.assertGreater(metric_data["totals"]["estimated_equivalent_gates"], 0)
            self.assertTrue(summary.exists())

    def test_synthesis_calibrated_2416_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            synth_model = tmp_path / "mobile_cpu_synth_library.xml"
            metrics = tmp_path / "metrics.json"

            metrics.write_text(
                json.dumps(
                    {
                        "source": "unit",
                        "workload": "unit",
                        "blocks": {
                            block: {
                                "cell_count": 10,
                                "combinational_cells": 6,
                                "sequential_cells": 1,
                                "latch_cells": 0,
                                "memory_cells": 0,
                                "estimated_equivalent_gates": 10.0,
                            }
                            for block in (
                                "fetch_unit",
                                "instr_rom",
                                "decode_unit",
                                "regfile",
                                "execute_unit",
                                "data_sram",
                                "dataflow_unit",
                                "power_controller",
                            )
                        },
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "ieee2416" / "synth_characterize.py"),
                    "--tech",
                    str(ROOT / "configs" / "tech" / "generic_7nm.json"),
                    "--metrics",
                    str(metrics),
                    "--out",
                    str(synth_model),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "ieee2416" / "validate.py"),
                    str(synth_model),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            execute_model = synth_model.read_text(encoding="utf-8")
            self.assertIn('<Cell name="execute_unit"', execute_model)
            self.assertIn('value="synthesis_calibrated_macro"', execute_model)
            self.assertIn('value="gate"', execute_model)
            self.assertIn("synthesis_dynamic_calibration", execute_model)

    def test_stdcell_and_memory_macro_model_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            liberty = tmp_path / "tiny.lib"
            techlib = tmp_path / "tiny_techlib.json"
            stdcells = tmp_path / "stdcells"
            macros = tmp_path / "macros"
            liberty.write_text(TINY_LIBERTY, encoding="utf-8")
            techlib.write_text(
                json.dumps(
                    {
                        "name": "tiny45",
                        "process": {"node_nm": 45, "corner": "typical"},
                        "temperature_c": 25.0,
                        "liberty": str(liberty),
                        "source": "unit",
                    }
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "ieee2416" / "stdcell.py"),
                    "--techlib",
                    str(techlib),
                    "--out",
                    str(stdcells / "tiny45_stdcells_library.xml"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "ieee2416" / "memory_macros.py"),
                    "--config",
                    str(ROOT / "configs" / "memory_macros" / "mobile_cpu_memory_macros.json"),
                    "--out",
                    str(macros / "mobile_cpu_memory_macros.xml"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            summary = json.loads((stdcells / "stdcells_summary.json").read_text(encoding="utf-8"))
            self.assertIn("AND2_X1", summary["cells"])
            self.assertTrue(summary["cells"]["DFFR_X1"]["is_sequential"])
            self.assertIn('<Cell name="AND2_X1"', (stdcells / "tiny45_stdcells_library.xml").read_text(encoding="utf-8"))
            self.assertIn('<Cell name="data_sram"', (macros / "mobile_cpu_memory_macros.xml").read_text(encoding="utf-8"))

    def test_mapped_power_estimator_with_macro_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            gate_vcd = tmp_path / "gate.vcd"
            activity = tmp_path / "activity.json"
            metrics = tmp_path / "metrics.json"
            liberty = tmp_path / "tiny.lib"
            techlib = tmp_path / "tiny_techlib.json"
            stdcell_model = tmp_path / "tiny45_stdcells_library.xml"
            memory_model = tmp_path / "mobile_cpu_memory_macros.xml"
            out = tmp_path / "mapped"
            gate_vcd.write_text(TINY_GATE_VCD, encoding="utf-8")
            liberty.write_text(TINY_LIBERTY, encoding="utf-8")
            techlib.write_text(
                json.dumps(
                    {
                        "name": "tiny45",
                        "process": {"node_nm": 45, "corner": "typical"},
                        "temperature_c": 25.0,
                        "liberty": str(liberty),
                        "source": "unit",
                    }
                ),
                encoding="utf-8",
            )
            activity.write_text(
                json.dumps(
                    {
                        "source": "unit_activity",
                        "duration_ps": 1000.0,
                        "state_durations_ps": {"RUN": 1000.0},
                        "dvfs_durations_ps": {"1": 1000.0},
                        "clock_cycles": {"top": 10, "core": 10, "mem": 10},
                        "clock_cycles_by_dvfs": {"top": {"1": 10}, "core": {"1": 10}, "mem": {"1": 10}},
                        "event_counts": {"instr_rom.instruction_fetch": 2, "data_sram.read": 1},
                        "event_counts_by_dvfs": {
                            "instr_rom.instruction_fetch": {"1": 2},
                            "data_sram.read": {"1": 1},
                        },
                        "block_toggles": {},
                        "mode_transitions": {},
                        "state_timeline": [
                            {"start_ps": 0.0, "end_ps": 1000.0, "duration_ps": 1000.0, "state": "RUN", "dvfs": "1"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            metrics.write_text(
                json.dumps(
                    {
                        "blocks": {
                            "execute_unit": {"module": "execute_unit", "cell_types": {"AND2_X1": 2}},
                            "power_controller": {"module": "power_controller", "cell_types": {"DFFR_X1": 1}},
                            "fetch_unit": {"module": "fetch_unit", "cell_types": {}},
                            "decode_unit": {"module": "decode_unit", "cell_types": {}},
                            "regfile": {"module": "regfile", "cell_types": {}},
                            "instr_rom": {"module": "instr_rom", "cell_types": {}},
                            "data_sram": {"module": "data_sram", "cell_types": {}},
                        }
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "ieee2416" / "stdcell.py"),
                    "--techlib",
                    str(techlib),
                    "--out",
                    str(stdcell_model),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "ieee2416" / "memory_macros.py"),
                    "--config",
                    str(ROOT / "configs" / "memory_macros" / "mobile_cpu_memory_macros.json"),
                    "--out",
                    str(memory_model),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "estimate_mapped_power_2416.py"),
                    "--metrics",
                    str(metrics),
                    "--stdcell-model",
                    str(stdcell_model),
                    "--memory-model",
                    str(memory_model),
                    "--tech",
                    str(ROOT / "configs" / "tech" / "generic_7nm.json"),
                    "--activity",
                    str(activity),
                    "--gate-vcd",
                    str(gate_vcd),
                    "--out",
                    str(out),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            result = json.loads((out / "2416_power_estimate.json").read_text(encoding="utf-8"))
            self.assertGreater(result["total_energy_pj"], 0.0)
            self.assertTrue((out / "2416_power_by_block.svg").exists())
            self.assertIn("memory_macro", (out / "2416_power_summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
