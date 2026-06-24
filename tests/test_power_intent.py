import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from asm import assemble  # noqa: E402
from power_intent import load_scheme  # noqa: E402


class PowerIntentModelTest(unittest.TestCase):
    def test_dvfs_scheme_normalizes_expected_features(self):
        intent = load_scheme("dvfs_retention_domains", ROOT / "power_schemes")
        metadata = intent.to_metadata()

        self.assertEqual(intent.name, "dvfs_retention_domains")
        self.assertTrue(intent.has_domain("PD_AON"))
        self.assertTrue(intent.has_domain("PD_CPU"))
        self.assertTrue(intent.has_domain("PD_MEM"))
        self.assertEqual(metadata["features"]["switched_domain_count"], 2)
        self.assertEqual(metadata["features"]["isolated_domain_count"], 2)
        self.assertEqual(metadata["features"]["retained_domain_count"], 2)
        self.assertGreaterEqual(metadata["features"]["level_shifter_count"], 1)
        self.assertGreaterEqual(metadata["features"]["voltage_crossing_count"], 1)
        self.assertFalse(intent.state_is_on("PD_CPU", "DEEP_SLEEP"))
        self.assertFalse(intent.state_is_on("PD_MEM", "DEEP_SLEEP"))

    def test_generated_sim_metadata_agrees_with_generated_upf(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "sim"
            upf_dir = Path(tmp) / "upf"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "gen_power_sim.py"),
                    "--scheme",
                    "dvfs_retention_domains",
                    "--schemes",
                    str(ROOT / "power_schemes"),
                    "--out",
                    str(out_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "gen_upf.py"),
                    "--schemes",
                    str(ROOT / "power_schemes"),
                    "--out",
                    str(upf_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            metadata = json.loads((out_dir / "power_intent.json").read_text(encoding="utf-8"))
            header = (out_dir / "power_intent.hpp").read_text(encoding="utf-8")
            upf = (upf_dir / "dvfs_retention_domains.upf").read_text(encoding="utf-8")

            domain_names = {domain["name"] for domain in metadata["domains"]}
            self.assertEqual(domain_names, {"PD_AON", "PD_CPU", "PD_MEM"})
            for domain_name in domain_names:
                self.assertIn(f"create_power_domain {domain_name}", upf)

            power_state_names = {state["name"] for state in metadata["power_states"]}
            self.assertIn("DEEP_SLEEP", power_state_names)
            self.assertIn("add_pst_state DEEP_SLEEP", upf)
            self.assertIn("constexpr bool kHasDeepSleepState = true;", header)

    def test_joules_script_generation_mentions_vcd_scope_and_libraries(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_file = Path(tmp) / "run_joules_power.tcl"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "gen_joules.py"),
                    "--scheme",
                    "dvfs_retention_domains",
                    "--schemes",
                    str(ROOT / "power_schemes"),
                    "--rtl-root",
                    str(ROOT),
                    "--vcd",
                    str(ROOT / "waves" / "mobile_cpu_power.vcd"),
                    "--upf",
                    str(ROOT / "upf" / "dvfs_retention_domains.upf"),
                    "--out",
                    str(out_file),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            script = out_file.read_text(encoding="utf-8")
            self.assertIn("set DESIGN_TOP mobile_cpu_top", script)
            self.assertIn("set VCD_DUT_INSTANCE /TOP/mobile_cpu_power_top/u_dut", script)
            self.assertIn("read_hdl -sv $RTL_FILES", script)
            self.assertIn("read_stimulus -file $VCD_FILE -dut_instance $VCD_DUT_INSTANCE", script)
            self.assertIn("JOULES_LIB_FILES", script)


class WorkloadAssemblyTest(unittest.TestCase):
    def test_default_workload_matches_builtin_rom_program(self):
        assembled = assemble(ROOT / "workloads" / "alu_idle.s")
        words = [word for _, _, word in assembled]

        self.assertEqual(
            words,
            [
                0x5101,  # ADDI r1, r0, 1
                0x5212,  # ADDI r2, r1, 2
                0x1321,  # ADD  r3, r2, r1
                0x7300,  # ST   r3, [r0 + 0]
                0x6400,  # LD   r4, [r0 + 0]
                0xF000,  # WFI
            ],
        )

    def test_workload_cli_writes_memh_and_listing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            memh = tmp_path / "memory_burst.memh"
            listing = tmp_path / "memory_burst.lst"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "asm.py"),
                    str(ROOT / "workloads" / "memory_burst.s"),
                    "--memh",
                    str(memh),
                    "--listing",
                    str(listing),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            memh_lines = memh.read_text(encoding="utf-8").splitlines()
            listing_text = listing.read_text(encoding="utf-8")
            self.assertEqual(memh_lines[0], "5101")
            self.assertEqual(memh_lines[-1], "f000")
            self.assertIn("ST   r4, [r0 + 3]", listing_text)
            self.assertIn("LD   r8, [r0 + 3]", listing_text)

    def test_dataflow_workload_uses_mmio_window(self):
        assembled = assemble(ROOT / "workloads" / "dataflow_mac.s")
        words = [word for _, _, word in assembled]

        self.assertIn(0x7606, words)  # ST r6, [r0 + 6] clears the accumulator.
        self.assertIn(0x7104, words)  # ST r1, [r0 + 4] writes operand A.
        self.assertIn(0x7205, words)  # ST r2, [r0 + 5] writes operand B.
        self.assertIn(0x6707, words)  # LD r7, [r0 + 7] reads the accumulated result.


class VerilatorPowerSimulationTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("verilator"), "Verilator is not installed")
    def test_power_sim_passes_and_negative_fixtures_fail(self):
        subprocess.run(
            ["make", "sim-power"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        binary = Path("/private/tmp/mobile_cpu_upf_power_sim_obj") / "Vmobile_cpu_power_top"
        self.assertTrue(binary.exists())
        summary = (ROOT / "reports" / "power_sim_summary.md").read_text(encoding="utf-8")
        self.assertIn("- Result: PASS", summary)

        negative_args = [
            "+power-sim-inject-illegal=1",
            "+power-sim-disable-isolation=1",
            "+power-sim-disable-retention=1",
        ]
        for arg in negative_args:
            with self.subTest(arg=arg), tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                result = subprocess.run(
                    [
                        str(binary),
                        "+power-sim-no-wave=1",
                        f"+power-sim-report={tmp_path / 'events.json'}",
                        f"+power-sim-summary={tmp_path / 'summary.md'}",
                        arg,
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue((tmp_path / "summary.md").exists())


if __name__ == "__main__":
    unittest.main()
