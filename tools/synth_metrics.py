#!/usr/bin/env python3
"""Extract block-level synthesis metrics from a Yosys JSON netlist."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


BLOCK_MODULES = {
    "fetch_unit": "fetch_unit",
    "instr_rom": "instr_rom",
    "decode_unit": "decode_unit",
    "regfile": "regfile",
    "execute_unit": "execute_unit",
    "data_sram": "data_sram",
    "power_controller": "power_controller",
}


def is_sequential_cell(cell_type: str) -> bool:
    upper = cell_type.upper()
    return "DFF" in upper or "SDFF" in upper or "ADFF" in upper or "DFFE" in upper


def is_latch_cell(cell_type: str) -> bool:
    upper = cell_type.upper()
    return "LATCH" in upper or "DLATCH" in upper


def is_memory_cell(cell_type: str) -> bool:
    lower = cell_type.lower()
    return "$mem" in lower or "memory" in lower or "sram" in lower


def estimated_equivalent_gates(combinational: int, sequential: int, latches: int, memory: int) -> float:
    return combinational + 4.0 * sequential + 2.0 * latches + 8.0 * memory


def module_metrics(module_name: str, module: dict) -> dict:
    cell_types: dict[str, int] = {}
    sequential = 0
    latches = 0
    memory = 0
    submodule_instances = 0
    cells = module.get("cells", {})

    for cell in cells.values():
        cell_type = str(cell.get("type", ""))
        cell_types[cell_type] = cell_types.get(cell_type, 0) + 1
        if cell_type in BLOCK_MODULES.values():
            submodule_instances += 1
        elif is_sequential_cell(cell_type):
            sequential += 1
        elif is_latch_cell(cell_type):
            latches += 1
        elif is_memory_cell(cell_type):
            memory += 1

    total = len(cells)
    combinational = max(total - sequential - latches - memory - submodule_instances, 0)
    eq_gates = estimated_equivalent_gates(combinational, sequential, latches, memory)
    return {
        "module": module_name,
        "cell_count": total,
        "combinational_cells": combinational,
        "sequential_cells": sequential,
        "latch_cells": latches,
        "memory_cells": memory,
        "submodule_instances": submodule_instances,
        "estimated_equivalent_gates": eq_gates,
        "cell_types": dict(sorted(cell_types.items())),
    }


def extract_metrics(yosys_json: dict, source: str = "", workload: str = "") -> dict:
    modules = yosys_json.get("modules", {})
    blocks = {}
    totals = {
        "cell_count": 0,
        "combinational_cells": 0,
        "sequential_cells": 0,
        "latch_cells": 0,
        "memory_cells": 0,
        "estimated_equivalent_gates": 0.0,
    }

    for block, module_name in BLOCK_MODULES.items():
        module = modules.get(module_name)
        if module is None:
            blocks[block] = {
                "module": module_name,
                "missing": True,
                "cell_count": 0,
                "combinational_cells": 0,
                "sequential_cells": 0,
                "latch_cells": 0,
                "memory_cells": 0,
                "submodule_instances": 0,
                "estimated_equivalent_gates": 0.0,
                "cell_types": {},
            }
            continue

        row = module_metrics(module_name, module)
        row["missing"] = False
        blocks[block] = row
        for key in totals:
            totals[key] += row[key]

    return {
        "source": source,
        "workload": workload,
        "generator": "tools/synth_metrics.py",
        "blocks": blocks,
        "totals": totals,
    }


def write_summary(metrics: dict, path: Path) -> None:
    lines = [
        "# Synthesis Metrics",
        "",
        f"- Source: `{metrics.get('source', '')}`",
        f"- Workload: `{metrics.get('workload', '')}`",
        "",
        "| Block | Module | Cells | Comb | Seq | Latch | Mem | Eq Gates |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for block, row in sorted(metrics["blocks"].items()):
        lines.append(
            f"| {block} | {row['module']} | {row['cell_count']} | "
            f"{row['combinational_cells']} | {row['sequential_cells']} | "
            f"{row['latch_cells']} | {row['memory_cells']} | "
            f"{row['estimated_equivalent_gates']:.1f} |"
        )
    totals = metrics["totals"]
    lines.extend(
        [
            "",
            "## Totals",
            "",
            f"- Cells: {totals['cell_count']}",
            f"- Combinational cells: {totals['combinational_cells']}",
            f"- Sequential cells: {totals['sequential_cells']}",
            f"- Latch cells: {totals['latch_cells']}",
            f"- Memory cells: {totals['memory_cells']}",
            f"- Estimated equivalent gates: {totals['estimated_equivalent_gates']:.1f}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--workload", default="")
    args = parser.parse_args()

    yosys_json = json.loads(args.json.read_text(encoding="utf-8"))
    metrics = extract_metrics(yosys_json, source=str(args.json), workload=args.workload)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        write_summary(metrics, args.summary)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
