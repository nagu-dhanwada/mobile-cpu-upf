import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkloadGenerationTest(unittest.TestCase):
    def test_dataflow_probe_generation_and_assembly(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            out_dir = tmp_path / "workloads"
            manifest_dir = tmp_path / "manifests"
            memh = tmp_path / "dataflow_energy_probe.memh"
            listing = tmp_path / "dataflow_energy_probe.lst"

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "gen_workload.py"),
                    "--spec",
                    str(ROOT / "workload_specs" / "dataflow_energy_probe.json"),
                    "--out",
                    str(out_dir),
                    "--manifest-dir",
                    str(manifest_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            asm_path = out_dir / "dataflow_energy_probe.s"
            manifest_path = manifest_dir / "dataflow_energy_probe" / "workload_intent.json"
            self.assertTrue(asm_path.exists())
            self.assertTrue(manifest_path.exists())

            assembly = asm_path.read_text(encoding="utf-8")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("ST   r1, [r0 + 4]", assembly)
            self.assertIn("LD   r7, [r0 + 7]", assembly)
            self.assertEqual(manifest["resolved_intent"]["profile"], "dataflow_heavy")
            self.assertEqual(manifest["category_counts"]["dataflow_mmio_access"], 14)
            self.assertEqual(manifest["instruction_count"], 38)

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "asm.py"),
                    str(asm_path),
                    "--memh",
                    str(memh),
                    "--listing",
                    str(listing),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(len(memh.read_text(encoding="utf-8").splitlines()), 38)
            self.assertIn("f000", memh.read_text(encoding="utf-8"))

    def test_generation_rejects_programs_that_exceed_rom_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            spec = tmp_path / "too_large.json"
            spec.write_text(
                json.dumps(
                    {
                        "name": "too_large",
                        "intent": {
                            "profile": "dataflow_heavy",
                            "dataflow_macs": 20,
                        },
                        "max_instructions": 64,
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "gen_workload.py"),
                    "--spec",
                    str(spec),
                    "--out",
                    str(tmp_path / "out"),
                    "--manifest-dir",
                    str(tmp_path / "manifest"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exceeding max_instructions", result.stderr)

    def test_generation_rejects_expected_name_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            spec = tmp_path / "renamed.json"
            spec.write_text(
                json.dumps(
                    {
                        "name": "inside_name",
                        "intent": {
                            "profile": "mixed_mobile",
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "gen_workload.py"),
                    "--spec",
                    str(spec),
                    "--out",
                    str(tmp_path / "out"),
                    "--manifest-dir",
                    str(tmp_path / "manifest"),
                    "--expected-name",
                    "outside_name",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not match GEN_WORKLOAD", result.stderr)


if __name__ == "__main__":
    unittest.main()
