#!/usr/bin/env python3
"""Generate a toy CPU assembly workload from a high-level intent spec."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from workloadgen.generate import generate_workload
from workloadgen.ir import intent_from_spec


def load_spec(path: Path) -> dict:
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise SystemExit(
                "YAML specs require PyYAML. Use JSON specs or install PyYAML."
            ) from exc
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Workload spec must decode to an object")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True, help="JSON workload intent spec")
    parser.add_argument("--out", type=Path, default=Path("workloads/generated"))
    parser.add_argument("--manifest-dir", type=Path, default=Path("build/workloadgen"))
    parser.add_argument(
        "--expected-name",
        help="Fail if the generated workload name does not match this value.",
    )
    parser.add_argument(
        "--print-workload",
        action="store_true",
        help="Print the generated workload name for scripts.",
    )
    args = parser.parse_args()

    try:
        intent = intent_from_spec(load_spec(args.spec))
        generated = generate_workload(intent)
    except Exception as exc:
        raise SystemExit(f"{args.spec}: {exc}") from exc

    if args.expected_name and generated.name != args.expected_name:
        raise SystemExit(
            f"{args.spec}: workload spec name {generated.name!r} does not match "
            f"GEN_WORKLOAD={args.expected_name!r}. Update the JSON 'name' field "
            "or call make with the matching GEN_WORKLOAD value."
        )

    asm_path = args.out / f"{generated.name}.s"
    manifest_path = args.manifest_dir / generated.name / "workload_intent.json"

    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    asm_path.write_text(generated.assembly, encoding="utf-8")
    manifest_path.write_text(json.dumps(generated.summary, indent=2) + "\n", encoding="utf-8")

    if args.print_workload:
        sys.stdout.write(f"{generated.name}\n")
    else:
        print(f"generated {asm_path}")
        print(f"wrote {manifest_path}")


if __name__ == "__main__":
    main()
