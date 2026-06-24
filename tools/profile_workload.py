#!/usr/bin/env python3
"""Generate architecture-efficiency metrics from workload activity and power reports."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from vcd_activity_2416 import VcdActivityExtractor


RUN_STATES = {"RUN"}
MEMORY_INSTRUCTIONS = {"LD", "ST"}
BRANCH_INSTRUCTIONS = {"BEQ"}
IDLE_INSTRUCTIONS = {"WFI"}
ALU_INSTRUCTIONS = {"ADD", "SUB", "AND", "OR", "ADDI"}


def load_activity(args: argparse.Namespace, estimate: dict | None) -> dict:
    if args.activity:
        return json.loads(args.activity.read_text(encoding="utf-8"))
    if estimate and "activity" in estimate:
        return estimate["activity"]
    if args.vcd:
        return VcdActivityExtractor(args.vcd).extract()
    raise SystemExit("Provide --activity, --estimate with embedded activity, or --vcd")


def energy_for_states(estimate: dict, states: set[str]) -> float:
    total = 0.0
    for row in estimate.get("power_timeline", []):
        if row.get("state") in states:
            total += float(row.get("total_mw", 0.0)) * float(row.get("duration_ns", 0.0))
    return total


def duration_for_states(activity: dict, states: set[str]) -> float:
    return sum(
        float(duration_ps) / 1000.0
        for state, duration_ps in activity.get("state_durations_ps", {}).items()
        if state in states
    )


def event_count(activity: dict, key: str) -> int:
    return int(activity.get("event_counts", {}).get(key, 0))


def instruction_count(activity: dict, name: str) -> int:
    return int(activity.get("instruction_counts", {}).get(name, 0))


def summarize(args: argparse.Namespace, activity: dict, estimate: dict | None) -> dict:
    instruction_counts = {
        name: int(count)
        for name, count in sorted(activity.get("instruction_counts", {}).items())
    }
    retired = int(activity.get("retired_instruction_count") or sum(instruction_counts.values()))
    duration_ns = (
        float(estimate.get("duration_ns", 0.0))
        if estimate
        else float(activity.get("duration_ps", 0.0)) / 1000.0
    )
    total_energy_pj = float(estimate.get("total_energy_pj", 0.0)) if estimate else 0.0
    total_power_mw = float(estimate.get("average_power_mw", 0.0)) if estimate else 0.0

    memory_ops = sum(instruction_count(activity, name) for name in MEMORY_INSTRUCTIONS)
    branch_ops = sum(instruction_count(activity, name) for name in BRANCH_INSTRUCTIONS)
    idle_ops = sum(instruction_count(activity, name) for name in IDLE_INSTRUCTIONS)
    alu_ops = sum(instruction_count(activity, name) for name in ALU_INSTRUCTIONS)
    useful_instructions = max(retired - instruction_count(activity, "NOP"), 0)
    dataflow_macs = event_count(activity, "dataflow_unit.mac_accumulate")
    dataflow_operand_writes = event_count(activity, "dataflow_unit.operand_write")
    dataflow_reads = event_count(activity, "dataflow_unit.result_read") + event_count(activity, "dataflow_unit.status_read")

    run_energy_pj = energy_for_states(estimate or {}, RUN_STATES)
    recovery_energy_pj = total_energy_pj - run_energy_pj if estimate else 0.0
    run_duration_ns = duration_for_states(activity, RUN_STATES)
    recovery_duration_ns = max(duration_ns - run_duration_ns, 0.0)

    metrics = {
        "workload": args.workload,
        "source_vcd": activity.get("source", ""),
        "duration_ns": duration_ns,
        "total_energy_pj": total_energy_pj,
        "average_power_mw": total_power_mw,
        "retired_instruction_count": retired,
        "useful_instruction_count": useful_instructions,
        "energy_per_instruction_pj": total_energy_pj / retired if retired and total_energy_pj else 0.0,
        "energy_per_useful_instruction_pj": total_energy_pj / useful_instructions
        if useful_instructions and total_energy_pj
        else 0.0,
        "instruction_counts": instruction_counts,
        "instruction_mix_percent": {
            name: (count / retired * 100.0) if retired else 0.0
            for name, count in instruction_counts.items()
        },
        "alu_instruction_count": alu_ops,
        "memory_instruction_count": memory_ops,
        "branch_instruction_count": branch_ops,
        "idle_instruction_count": idle_ops,
        "memory_intensity": memory_ops / retired if retired else 0.0,
        "branch_density": branch_ops / retired if retired else 0.0,
        "wfi_density": idle_ops / retired if retired else 0.0,
        "dataflow_mac_count": dataflow_macs,
        "dataflow_operand_write_count": dataflow_operand_writes,
        "dataflow_read_count": dataflow_reads,
        "energy_per_dataflow_mac_pj": total_energy_pj / dataflow_macs if dataflow_macs and total_energy_pj else 0.0,
        "run_duration_ns": run_duration_ns,
        "recovery_duration_ns": recovery_duration_ns,
        "recovery_residency_percent": recovery_duration_ns / duration_ns * 100.0 if duration_ns else 0.0,
        "run_energy_pj": run_energy_pj,
        "recovery_energy_pj": recovery_energy_pj,
        "recovery_energy_percent": recovery_energy_pj / total_energy_pj * 100.0 if total_energy_pj else 0.0,
        "state_durations_ps": activity.get("state_durations_ps", {}),
        "mode_transitions": activity.get("mode_transitions", {}),
    }
    return metrics


def write_csv(path: Path, metrics: dict) -> None:
    rows = [
        {"metric": key, "value": value}
        for key, value in metrics.items()
        if not isinstance(value, (dict, list))
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, metrics: dict) -> None:
    lines = [
        "# Workload Architecture Efficiency Profile",
        "",
        f"- Workload: `{metrics['workload']}`",
        f"- Source VCD: `{metrics['source_vcd']}`",
        f"- Duration: {metrics['duration_ns']:.3f} ns",
        f"- Total energy: {metrics['total_energy_pj']:.6f} pJ",
        f"- Average power: {metrics['average_power_mw']:.6f} mW",
        f"- Retired instructions: {metrics['retired_instruction_count']}",
        f"- Useful non-NOP instructions: {metrics['useful_instruction_count']}",
        f"- Energy per instruction: {metrics['energy_per_instruction_pj']:.6f} pJ",
        f"- Energy per useful instruction: {metrics['energy_per_useful_instruction_pj']:.6f} pJ",
        f"- Memory intensity: {metrics['memory_intensity']:.3f}",
        f"- Branch density: {metrics['branch_density']:.3f}",
        f"- WFI density: {metrics['wfi_density']:.3f}",
        f"- Recovery residency: {metrics['recovery_residency_percent']:.2f}%",
        f"- Recovery energy: {metrics['recovery_energy_pj']:.6f} pJ ({metrics['recovery_energy_percent']:.2f}%)",
        "",
        "## Dataflow Activity",
        "",
        f"- MAC operations: {metrics['dataflow_mac_count']}",
        f"- Operand writes: {metrics['dataflow_operand_write_count']}",
        f"- Result/status reads: {metrics['dataflow_read_count']}",
        f"- Energy per dataflow MAC: {metrics['energy_per_dataflow_mac_pj']:.6f} pJ",
        "",
        "## Instruction Mix",
        "",
        "| Instruction | Count | Mix (%) |",
        "| --- | ---: | ---: |",
    ]
    for name, count in sorted(metrics["instruction_counts"].items()):
        mix = metrics["instruction_mix_percent"].get(name, 0.0)
        lines.append(f"| {name} | {count} | {mix:.2f} |")

    lines.extend(["", "## Power States", "", "| State | Duration (ns) |", "| --- | ---: |"])
    for state, duration_ps in sorted(metrics["state_durations_ps"].items()):
        lines.append(f"| {state} | {float(duration_ps) / 1000.0:.3f} |")

    if metrics["mode_transitions"]:
        lines.extend(["", "## Mode Transitions", "", "| Transition | Count |", "| --- | ---: |"])
        for transition, count in sorted(metrics["mode_transitions"].items()):
            lines.append(f"| {transition} | {count} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", default="unknown")
    parser.add_argument("--estimate", type=Path)
    parser.add_argument("--activity", type=Path)
    parser.add_argument("--vcd", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    estimate = json.loads(args.estimate.read_text(encoding="utf-8")) if args.estimate else None
    activity = load_activity(args, estimate)
    metrics = summarize(args, activity, estimate)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "workload_profile.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    write_csv(args.out / "workload_profile.csv", metrics)
    write_markdown(args.out / "workload_profile.md", metrics)
    print(f"wrote {args.out / 'workload_profile.md'}")


if __name__ == "__main__":
    main()
