import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def write_case(report_root: Path, workload: str, tech: str, scheme: str, energy: float) -> None:
    out = report_root / f"{workload}_{tech}_{scheme}"
    profile_dir = out / "workload_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    estimate = {
        "technology": tech,
        "scheme": scheme,
        "source_vcd": f"waves/{workload}.vcd",
        "duration_ns": 10.0,
        "total_energy_pj": energy,
        "average_power_mw": energy / 10.0,
        "domains": [
            {"domain": "PD_AON", "total_pj": energy * 0.20, "average_mw": energy * 0.02},
            {"domain": "PD_CPU", "total_pj": energy * 0.65, "average_mw": energy * 0.065},
            {"domain": "PD_MEM", "total_pj": energy * 0.15, "average_mw": energy * 0.015},
        ],
        "activity": {
            "event_counts": {
                "data_bus_interconnect.mmio_route": 8,
                "fetch_unit.pc_update": 6,
                "fetch_unit.fetch_ce_cycle": 12,
                "fetch_unit.stall_valid_cycle": 4,
                "decode_unit.decode_ce_cycle": 12,
                "decode_unit.stall_valid_cycle": 4,
                "execute_unit.execute_ce_cycle": 12,
                "execute_unit.stall_valid_cycle": 4,
                "instr_rom.stall_hold_cycle": 4,
                "execute_unit.alu_add": 3,
                "dataflow_unit.mac_accumulate": 2,
                "dataflow_unit.operand_write": 4,
                "dataflow_unit.command_write": 2,
                "dataflow_unit.result_read": 1,
                "dataflow_unit.busy_cycle": 2,
                "dataflow_unit.idle_cycle": 40,
                "dataflow_unit.mac_active_cycle": 2,
                "dataflow_unit.ctrl_ce_cycle": 8,
                "dataflow_unit.mac_ce_cycle": 2,
                "load_store_unit.request_issue": 8,
                "load_store_unit.response_complete": 8,
                "load_store_unit.stall_cycle": 24,
            }
        },
        "power_timeline": [
            {
                "start_ns": 0.0,
                "end_ns": 5.0,
                "duration_ns": 5.0,
                "state": "RUN",
                "dvfs": "1",
                "PD_AON_mw": 0.1,
                "PD_CPU_mw": 0.6,
                "PD_MEM_mw": 0.2,
                "total_mw": 0.9,
            },
            {
                "start_ns": 5.0,
                "end_ns": 10.0,
                "duration_ns": 5.0,
                "state": "IDLE",
                "dvfs": "0",
                "PD_AON_mw": 0.1,
                "PD_CPU_mw": 0.1,
                "PD_MEM_mw": 0.0,
                "total_mw": 0.2,
            },
        ],
    }
    profile = {
        "workload": workload,
        "duration_ns": 10.0,
        "total_energy_pj": energy,
        "average_power_mw": energy / 10.0,
        "retired_instruction_count": 8,
        "useful_instruction_count": 7,
        "energy_per_useful_instruction_pj": energy / 7.0,
        "memory_intensity": 0.25,
        "wfi_density": 0.125,
        "recovery_energy_percent": 12.5,
        "dataflow_mac_count": 2,
        "instruction_counts": {"ADD": 3, "ADDI": 2, "LD": 1, "ST": 1, "WFI": 1},
    }
    (out / "2416_power_estimate.json").write_text(json.dumps(estimate), encoding="utf-8")
    (profile_dir / "workload_profile.json").write_text(json.dumps(profile), encoding="utf-8")


class VisualStoryTest(unittest.TestCase):
    def test_visual_story_handles_regular_and_generated_workloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "reports" / "2416"
            intent_root = tmp_path / "build" / "workloadgen"
            scheme_root = tmp_path / "power_schemes"
            out = tmp_path / "visual" / "index.html"
            scheme_root.mkdir(parents=True)
            (scheme_root / "04_dvfs_retention_domains.json").write_text(
                json.dumps(
                    {
                        "name": "dvfs_retention_domains",
                        "description": "Fixture scheme",
                        "domains": [{"name": "PD_AON"}, {"name": "PD_CPU"}, {"name": "PD_MEM"}],
                        "power_states": [{"name": "RUN"}, {"name": "IDLE"}],
                        "methodology": {
                            "gated_in_rtl": ["fixture RTL behavior"],
                            "estimated_behavior": ["fixture estimated behavior"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            write_case(report_root, "cpu_mac", "generic_7nm", "dvfs_retention_domains", 21.0)
            write_case(report_root, "generated/generated_probe", "generic_7nm", "dvfs_retention_domains", 34.0)
            (intent_root / "generated_probe").mkdir(parents=True)
            (intent_root / "generated_probe" / "workload_intent.json").write_text(
                json.dumps({"resolved_intent": {"profile": "dataflow_heavy"}}),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "gen_visual_story.py"),
                    "--report-root",
                    str(report_root),
                    "--intent-root",
                    str(intent_root),
                    "--scheme-root",
                    str(scheme_root),
                    "--tech",
                    "generic_7nm",
                    "--scheme",
                    "dvfs_retention_domains",
                    "--out",
                    str(out),
                    "--workload",
                    "cpu_mac",
                    "--workload",
                    "generated/generated_probe",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            html = out.read_text(encoding="utf-8")
            self.assertIn("Mobile CPU Visual Power Story", html)
            self.assertIn("How The CPU Moves Work", html)
            self.assertIn("timeline-cursor", html)
            self.assertIn("Workload Cards", html)
            self.assertIn("Designer Optimization Cards", html)
            self.assertIn("Power Tradeoffs", html)
            self.assertIn("fixture RTL behavior", html)
            self.assertIn("generated_probe", html)
            self.assertIn("dataflow_heavy", html)
            self.assertNotIn("http://", html)
            self.assertNotIn("https://", html)
            cards = json.loads((out.parent / "power_optimization_cards.json").read_text(encoding="utf-8"))
            self.assertTrue(cards)
            self.assertIn("card_id", cards[0])
            self.assertIn("suggested_design_change", cards[0])

    def test_missing_optional_intent_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "reports" / "2416"
            out = tmp_path / "visual" / "index.html"
            write_case(report_root, "generated/no_intent", "generic_7nm", "dvfs_retention_domains", 11.0)

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "gen_visual_story.py"),
                    "--report-root",
                    str(report_root),
                    "--intent-root",
                    str(tmp_path / "missing_intents"),
                    "--scheme-root",
                    str(tmp_path / "missing_schemes"),
                    "--tech",
                    "generic_7nm",
                    "--scheme",
                    "dvfs_retention_domains",
                    "--out",
                    str(out),
                    "--workload",
                    "generated/no_intent",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            html = out.read_text(encoding="utf-8")
            self.assertIn("no_intent", html)
            self.assertIn("hand-written", html)
            self.assertTrue((out.parent / "power_optimization_cards.json").exists())


if __name__ == "__main__":
    unittest.main()
