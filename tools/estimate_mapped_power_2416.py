#!/usr/bin/env python3
"""Estimate mapped-netlist power from 2416 cell/macro models and VCD activity."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from estimate_power_2416 import (
    DOMAIN_COLORS,
    DOMAIN_ORDER,
    STATE_COLORS,
    apply_scheme_profile,
    domain_voltage,
    normalize_activity_time,
    voltage_scale,
    xml_escape,
)
from vcd_activity_2416 import VcdActivityExtractor, hamming, parse_timescale_ps


BLOCK_DOMAINS = {
    "fetch_unit": "PD_CPU",
    "instr_rom": "PD_CPU",
    "decode_unit": "PD_CPU",
    "regfile": "PD_CPU",
    "execute_unit": "PD_CPU",
    "data_sram": "PD_MEM",
    "power_controller": "PD_AON",
}

BLOCK_CLOCKS = {
    "fetch_unit": "core",
    "instr_rom": "none",
    "decode_unit": "none",
    "regfile": "core",
    "execute_unit": "none",
    "data_sram": "mem",
    "power_controller": "top",
}

GATE_BLOCK_PATHS = {
    "fetch_unit": "TOP.mobile_cpu_top.u_fetch",
    "instr_rom": "TOP.mobile_cpu_top.u_icache",
    "decode_unit": "TOP.mobile_cpu_top.u_decode",
    "regfile": "TOP.mobile_cpu_top.u_regfile",
    "execute_unit": "TOP.mobile_cpu_top.u_execute",
    "data_sram": "TOP.mobile_cpu_top.u_dmem",
    "power_controller": "TOP.mobile_cpu_top.u_power_controller",
}


def parse_gate_vcd_toggles(path: Path) -> dict:
    timescale_ps = 1.0
    header_done = False
    scope: list[str] = []
    code_to_paths: dict[str, list[str]] = defaultdict(list)
    values: dict[str, str] = {}
    block_toggles: dict[str, int] = defaultdict(int)
    current_time = 0

    def parse_change(line: str) -> tuple[str, str] | None:
        if not line:
            return None
        if line[0] in "01xXzZ":
            return line[1:], line[0].lower()
        if line[0] in "bBrR":
            parts = line.split()
            if len(parts) == 2:
                return parts[1], parts[0][1:].lower()
        return None

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not header_done:
            if line.startswith("$timescale"):
                timescale_ps = parse_timescale_ps(line)
            elif line.startswith("$scope"):
                parts = line.split()
                if len(parts) >= 3:
                    scope.append(parts[2])
            elif line.startswith("$upscope"):
                if scope:
                    scope.pop()
            elif line.startswith("$var"):
                parts = line.split()
                if len(parts) >= 5:
                    code_to_paths[parts[3]].append(".".join(scope + [parts[4]]))
            elif line.startswith("$enddefinitions"):
                header_done = True
            continue

        if line.startswith("#"):
            current_time = int(line[1:])
            continue

        change = parse_change(line)
        if not change:
            continue
        code, new_value = change
        old_value = values.get(code)
        values[code] = new_value
        count = hamming(old_value, new_value)
        if count == 0:
            continue
        paths = code_to_paths.get(code, [])
        for block, prefix in GATE_BLOCK_PATHS.items():
            if any(item.startswith(prefix) for item in paths):
                block_toggles[block] += count

    return {
        "source": str(path),
        "timescale_ps": timescale_ps,
        "duration_ps": current_time * timescale_ps,
        "block_toggles": dict(sorted(block_toggles.items())),
    }


def load_activity(args: argparse.Namespace, tech: dict) -> dict:
    if args.activity:
        activity = json.loads(args.activity.read_text(encoding="utf-8"))
    elif args.rtl_vcd:
        activity = VcdActivityExtractor(args.rtl_vcd).extract()
    else:
        raise SystemExit("Either --activity or --rtl-vcd is required for mapped power estimation")
    return apply_scheme_profile(normalize_activity_time(activity, tech), args.scheme)


def weighted_dynamic_scale(activity: dict, tech: dict, domain: str, reference_v: float) -> float:
    durations = activity.get("dvfs_durations_ps", {})
    total = sum(float(duration) for duration in durations.values())
    if total <= 0.0:
        return 1.0
    weighted = 0.0
    for dvfs, duration in durations.items():
        voltage = domain_voltage(tech, domain, dvfs)
        weighted += float(duration) * voltage_scale(voltage, reference_v, 2.0)
    return weighted / total


def leakage_energy(leakage_mw: float, domain: str, activity: dict, tech: dict, reference_v: float) -> float:
    total = 0.0
    for state, duration_ps in activity.get("state_durations_ps", {}).items():
        if domain == "PD_AON":
            state_factor = 1.0 if state in {"RUN", "WAKE"} else 0.82
        elif state == "DEEP_SLEEP":
            state_factor = 0.02
        elif state == "LIGHT_SLEEP":
            state_factor = 0.35
        elif state == "IDLE":
            state_factor = 0.82
        else:
            state_factor = 1.0
        voltage = domain_voltage(tech, domain, 1, state=state)
        total += leakage_mw * state_factor * voltage_scale(voltage, reference_v, 1.2) * (float(duration_ps) / 1000.0)
    return total


def cell_count_for_block(block_metrics: dict, cell_lib: dict) -> tuple[int, int, float, float, float]:
    cells = cell_lib["cells"]
    total = 0
    sequential = 0
    leakage_mw = 0.0
    switching_sum = 0.0
    clock_sum = 0.0
    for cell_name, count in block_metrics.get("cell_types", {}).items():
        cell = cells.get(cell_name)
        if not cell:
            continue
        count = int(count)
        total += count
        leakage_mw += count * float(cell["leakage_mw"])
        switching_sum += count * float(cell["switching_energy_pj"])
        if cell.get("is_sequential"):
            sequential += count
            clock_sum += count * max(float(cell["switching_energy_pj"]) * 0.35, 0.000001)
    avg_switching = switching_sum / total if total else 0.0
    return total, sequential, leakage_mw, avg_switching, clock_sum


def memory_macro_energy(macro: dict, activity: dict, tech: dict, reference_v: float) -> dict:
    domain = macro["powerDomain"]
    leakage_pj = leakage_energy(float(macro["leakage_mw"]), domain, activity, tech, reference_v)
    event_pj = 0.0
    event_counts: dict[str, int] = {}
    dyn_scale = weighted_dynamic_scale(activity, tech, domain, reference_v)
    for event_name, event in macro["events"].items():
        key = f"{macro['block']}.{event_name}"
        count = sum(int(value) for value in activity.get("event_counts_by_dvfs", {}).get(key, {}).values())
        event_counts[event_name] = count
        event_pj += count * float(event["energy_pj"]) * dyn_scale
    clock_pj = 0.0
    if macro["clock"] != "none":
        cycles = sum(int(value) for value in activity.get("clock_cycles_by_dvfs", {}).get(macro["clock"], {}).values())
        clock_pj = cycles * 0.010 * dyn_scale
    return {
        "block": macro["block"],
        "module": macro["module"],
        "domain": domain,
        "kind": "memory_macro",
        "cell_count": 1,
        "sequential_cells": 0,
        "gate_toggles": 0,
        "leakage_pj": leakage_pj,
        "clock_pj": clock_pj,
        "event_pj": event_pj,
        "toggle_pj": 0.0,
        "total_pj": leakage_pj + clock_pj + event_pj,
        "event_counts": event_counts,
    }


def estimate(metrics: dict, cell_lib: dict, macros: dict, gate_activity: dict, activity: dict, tech: dict) -> dict:
    reference_v = float(cell_lib.get("nominal_voltage_v", 1.0))
    duration_ns = float(activity.get("duration_ps", 0.0)) / 1000.0
    blocks: list[dict] = []
    by_domain: dict[str, dict[str, float]] = {}

    for block, row in metrics.get("blocks", {}).items():
        if block in macros:
            continue
        domain = BLOCK_DOMAINS.get(block, "PD_CPU")
        clock = BLOCK_CLOCKS.get(block, "none")
        total_cells, seq_cells, leakage_mw, avg_switching_pj, clock_sum_pj = cell_count_for_block(row, cell_lib)
        toggles = int(gate_activity.get("block_toggles", {}).get(block, 0))
        dyn_scale = weighted_dynamic_scale(activity, tech, domain, reference_v)
        leakage_pj = leakage_energy(leakage_mw, domain, activity, tech, reference_v)
        toggle_pj = toggles * avg_switching_pj * dyn_scale
        clock_pj = 0.0
        if clock != "none":
            cycles = sum(int(value) for value in activity.get("clock_cycles_by_dvfs", {}).get(clock, {}).values())
            clock_pj = cycles * clock_sum_pj * dyn_scale
        blocks.append(
            {
                "block": block,
                "module": row.get("module", block),
                "domain": domain,
                "kind": "stdcell_mapped_logic",
                "cell_count": total_cells,
                "sequential_cells": seq_cells,
                "gate_toggles": toggles,
                "avg_cell_switching_pj": avg_switching_pj,
                "leakage_pj": leakage_pj,
                "clock_pj": clock_pj,
                "event_pj": 0.0,
                "toggle_pj": toggle_pj,
                "total_pj": leakage_pj + clock_pj + toggle_pj,
            }
        )

    for macro in macros.values():
        blocks.append(memory_macro_energy(macro, activity, tech, reference_v))

    for block_row in blocks:
        block_row["average_mw"] = block_row["total_pj"] / duration_ns if duration_ns > 0 else 0.0
        domain_row = by_domain.setdefault(
            block_row["domain"],
            {"leakage_pj": 0.0, "clock_pj": 0.0, "event_pj": 0.0, "toggle_pj": 0.0, "total_pj": 0.0},
        )
        for key in ("leakage_pj", "clock_pj", "event_pj", "toggle_pj", "total_pj"):
            domain_row[key] += block_row[key]

    total_energy_pj = sum(row["total_pj"] for row in blocks)
    result = {
        "source_vcd": gate_activity["source"],
        "rtl_activity_source": activity.get("source", ""),
        "technology": tech["name"],
        "technology_library": Path(cell_lib["source"]).parent.name,
        "scheme": activity.get("scheme", "dvfs_retention_domains"),
        "duration_ns": duration_ns,
        "total_energy_pj": total_energy_pj,
        "average_power_mw": total_energy_pj / duration_ns if duration_ns > 0 else 0.0,
        "blocks": sorted(blocks, key=lambda row: row["total_pj"], reverse=True),
        "domains": [
            {"domain": domain, **values, "average_mw": values["total_pj"] / duration_ns if duration_ns > 0 else 0.0}
            for domain, values in sorted(by_domain.items())
        ],
        "activity": activity,
        "gate_activity": gate_activity,
    }
    result["power_timeline"] = build_timeline(result, activity)
    return result


def domain_active(domain: str, state: str) -> bool:
    if domain == "PD_AON":
        return True
    return state in {"RUN", "WAKE"}


def build_timeline(result: dict, activity: dict) -> list[dict]:
    timeline = activity.get("state_timeline", [])
    if not timeline:
        return []
    domain_totals = {row["domain"]: row for row in result["domains"]}
    dynamic_by_domain = {
        domain: domain_totals.get(domain, {}).get("clock_pj", 0.0)
        + domain_totals.get(domain, {}).get("event_pj", 0.0)
        + domain_totals.get(domain, {}).get("toggle_pj", 0.0)
        for domain in DOMAIN_ORDER
    }
    active_duration_ns = {domain: 0.0 for domain in DOMAIN_ORDER}
    for segment in timeline:
        state = segment["state"]
        duration_ns = float(segment["duration_ps"]) / 1000.0
        for domain in DOMAIN_ORDER:
            if domain_active(domain, state):
                active_duration_ns[domain] += duration_ns

    rows = []
    for segment in timeline:
        row = {
            "start_ns": float(segment["start_ps"]) / 1000.0,
            "end_ns": float(segment["end_ps"]) / 1000.0,
            "duration_ns": float(segment["duration_ps"]) / 1000.0,
            "state": segment["state"],
            "dvfs": segment.get("dvfs", "1"),
        }
        total = 0.0
        for domain in DOMAIN_ORDER:
            leakage_mw = domain_totals.get(domain, {}).get("leakage_pj", 0.0) / result["duration_ns"] if result["duration_ns"] else 0.0
            dynamic_mw = (
                dynamic_by_domain[domain] / active_duration_ns[domain]
                if active_duration_ns[domain] > 0.0 and domain_active(domain, segment["state"])
                else 0.0
            )
            row[f"{domain}_mw"] = leakage_mw + dynamic_mw
            total += row[f"{domain}_mw"]
        row["total_mw"] = total
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_bar_svg(result: dict, path: Path) -> None:
    rows = result["blocks"]
    width = 980
    row_h = 30
    left = 190
    top = 54
    height = top + len(rows) * row_h + 36
    max_energy = max((float(row["total_pj"]) for row in rows), default=1.0) or 1.0
    plot_w = width - left - 48
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        '<text x="24" y="28" font-family="Arial" font-size="18" font-weight="700">IEEE 2416 Mapped Energy By Block</text>',
        f'<text x="24" y="44" font-family="Arial" font-size="12" fill="#555">{xml_escape(result["technology"])} / {xml_escape(result["scheme"])}</text>',
    ]
    for idx, row in enumerate(rows):
        y = top + idx * row_h
        value = float(row["total_pj"])
        bar_w = value / max_energy * plot_w
        color = DOMAIN_COLORS.get(row["domain"], "#4c78a8")
        lines.append(f'<text x="{left - 10}" y="{y + 18}" text-anchor="end" font-family="Arial" font-size="12" fill="#333">{xml_escape(row["block"])}</text>')
        lines.append(f'<rect x="{left}" y="{y + 5}" width="{bar_w:.2f}" height="18" fill="{color}" opacity="0.84"/>')
        lines.append(f'<text x="{left + bar_w + 6:.2f}" y="{y + 18}" font-family="Arial" font-size="11" fill="#555">{value:.4f}</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_timeline_svg(result: dict, path: Path) -> None:
    timeline = result.get("power_timeline", [])
    if not timeline:
        return
    width = 1100
    height = 430
    left = 72
    top = 42
    plot_w = width - left - 26
    plot_h = 280
    duration = max(float(row["end_ns"]) for row in timeline) or 1.0
    max_power = max(float(row["total_mw"]) for row in timeline) * 1.15 or 1.0

    def x(value: float) -> float:
        return left + value / duration * plot_w

    def y(value: float) -> float:
        return top + plot_h - value / max_power * plot_h

    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="430" viewBox="0 0 1100 430">',
        '<rect width="1100" height="430" fill="#ffffff"/>',
        f'<text x="{left}" y="24" font-family="Arial" font-size="18" font-weight="700">IEEE 2416 Mapped Power Timeline</text>',
        f'<text x="{left}" y="39" font-family="Arial" font-size="12" fill="#555">Average {result["average_power_mw"]:.4f} mW, energy {result["total_energy_pj"]:.4f} pJ</text>',
    ]
    for idx in range(5):
        value = max_power * idx / 4
        yy = y(value)
        lines.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{left + plot_w}" y2="{yy:.2f}" stroke="#e4e7eb"/>')
        lines.append(f'<text x="{left - 8}" y="{yy + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11" fill="#555">{value:.2f}</text>')
    for row in timeline:
        x0 = x(float(row["start_ns"]))
        x1 = x(float(row["end_ns"]))
        base = 0.0
        for domain in DOMAIN_ORDER:
            value = float(row.get(f"{domain}_mw", 0.0))
            y0 = y(base)
            y1 = y(base + value)
            lines.append(
                f'<rect x="{x0:.2f}" y="{y1:.2f}" width="{max(x1 - x0, 0.6):.2f}" height="{max(y0 - y1, 0.0):.2f}" '
                f'fill="{DOMAIN_COLORS[domain]}" opacity="0.82"/>'
            )
            base += value
    band_y = top + plot_h + 32
    for row in timeline:
        lines.append(
            f'<rect x="{x(float(row["start_ns"])):.2f}" y="{band_y}" '
            f'width="{max(x(float(row["end_ns"])) - x(float(row["start_ns"])), 0.6):.2f}" '
            f'height="24" fill="{STATE_COLORS.get(row["state"], "#f4f4f4")}" stroke="#fff"/>'
        )
    lines.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#222"/>')
    lines.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#222"/>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_reports(result: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "2416_power_estimate.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (out_dir / "2416_mapped_gate_activity.json").write_text(json.dumps(result["gate_activity"], indent=2) + "\n", encoding="utf-8")
    write_csv(
        out_dir / "2416_power_by_block.csv",
        result["blocks"],
        [
            "block",
            "module",
            "domain",
            "kind",
            "cell_count",
            "sequential_cells",
            "gate_toggles",
            "leakage_pj",
            "clock_pj",
            "event_pj",
            "toggle_pj",
            "total_pj",
            "average_mw",
        ],
    )
    write_csv(
        out_dir / "2416_power_by_domain.csv",
        result["domains"],
        ["domain", "leakage_pj", "clock_pj", "event_pj", "toggle_pj", "total_pj", "average_mw"],
    )
    write_csv(
        out_dir / "2416_power_waveform.csv",
        result["power_timeline"],
        ["start_ns", "end_ns", "duration_ns", "state", "dvfs", "PD_AON_mw", "PD_CPU_mw", "PD_MEM_mw", "total_mw"],
    )
    write_bar_svg(result, out_dir / "2416_power_by_block.svg")
    write_timeline_svg(result, out_dir / "2416_power_waveform.svg")

    lines = [
        "# IEEE 2416 Mapped Power Estimate",
        "",
        f"- Technology profile: `{result['technology']}`",
        f"- Mapped VCD: `{result['source_vcd']}`",
        f"- RTL activity source: `{result['rtl_activity_source']}`",
        f"- Scheme profile: `{result['scheme']}`",
        f"- Duration: {result['duration_ns']:.3f} ns",
        f"- Total energy: {result['total_energy_pj']:.6f} pJ",
        f"- Average power: {result['average_power_mw']:.6f} mW",
        "",
        "This report combines standard-cell counts from the mapped netlist, gate-level VCD toggles, "
        "and memory macro transaction events from the RTL activity trace.",
        "",
        "## Power By Domain",
        "",
        "| Domain | Energy (pJ) | Average Power (mW) |",
        "| --- | ---: | ---: |",
    ]
    for row in result["domains"]:
        lines.append(f"| {row['domain']} | {row['total_pj']:.6f} | {row['average_mw']:.6f} |")
    lines.extend(["", "## Blocks", "", "| Block | Kind | Domain | Cells | Toggles | Energy (pJ) |", "| --- | --- | --- | ---: | ---: | ---: |"])
    for row in result["blocks"]:
        lines.append(
            f"| {row['block']} | {row['kind']} | {row['domain']} | {row['cell_count']} | "
            f"{row.get('gate_toggles', 0)} | {row['total_pj']:.6f} |"
        )
    (out_dir / "2416_power_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--stdcells", type=Path, required=True)
    parser.add_argument("--memory-macros", type=Path, default=Path("configs/memory_macros/mobile_cpu_memory_macros.json"))
    parser.add_argument("--tech", type=Path, default=Path("configs/tech/generic_7nm.json"))
    parser.add_argument("--gate-vcd", type=Path, required=True)
    parser.add_argument("--rtl-vcd", type=Path)
    parser.add_argument("--activity", type=Path)
    parser.add_argument("--scheme", default="dvfs_retention_domains")
    parser.add_argument("--out", type=Path, default=Path("reports/legacy2416_mapped"))
    args = parser.parse_args()

    tech = json.loads(args.tech.read_text(encoding="utf-8"))
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    cell_lib = json.loads(args.stdcells.read_text(encoding="utf-8"))
    macro_config = json.loads(args.memory_macros.read_text(encoding="utf-8"))
    macros = {macro["block"]: macro for macro in macro_config["macros"]}
    activity = load_activity(args, tech)
    gate_activity = parse_gate_vcd_toggles(args.gate_vcd)
    result = estimate(metrics, cell_lib, macros, gate_activity, activity, tech)
    write_reports(result, args.out)
    print(f"wrote {args.out / '2416_power_summary.md'}")


if __name__ == "__main__":
    main()
