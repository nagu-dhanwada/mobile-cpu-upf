#!/usr/bin/env python3
"""Explore DVFS operating points with IEEE 2416 XML power models and VCD activity."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    REPO_ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(REPO_ROOT))

from estimate_power_2416 import (
    apply_scheme_profile,
    estimate,
    normalize_activity_time,
    xml_escape,
)
from tools.ieee2416.estimate import load_library_models
from vcd_activity_2416 import VcdActivityExtractor


CONTRIBUTOR_KEYS = ("leakage_pj", "clock_pj", "event_pj", "toggle_pj")
CONTRIBUTOR_LABELS = {
    "leakage_pj": "Leakage",
    "clock_pj": "Clock",
    "event_pj": "Events",
    "toggle_pj": "Toggles",
}
CONTRIBUTOR_COLORS = {
    "leakage_pj": "#4c78a8",
    "clock_pj": "#f58518",
    "event_pj": "#54a24b",
    "toggle_pj": "#e45756",
}
BAR_COLOR = "#4c78a8"


def load_opps(path: Path) -> dict:
    opps = json.loads(path.read_text(encoding="utf-8"))
    if "opps" not in opps or not isinstance(opps["opps"], list) or not opps["opps"]:
        raise ValueError(f"{path} must contain a non-empty 'opps' list")

    required = {"name", "dvfs_level", "cpu_voltage_v", "cpu_frequency_mhz", "mem_voltage_v", "mem_frequency_mhz"}
    for idx, opp in enumerate(opps["opps"]):
        missing = sorted(required - set(opp))
        if missing:
            raise ValueError(f"{path}: OPP #{idx} missing {missing}")
        opp["dvfs_level"] = str(opp["dvfs_level"])
        for key in ("cpu_voltage_v", "cpu_frequency_mhz", "mem_voltage_v", "mem_frequency_mhz"):
            opp[key] = float(opp[key])
    return opps


def force_counts_to_opp(counts_by_dvfs: dict, level: str) -> dict:
    forced = {}
    for name, counts in counts_by_dvfs.items():
        forced[name] = {level: sum(int(count) for count in counts.values())}
    return forced


def force_opp_activity(activity: dict, opp: dict) -> dict:
    forced = copy.deepcopy(activity)
    level = str(opp["dvfs_level"])

    forced["forced_opp"] = opp["name"]
    forced["forced_opp_dvfs_level"] = level
    forced["event_counts_by_dvfs"] = force_counts_to_opp(forced.get("event_counts_by_dvfs", {}), level)
    forced["clock_cycles_by_dvfs"] = force_counts_to_opp(forced.get("clock_cycles_by_dvfs", {}), level)

    duration_ps = float(forced.get("duration_ps", 0.0))
    forced["dvfs_durations_ps"] = {level: duration_ps}
    for segment in forced.get("state_timeline", []):
        segment["dvfs"] = level
    return forced


def tech_for_opp(base_tech: dict, opp: dict) -> dict:
    tech = copy.deepcopy(base_tech)
    tech["name"] = f'{base_tech["name"]}:{opp["name"]}'
    tech["clock_frequency_mhz"] = float(opp["cpu_frequency_mhz"])
    supplies = tech.setdefault("supplies", {})
    for supply in ("VDD_CPU_LOW", "VDD_CPU_NOM", "VDD_CPU_TURBO"):
        supplies[supply] = float(opp["cpu_voltage_v"])
    supplies["VDD_MEM"] = float(opp["mem_voltage_v"])
    tech["dvfs_opp"] = {
        "name": opp["name"],
        "dvfs_level": str(opp["dvfs_level"]),
        "cpu_voltage_v": float(opp["cpu_voltage_v"]),
        "cpu_frequency_mhz": float(opp["cpu_frequency_mhz"]),
        "mem_voltage_v": float(opp["mem_voltage_v"]),
        "mem_frequency_mhz": float(opp["mem_frequency_mhz"]),
    }
    return tech


def contributor_totals(result: dict) -> dict[str, float]:
    totals = {key: 0.0 for key in CONTRIBUTOR_KEYS}
    for row in result.get("blocks", []):
        for key in CONTRIBUTOR_KEYS:
            totals[key] += float(row.get(key, 0.0))
    return totals


def retired_instruction_count(activity: dict) -> int:
    return int(activity.get("event_counts", {}).get("decode_unit.decode_instruction", 0))


def make_row(opp: dict, result: dict) -> dict:
    totals = contributor_totals(result)
    dynamic_pj = totals["clock_pj"] + totals["event_pj"] + totals["toggle_pj"]
    duration_ns = float(result.get("duration_ns", 0.0))
    total_energy_pj = float(result.get("total_energy_pj", 0.0))
    instructions = retired_instruction_count(result.get("activity", {}))
    row = {
        "opp": opp["name"],
        "dvfs_level": str(opp["dvfs_level"]),
        "cpu_voltage_v": float(opp["cpu_voltage_v"]),
        "cpu_frequency_mhz": float(opp["cpu_frequency_mhz"]),
        "mem_voltage_v": float(opp["mem_voltage_v"]),
        "mem_frequency_mhz": float(opp["mem_frequency_mhz"]),
        "duration_ns": duration_ns,
        "total_energy_pj": total_energy_pj,
        "average_power_mw": float(result.get("average_power_mw", 0.0)),
        "leakage_pj": totals["leakage_pj"],
        "clock_pj": totals["clock_pj"],
        "event_pj": totals["event_pj"],
        "toggle_pj": totals["toggle_pj"],
        "dynamic_pj": dynamic_pj,
        "edp_pj_ns": total_energy_pj * duration_ns,
        "ed2p_pj_ns2": total_energy_pj * duration_ns * duration_ns,
        "retired_instructions": instructions,
        "energy_per_instruction_pj": total_energy_pj / instructions if instructions > 0 else 0.0,
    }
    total = max(total_energy_pj, 1e-30)
    row["leakage_percent"] = totals["leakage_pj"] / total * 100.0
    row["dynamic_percent"] = dynamic_pj / total * 100.0
    return row


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_metric_svg(path: Path, rows: list[dict], value_key: str, title: str, unit: str) -> None:
    width = 920
    height = 380
    left = 86
    right = 28
    top = 58
    bottom = 78
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_value = max((float(row[value_key]) for row in rows), default=1.0) or 1.0
    gap = 28
    bar_width = max(42, (plot_width - gap * (len(rows) + 1)) / max(len(rows), 1))

    def y(value: float) -> float:
        return top + plot_height - (value / max_value) * plot_height

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="24" y="30" font-family="Arial" font-size="18" font-weight="700">{xml_escape(title)}</text>',
        f'<text x="24" y="47" font-family="Arial" font-size="12" fill="#555">Unit: {xml_escape(unit)}</text>',
    ]
    for i in range(5):
        value = max_value * i / 4
        yy = y(value)
        lines.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{width - right}" y2="{yy:.2f}" stroke="#e4e7eb"/>')
        lines.append(f'<text x="{left - 8}" y="{yy + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11" fill="#555">{value:.3f}</text>')
    lines.append(f'<line x1="{left}" y1="{top + plot_height}" x2="{width - right}" y2="{top + plot_height}" stroke="#222"/>')
    lines.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#222"/>')

    for idx, row in enumerate(rows):
        value = float(row[value_key])
        x0 = left + gap + idx * (bar_width + gap)
        y0 = y(value)
        lines.append(f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{bar_width:.2f}" height="{top + plot_height - y0:.2f}" fill="{BAR_COLOR}" opacity="0.86"/>')
        lines.append(f'<text x="{x0 + bar_width / 2:.2f}" y="{y0 - 6:.2f}" text-anchor="middle" font-family="Arial" font-size="11" fill="#333">{value:.3f}</text>')
        lines.append(f'<text x="{x0 + bar_width / 2:.2f}" y="{top + plot_height + 20}" text-anchor="middle" font-family="Arial" font-size="11" fill="#333">{xml_escape(row["opp"])}</text>')
        detail = f'{row["cpu_voltage_v"]:.2f}V/{row["cpu_frequency_mhz"]:.0f}MHz'
        lines.append(f'<text x="{x0 + bar_width / 2:.2f}" y="{top + plot_height + 36}" text-anchor="middle" font-family="Arial" font-size="10" fill="#555">{xml_escape(detail)}</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_contributor_svg(path: Path, rows: list[dict]) -> None:
    width = 980
    height = 430
    left = 84
    right = 28
    top = 58
    bottom = 108
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_value = max((float(row["total_energy_pj"]) for row in rows), default=1.0) or 1.0
    gap = 28
    bar_width = max(42, (plot_width - gap * (len(rows) + 1)) / max(len(rows), 1))

    def y(value: float) -> float:
        return top + plot_height - (value / max_value) * plot_height

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        '<text x="24" y="30" font-family="Arial" font-size="18" font-weight="700">DVFS Energy Contributors</text>',
        '<text x="24" y="47" font-family="Arial" font-size="12" fill="#555">Stacked IEEE 2416 contributor categories per operating point</text>',
    ]
    for i in range(5):
        value = max_value * i / 4
        yy = y(value)
        lines.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{width - right}" y2="{yy:.2f}" stroke="#e4e7eb"/>')
        lines.append(f'<text x="{left - 8}" y="{yy + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11" fill="#555">{value:.3f}</text>')
    lines.append(f'<line x1="{left}" y1="{top + plot_height}" x2="{width - right}" y2="{top + plot_height}" stroke="#222"/>')
    lines.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#222"/>')

    for idx, row in enumerate(rows):
        x0 = left + gap + idx * (bar_width + gap)
        base = 0.0
        for key in CONTRIBUTOR_KEYS:
            value = float(row[key])
            y0 = y(base)
            y1 = y(base + value)
            lines.append(
                f'<rect x="{x0:.2f}" y="{y1:.2f}" width="{bar_width:.2f}" '
                f'height="{max(y0 - y1, 0.0):.2f}" fill="{CONTRIBUTOR_COLORS[key]}" opacity="0.88"/>'
            )
            base += value
        lines.append(f'<text x="{x0 + bar_width / 2:.2f}" y="{y(base) - 6:.2f}" text-anchor="middle" font-family="Arial" font-size="11" fill="#333">{base:.3f}</text>')
        lines.append(f'<text x="{x0 + bar_width / 2:.2f}" y="{top + plot_height + 20}" text-anchor="middle" font-family="Arial" font-size="11" fill="#333">{xml_escape(row["opp"])}</text>')
        lines.append(f'<text x="{x0 + bar_width / 2:.2f}" y="{top + plot_height + 36}" text-anchor="middle" font-family="Arial" font-size="10" fill="#555">{row["cpu_voltage_v"]:.2f}V/{row["cpu_frequency_mhz"]:.0f}MHz</text>')

    legend_x = left
    legend_y = height - 38
    for key in CONTRIBUTOR_KEYS:
        lines.append(f'<rect x="{legend_x}" y="{legend_y - 10}" width="14" height="14" fill="{CONTRIBUTOR_COLORS[key]}"/>')
        lines.append(f'<text x="{legend_x + 20}" y="{legend_y + 2}" font-family="Arial" font-size="12" fill="#333">{CONTRIBUTOR_LABELS[key]}</text>')
        legend_x += 112
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def best_row(rows: list[dict], key: str) -> dict:
    return min(rows, key=lambda row: float(row[key]))


def write_summary(path: Path, rows: list[dict], metadata: dict) -> None:
    best_energy = best_row(rows, "total_energy_pj")
    best_power = best_row(rows, "average_power_mw")
    best_runtime = best_row(rows, "duration_ns")
    best_edp = best_row(rows, "edp_pj_ns")
    lines = [
        "# IEEE 2416 DVFS Exploration",
        "",
        f"- Technology: `{metadata['technology']}`",
        f"- Workload source: `{metadata['source']}`",
        f"- Scheme profile: `{metadata['scheme']}`",
        f"- OPP set: `{metadata['opp_set']}`",
        f"- Lowest energy: `{best_energy['opp']}` ({best_energy['total_energy_pj']:.6f} pJ)",
        f"- Lowest average power: `{best_power['opp']}` ({best_power['average_power_mw']:.6f} mW)",
        f"- Shortest runtime: `{best_runtime['opp']}` ({best_runtime['duration_ns']:.3f} ns)",
        f"- Best energy-delay product: `{best_edp['opp']}` ({best_edp['edp_pj_ns']:.6f} pJ*ns)",
        "",
        "The same workload activity is replayed at each operating performance point. "
        "The same IEEE 2416 model coefficients are reused, while voltage and frequency "
        "are supplied by the selected OPP.",
        "",
        "## Operating Points",
        "",
        "| OPP | DVFS | CPU V | CPU MHz | Runtime ns | Energy pJ | Avg mW | EDP pJ*ns | Leakage % | Dynamic % |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['opp']} | {row['dvfs_level']} | {row['cpu_voltage_v']:.3f} | "
            f"{row['cpu_frequency_mhz']:.1f} | {row['duration_ns']:.3f} | "
            f"{row['total_energy_pj']:.6f} | {row['average_power_mw']:.6f} | "
            f"{row['edp_pj_ns']:.6f} | {row['leakage_percent']:.2f} | {row['dynamic_percent']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Visual Outputs",
            "",
            "- `dvfs_energy.svg`",
            "- `dvfs_average_power.svg`",
            "- `dvfs_runtime.svg`",
            "- `dvfs_edp.svg`",
            "- `dvfs_contributors.svg`",
            "- `dvfs_points.csv`",
            "- `dvfs_contributors.csv`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_reports(out_dir: Path, rows: list[dict], results: list[dict], metadata: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = [
        "opp",
        "dvfs_level",
        "cpu_voltage_v",
        "cpu_frequency_mhz",
        "mem_voltage_v",
        "mem_frequency_mhz",
        "duration_ns",
        "total_energy_pj",
        "average_power_mw",
        "leakage_pj",
        "clock_pj",
        "event_pj",
        "toggle_pj",
        "dynamic_pj",
        "edp_pj_ns",
        "ed2p_pj_ns2",
        "retired_instructions",
        "energy_per_instruction_pj",
        "leakage_percent",
        "dynamic_percent",
    ]
    write_csv(out_dir / "dvfs_points.csv", rows, fields)
    write_csv(
        out_dir / "dvfs_contributors.csv",
        rows,
        ["opp", "leakage_pj", "clock_pj", "event_pj", "toggle_pj", "dynamic_pj", "total_energy_pj"],
    )
    (out_dir / "dvfs_results.json").write_text(
        json.dumps({"metadata": metadata, "points": rows, "results": results}, indent=2) + "\n",
        encoding="utf-8",
    )
    write_summary(out_dir / "dvfs_summary.md", rows, metadata)
    write_metric_svg(out_dir / "dvfs_energy.svg", rows, "total_energy_pj", "DVFS Total Energy", "pJ")
    write_metric_svg(out_dir / "dvfs_average_power.svg", rows, "average_power_mw", "DVFS Average Power", "mW")
    write_metric_svg(out_dir / "dvfs_runtime.svg", rows, "duration_ns", "DVFS Runtime", "ns")
    write_metric_svg(out_dir / "dvfs_edp.svg", rows, "edp_pj_ns", "DVFS Energy-Delay Product", "pJ*ns")
    write_contributor_svg(out_dir / "dvfs_contributors.svg", rows)


def explore(args: argparse.Namespace) -> None:
    base_tech = json.loads(args.tech.read_text(encoding="utf-8"))
    opp_set = load_opps(args.opps)
    models = load_library_models(args.model)
    if not models:
        print(f"No OpenLowPower IEEE 2416 cells found in {args.model}", file=sys.stderr)
        raise SystemExit(2)

    if args.activity:
        raw_activity = json.loads(args.activity.read_text(encoding="utf-8"))
    elif args.vcd:
        raw_activity = VcdActivityExtractor(args.vcd).extract()
    else:
        print("Either --vcd or --activity is required", file=sys.stderr)
        raise SystemExit(2)

    rows: list[dict] = []
    results: list[dict] = []
    for opp in opp_set["opps"]:
        tech = tech_for_opp(base_tech, opp)
        activity = apply_scheme_profile(raw_activity, args.scheme)
        activity = force_opp_activity(activity, opp)
        activity = normalize_activity_time(activity, tech)
        activity["scheme"] = args.scheme
        activity["opp"] = opp["name"]
        activity["opp_parameters"] = tech["dvfs_opp"]
        result = estimate(models, activity, tech)
        result["opp"] = opp["name"]
        result["opp_parameters"] = tech["dvfs_opp"]
        rows.append(make_row(opp, result))
        results.append(result)

    metadata = {
        "technology": base_tech["name"],
        "source": raw_activity.get("source", str(args.vcd or args.activity)),
        "scheme": args.scheme,
        "opp_set": opp_set.get("name", str(args.opps)),
    }
    write_reports(args.out, rows, results, metadata)
    print(f"wrote {args.out / 'dvfs_summary.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=Path("power_models/mobile_cpu/ieee2416/mobile_cpu_library.xml"))
    parser.add_argument("--tech", type=Path, default=Path("configs/tech/generic_7nm.json"))
    parser.add_argument("--opps", type=Path, default=Path("configs/dvfs/mobile_cpu_opps.json"))
    parser.add_argument("--vcd", type=Path)
    parser.add_argument("--activity", type=Path)
    parser.add_argument("--scheme", default="dvfs_retention_domains")
    parser.add_argument("--out", type=Path, default=Path("reports/2416/dvfs"))
    args = parser.parse_args()
    try:
        explore(args)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
