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
            {"domain": "PD_AON", "total_pj": energy * 0.10, "average_mw": energy * 0.01},
            {"domain": "PD_CPU", "total_pj": energy * 0.75, "average_mw": energy * 0.075},
            {"domain": "PD_MEM", "total_pj": energy * 0.15, "average_mw": energy * 0.015},
        ],
        "blocks": [
            {"block": "load_store_unit", "domain": "PD_CPU", "total_pj": energy * 0.10, "average_mw": 0.1},
            {"block": "dataflow_unit", "domain": "PD_CPU", "total_pj": energy * 0.12, "average_mw": 0.1},
        ],
        "activity": {
            "clock_cycles": {"core": 80, "mem": 80, "top": 90},
            "lsu_latency_cycles": [2, 3, 2],
            "event_counts": {
                "data_bus_interconnect.address_decode": 12,
                "data_bus_interconnect.mmio_route": 10,
                "data_bus_interconnect.sram_route": 2,
                "dataflow_unit.operand_write": 4,
                "dataflow_unit.command_write": 4,
                "dataflow_unit.result_read": 2,
                "dataflow_unit.mac_accumulate": 2,
                "dataflow_unit.mac_active_cycle": 2,
                "dataflow_unit.idle_cycle": 60,
                "dataflow_unit.busy_cycle": 2,
                "dataflow_unit.ctrl_ce_cycle": 12,
                "dataflow_unit.mac_ce_cycle": 2,
                "dataflow_unit.done_assert": 2,
                "load_store_unit.request_issue": 12,
                "load_store_unit.response_complete": 12,
                "load_store_unit.stall_cycle": 40,
                "fetch_unit.fetch_valid_cycle": 80,
                "fetch_unit.fetch_ce_cycle": 40,
                "fetch_unit.stall_valid_cycle": 40,
                "decode_unit.decode_valid_cycle": 80,
                "decode_unit.decode_ce_cycle": 40,
                "decode_unit.stall_valid_cycle": 40,
                "execute_unit.execute_valid_cycle": 80,
                "execute_unit.execute_ce_cycle": 40,
                "execute_unit.stall_valid_cycle": 40,
                "instr_rom.stall_hold_cycle": 40,
                "power_controller.mode_transition": 2,
            },
        },
    }
    profile = {
        "workload": workload,
        "duration_ns": 10.0,
        "total_energy_pj": energy,
        "average_power_mw": energy / 10.0,
        "retired_instruction_count": 20,
        "useful_instruction_count": 18,
        "memory_intensity": 0.6,
        "wfi_density": 0.05,
        "recovery_energy_percent": 10.0,
        "dataflow_mac_count": 2,
        "instruction_counts": {"ADDI": 4, "LD": 2, "ST": 8, "WFI": 1},
    }
    (out / "2416_power_estimate.json").write_text(json.dumps(estimate), encoding="utf-8")
    (profile_dir / "workload_profile.json").write_text(json.dumps(profile), encoding="utf-8")


class PowerCheckTest(unittest.TestCase):
    def test_power_check_generates_metrics_delta_and_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "reports" / "2416"
            write_case(report_root, "dataflow_mac", "generic_7nm", "clock_gated_idle", 50.0)

            metrics = tmp_path / "power_metrics.json"
            delta = tmp_path / "power_metrics_delta.json"
            cards = tmp_path / "power_optimization_cards.json"
            summary = tmp_path / "checkin_summary.md"

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "power_check.py"),
                    "check",
                    "--report-root",
                    str(report_root),
                    "--config",
                    str(ROOT / "power_check_config.json"),
                    "--hierarchy-map",
                    str(ROOT / "power_hierarchy_map.json"),
                    "--tech",
                    "generic_7nm",
                    "--scheme",
                    "clock_gated_idle",
                    "--workload",
                    "dataflow_mac",
                    "--out",
                    str(metrics),
                    "--delta-out",
                    str(delta),
                    "--cards-out",
                    str(cards),
                    "--summary-out",
                    str(summary),
                    "--baseline",
                    str(tmp_path / "missing_baseline.json"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            metrics_data = json.loads(metrics.read_text(encoding="utf-8"))
            delta_data = json.loads(delta.read_text(encoding="utf-8"))
            card_data = json.loads(cards.read_text(encoding="utf-8"))

            self.assertEqual(metrics_data["workload_count"], 1)
            self.assertEqual(delta_data["status"], "no_baseline")
            self.assertTrue(metrics_data["events"])
            self.assertTrue(metrics_data["hierarchy_rollup"])
            self.assertTrue(card_data)
            self.assertIn("rtl_hierarchy", card_data[0])
            self.assertIn("triggering_metric", card_data[0])
            self.assertIn("likely_control_signal_or_fsm", card_data[0])
            self.assertIn("blocking_status", card_data[0])
            self.assertIn("Power Methodology Summary", summary.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
