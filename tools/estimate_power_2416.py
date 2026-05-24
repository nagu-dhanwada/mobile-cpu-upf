#!/usr/bin/env python3
"""Estimate RTL power from IEEE 2416 XML power models and VCD activity."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from vcd_activity_2416 import VcdActivityExtractor


POWER_STATES = {"RUN", "IDLE", "LIGHT_SLEEP", "DEEP_SLEEP", "WAKE"}
DOMAIN_ORDER = ("PD_AON", "PD_CPU", "PD_MEM")
DOMAIN_COLORS = {
    "PD_AON": "#4c78a8",
    "PD_CPU": "#f58518",
    "PD_MEM": "#54a24b",
}
STATE_COLORS = {
    "RUN": "#e8f2ff",
    "IDLE": "#edf6e8",
    "LIGHT_SLEEP": "#fff4d6",
    "DEEP_SLEEP": "#eeeaf8",
    "WAKE": "#fde7e9",
}


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def child(element: ET.Element, name: str) -> ET.Element | None:
    for candidate in element:
        if local_name(candidate.tag) == name:
            return candidate
    return None


def children(element: ET.Element, name: str) -> list[ET.Element]:
    return [candidate for candidate in element if local_name(candidate.tag) == name]


def fattr(element: ET.Element, name: str, default: float = 0.0) -> float:
    try:
        return float(element.attrib.get(name, default))
    except ValueError:
        return default


@dataclass
class PowerModel:
    block: str
    module: str
    rtl_path: str
    domain: str
    clock: str
    leakage_mw_by_state: dict[str, float]
    event_pj: dict[str, float]
    clock_pj: float
    toggle_pj: float
    reference_voltage_v: float
    dynamic_voltage_exponent: float
    leakage_voltage_exponent: float


def load_models(model_dir: Path) -> list[PowerModel]:
    models: list[PowerModel] = []
    for path in sorted(model_dir.glob("*.xml")):
        root = ET.parse(path).getroot()
        design = child(root, "design")
        if design is None:
            continue
        components = child(root, "powerComponents")
        scaling = child(root, "scaling")
        voltage_scaling = child(scaling, "voltage") if scaling is not None else None

        leakage: dict[str, float] = {}
        event_pj: dict[str, float] = {}
        clock_pj = 0.0
        toggle_pj = 0.0
        if components is not None:
            for component in children(components, "component"):
                ctype = component.attrib.get("type", "")
                ref = component.attrib.get("ref", "")
                value = fattr(component, "value")
                if ctype == "leakage":
                    leakage[ref] = value
                elif ctype == "event":
                    event_pj[ref] = value
                elif ctype == "clock":
                    clock_pj = value
                elif ctype == "toggle":
                    toggle_pj = value

        models.append(
            PowerModel(
                block=design.attrib["block"],
                module=design.attrib["module"],
                rtl_path=design.attrib["rtlPath"],
                domain=design.attrib["powerDomain"],
                clock=design.attrib["clock"],
                leakage_mw_by_state=leakage,
                event_pj=event_pj,
                clock_pj=clock_pj,
                toggle_pj=toggle_pj,
                reference_voltage_v=fattr(voltage_scaling, "referenceV", 1.0) if voltage_scaling is not None else 1.0,
                dynamic_voltage_exponent=fattr(voltage_scaling, "dynamicExponent", 2.0)
                if voltage_scaling is not None
                else 2.0,
                leakage_voltage_exponent=fattr(voltage_scaling, "leakageExponent", 1.0)
                if voltage_scaling is not None
                else 1.0,
            )
        )
    return models


def domain_voltage(tech: dict, domain: str, dvfs: str | int, state: str | None = None) -> float:
    supplies = tech["supplies"]
    if domain == "PD_AON":
        return supplies["VDD_AON"]
    if domain == "PD_MEM":
        return supplies["VDD_MEM"]
    if state == "DEEP_SLEEP":
        return 0.0
    dvfs_value = int(dvfs)
    if dvfs_value == 0:
        return supplies["VDD_CPU_LOW"]
    if dvfs_value == 2:
        return supplies["VDD_CPU_TURBO"]
    return supplies["VDD_CPU_NOM"]


def remap_state_for_scheme(state: str, scheme: str) -> str:
    if scheme == "baseline_always_on":
        return "RUN"
    if scheme == "clock_gated_idle":
        if state in {"LIGHT_SLEEP", "DEEP_SLEEP"}:
            return "IDLE"
        return state
    if scheme == "core_power_gated_sleep":
        if state == "IDLE":
            return "LIGHT_SLEEP"
        return state
    return state


def remap_dvfs_for_scheme(dvfs: str, scheme: str) -> str:
    if scheme in {"baseline_always_on", "clock_gated_idle", "core_power_gated_sleep"}:
        return "1"
    return str(dvfs)


def apply_scheme_profile(activity: dict, scheme: str) -> dict:
    profiled = copy.deepcopy(activity)
    profiled["scheme"] = scheme
    if scheme == "dvfs_retention_domains":
        return profiled

    state_durations: dict[str, float] = {}
    for state, duration in profiled.get("state_durations_ps", {}).items():
        mapped = remap_state_for_scheme(state, scheme)
        state_durations[mapped] = state_durations.get(mapped, 0.0) + float(duration)
    profiled["state_durations_ps"] = dict(sorted(state_durations.items()))

    for segment in profiled.get("state_timeline", []):
        segment["state"] = remap_state_for_scheme(segment.get("state", "RUN"), scheme)
        segment["dvfs"] = remap_dvfs_for_scheme(segment.get("dvfs", "1"), scheme)

    merged_timeline: list[dict] = []
    for segment in profiled.get("state_timeline", []):
        if (
            merged_timeline
            and merged_timeline[-1]["state"] == segment["state"]
            and merged_timeline[-1]["dvfs"] == segment["dvfs"]
            and abs(float(merged_timeline[-1]["end_ps"]) - float(segment["start_ps"])) < 1e-9
        ):
            merged_timeline[-1]["end_ps"] = segment["end_ps"]
            merged_timeline[-1]["duration_ps"] += segment["duration_ps"]
        else:
            merged_timeline.append(segment)
    profiled["state_timeline"] = merged_timeline

    dvfs_durations: dict[str, float] = {}
    for dvfs, duration in profiled.get("dvfs_durations_ps", {}).items():
        mapped = remap_dvfs_for_scheme(dvfs, scheme)
        dvfs_durations[mapped] = dvfs_durations.get(mapped, 0.0) + float(duration)
    profiled["dvfs_durations_ps"] = dict(sorted(dvfs_durations.items()))

    for key in ("clock_cycles_by_dvfs", "event_counts_by_dvfs"):
        remapped_outer: dict[str, dict[str, int]] = {}
        for name, counts in profiled.get(key, {}).items():
            remapped_counts: dict[str, int] = {}
            for dvfs, count in counts.items():
                mapped = remap_dvfs_for_scheme(dvfs, scheme)
                remapped_counts[mapped] = remapped_counts.get(mapped, 0) + int(count)
            remapped_outer[name] = dict(sorted(remapped_counts.items()))
        profiled[key] = remapped_outer

    if scheme == "baseline_always_on":
        top_cycles = int(profiled.get("clock_cycles", {}).get("top", 0))
        profiled["clock_cycles"]["core"] = top_cycles
        profiled["clock_cycles"]["mem"] = top_cycles
        profiled["clock_cycles_by_dvfs"]["core"] = {"1": top_cycles}
        profiled["clock_cycles_by_dvfs"]["mem"] = {"1": top_cycles}
        profiled["clock_cycles_by_dvfs"]["top"] = {"1": top_cycles}

    return profiled


def voltage_scale(voltage: float, reference: float, exponent: float) -> float:
    if voltage <= 0 or reference <= 0:
        return 0.0
    return math.pow(voltage / reference, exponent)


def event_energy(model: PowerModel, event: str, counts_by_dvfs: dict[str, int], tech: dict) -> float:
    base_pj = model.event_pj.get(event, 0.0)
    total = 0.0
    for dvfs, count in counts_by_dvfs.items():
        voltage = domain_voltage(tech, model.domain, dvfs)
        scale = voltage_scale(voltage, model.reference_voltage_v, model.dynamic_voltage_exponent)
        total += base_pj * count * scale
    return total


def clock_energy(model: PowerModel, activity: dict, tech: dict) -> float:
    if model.clock == "none" or model.clock_pj == 0.0:
        return 0.0
    cycles_by_dvfs = activity.get("clock_cycles_by_dvfs", {}).get(model.clock, {})
    total = 0.0
    for dvfs, cycles in cycles_by_dvfs.items():
        voltage = domain_voltage(tech, model.domain, dvfs)
        scale = voltage_scale(voltage, model.reference_voltage_v, model.dynamic_voltage_exponent)
        total += model.clock_pj * cycles * scale
    return total


def leakage_energy(model: PowerModel, activity: dict, tech: dict) -> float:
    total = 0.0
    for state, duration_ps in activity.get("state_durations_ps", {}).items():
        if state not in POWER_STATES:
            continue
        leakage_mw = model.leakage_mw_by_state.get(state, model.leakage_mw_by_state.get("RUN", 0.0))
        voltage = domain_voltage(tech, model.domain, 1, state=state)
        scale = voltage_scale(voltage, model.reference_voltage_v, model.leakage_voltage_exponent)
        duration_ns = float(duration_ps) / 1000.0
        total += leakage_mw * scale * duration_ns
    return total


def leakage_power_mw(model: PowerModel, state: str, tech: dict) -> float:
    leakage_mw = model.leakage_mw_by_state.get(state, model.leakage_mw_by_state.get("RUN", 0.0))
    voltage = domain_voltage(tech, model.domain, 1, state=state)
    scale = voltage_scale(voltage, model.reference_voltage_v, model.leakage_voltage_exponent)
    return leakage_mw * scale


def toggle_energy(model: PowerModel, activity: dict, tech: dict) -> float:
    toggles = activity.get("block_toggles", {}).get(model.block, 0)
    voltage = domain_voltage(tech, model.domain, 1)
    scale = voltage_scale(voltage, model.reference_voltage_v, model.dynamic_voltage_exponent)
    return toggles * model.toggle_pj * scale


def domain_is_dynamically_active(domain: str, state: str) -> bool:
    if domain == "PD_AON":
        return True
    return state in {"RUN", "WAKE"}


def build_power_timeline(models: list[PowerModel], activity: dict, result: dict, tech: dict) -> list[dict]:
    timeline = activity.get("state_timeline", [])
    if not timeline:
        return []

    duration_ns = result["duration_ns"]
    domain_totals = {row["domain"]: row for row in result["domains"]}
    dynamic_energy_by_domain = {
        domain: domain_totals.get(domain, {}).get("clock_pj", 0.0)
        + domain_totals.get(domain, {}).get("event_pj", 0.0)
        + domain_totals.get(domain, {}).get("toggle_pj", 0.0)
        for domain in DOMAIN_ORDER
    }
    active_duration_by_domain: dict[str, float] = {domain: 0.0 for domain in DOMAIN_ORDER}
    for segment in timeline:
        state = segment["state"]
        duration_ns_segment = float(segment["duration_ps"]) / 1000.0
        for domain in DOMAIN_ORDER:
            if domain_is_dynamically_active(domain, state):
                active_duration_by_domain[domain] += duration_ns_segment

    rows: list[dict] = []
    for segment in timeline:
        state = segment["state"]
        row = {
            "start_ns": float(segment["start_ps"]) / 1000.0,
            "end_ns": float(segment["end_ps"]) / 1000.0,
            "duration_ns": float(segment["duration_ps"]) / 1000.0,
            "state": state,
            "dvfs": segment.get("dvfs", "1"),
        }
        total_mw = 0.0
        for domain in DOMAIN_ORDER:
            leakage_mw = sum(leakage_power_mw(model, state, tech) for model in models if model.domain == domain)
            dynamic_mw = 0.0
            if domain_is_dynamically_active(domain, state) and active_duration_by_domain[domain] > 0:
                dynamic_mw = dynamic_energy_by_domain[domain] / active_duration_by_domain[domain]
            row[f"{domain}_mw"] = leakage_mw + dynamic_mw
            total_mw += row[f"{domain}_mw"]
        row["total_mw"] = total_mw
        rows.append(row)
    return rows


def estimate(models: list[PowerModel], activity: dict, tech: dict) -> dict:
    blocks: list[dict] = []
    by_domain: dict[str, dict[str, float]] = {}
    duration_ns = activity.get("duration_ps", 0.0) / 1000.0

    for model in models:
        leakage_pj = leakage_energy(model, activity, tech)
        clk_pj = clock_energy(model, activity, tech)
        event_pj = 0.0
        for event in model.event_pj:
            key = f"{model.block}.{event}"
            event_pj += event_energy(
                model,
                event,
                activity.get("event_counts_by_dvfs", {}).get(key, {}),
                tech,
            )
        toggle_pj = toggle_energy(model, activity, tech)
        total_pj = leakage_pj + clk_pj + event_pj + toggle_pj
        average_mw = total_pj / duration_ns if duration_ns > 0 else 0.0
        block_row = {
            "block": model.block,
            "module": model.module,
            "domain": model.domain,
            "leakage_pj": leakage_pj,
            "clock_pj": clk_pj,
            "event_pj": event_pj,
            "toggle_pj": toggle_pj,
            "total_pj": total_pj,
            "average_mw": average_mw,
        }
        blocks.append(block_row)
        domain_row = by_domain.setdefault(
            model.domain,
            {"leakage_pj": 0.0, "clock_pj": 0.0, "event_pj": 0.0, "toggle_pj": 0.0, "total_pj": 0.0},
        )
        for key in ("leakage_pj", "clock_pj", "event_pj", "toggle_pj", "total_pj"):
            domain_row[key] += block_row[key]

    total_energy_pj = sum(row["total_pj"] for row in blocks)
    result = {
        "source_vcd": activity.get("source", ""),
        "technology": tech["name"],
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
    }
    result["power_timeline"] = build_power_timeline(models, activity, result, tech)
    return result


def normalize_activity_time(activity: dict, tech: dict) -> dict:
    normalized = copy.deepcopy(activity)
    raw_duration_ps = float(normalized.get("duration_ps", 0.0))
    top_cycles = int(normalized.get("clock_cycles", {}).get("top", 0))
    frequency_mhz = float(tech.get("clock_frequency_mhz", 0.0))

    if raw_duration_ps <= 0.0 or top_cycles <= 0 or frequency_mhz <= 0.0:
        normalized["time_normalization"] = {
            "applied": False,
            "reason": "Missing raw duration, top clock cycles, or technology clock frequency.",
        }
        return normalized

    real_duration_ns = top_cycles * (1000.0 / frequency_mhz)
    real_duration_ps = real_duration_ns * 1000.0
    scale = real_duration_ps / raw_duration_ps

    normalized["raw_duration_ps"] = raw_duration_ps
    normalized["duration_ps"] = real_duration_ps
    for key in ("state_durations_ps", "dvfs_durations_ps"):
        normalized[key] = {
            name: float(duration) * scale
            for name, duration in normalized.get(key, {}).items()
        }
    normalized["state_timeline"] = [
        {
            **segment,
            "start_ps": float(segment["start_ps"]) * scale,
            "end_ps": float(segment["end_ps"]) * scale,
            "duration_ps": float(segment["duration_ps"]) * scale,
        }
        for segment in normalized.get("state_timeline", [])
    ]
    normalized["time_normalization"] = {
        "applied": True,
        "raw_duration_ps": raw_duration_ps,
        "normalized_duration_ps": real_duration_ps,
        "top_cycles": top_cycles,
        "clock_frequency_mhz": frequency_mhz,
        "scale": scale,
    }
    return normalized


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def xml_escape(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_timeline_svg(result: dict, path: Path) -> None:
    timeline = result.get("power_timeline", [])
    if not timeline:
        return

    width = 1100
    height = 440
    left = 72
    right = 24
    top = 42
    plot_height = 285
    band_top = top + plot_height + 32
    band_height = 24
    plot_width = width - left - right
    duration = max(float(row["end_ns"]) for row in timeline)
    max_power = max(float(row["total_mw"]) for row in timeline) * 1.15 or 1.0

    def x(value: float) -> float:
        return left + (value / duration) * plot_width if duration else left

    def y(value: float) -> float:
        return top + plot_height - (value / max_power) * plot_height

    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="440" viewBox="0 0 1100 440">',
        '<rect width="1100" height="440" fill="#ffffff"/>',
        f'<text x="{left}" y="24" font-family="Arial" font-size="18" font-weight="700">IEEE 2416 Power Timeline - {xml_escape(result["scheme"])}</text>',
        f'<text x="{left}" y="39" font-family="Arial" font-size="12" fill="#555">Technology: {xml_escape(result["technology"])}  Average: {result["average_power_mw"]:.4f} mW  Energy: {result["total_energy_pj"]:.4f} pJ</text>',
    ]

    for i in range(5):
        value = max_power * i / 4
        yy = y(value)
        lines.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{left + plot_width}" y2="{yy:.2f}" stroke="#e4e7eb" stroke-width="1"/>')
        lines.append(f'<text x="{left - 8}" y="{yy + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11" fill="#555">{value:.2f}</text>')
    lines.append(f'<text x="18" y="{top + plot_height / 2:.2f}" transform="rotate(-90 18 {top + plot_height / 2:.2f})" font-family="Arial" font-size="12" fill="#555">Power (mW)</text>')

    for row in timeline:
        x0 = x(float(row["start_ns"]))
        x1 = x(float(row["end_ns"]))
        if x1 <= x0:
            continue
        base = 0.0
        for domain in DOMAIN_ORDER:
            value = float(row.get(f"{domain}_mw", 0.0))
            y0 = y(base)
            y1 = y(base + value)
            lines.append(
                f'<rect x="{x0:.2f}" y="{y1:.2f}" width="{max(x1 - x0, 0.6):.2f}" '
                f'height="{max(y0 - y1, 0.0):.2f}" fill="{DOMAIN_COLORS[domain]}" opacity="0.82"/>'
            )
            base += value

    lines.append(f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" stroke="#222" stroke-width="1"/>')
    lines.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#222" stroke-width="1"/>')
    for i in range(6):
        value = duration * i / 5
        xx = x(value)
        lines.append(f'<line x1="{xx:.2f}" y1="{top + plot_height}" x2="{xx:.2f}" y2="{top + plot_height + 5}" stroke="#222"/>')
        lines.append(f'<text x="{xx:.2f}" y="{top + plot_height + 20}" text-anchor="middle" font-family="Arial" font-size="11" fill="#555">{value:.1f}</text>')
    lines.append(f'<text x="{left + plot_width / 2:.2f}" y="{height - 16}" text-anchor="middle" font-family="Arial" font-size="12" fill="#555">Time (ns)</text>')

    for row in timeline:
        x0 = x(float(row["start_ns"]))
        x1 = x(float(row["end_ns"]))
        color = STATE_COLORS.get(row["state"], "#f4f4f4")
        lines.append(
            f'<rect x="{x0:.2f}" y="{band_top}" width="{max(x1 - x0, 0.6):.2f}" height="{band_height}" '
            f'fill="{color}" stroke="#ffffff" stroke-width="0.5"/>'
        )
    lines.append(f'<text x="{left - 8}" y="{band_top + 16}" text-anchor="end" font-family="Arial" font-size="11" fill="#555">mode</text>')

    legend_x = left
    legend_y = band_top + 50
    for domain in DOMAIN_ORDER:
        lines.append(f'<rect x="{legend_x}" y="{legend_y - 10}" width="14" height="14" fill="{DOMAIN_COLORS[domain]}"/>')
        lines.append(f'<text x="{legend_x + 20}" y="{legend_y + 2}" font-family="Arial" font-size="12" fill="#333">{domain}</text>')
        legend_x += 92

    state_x = left + 330
    for state, color in STATE_COLORS.items():
        lines.append(f'<rect x="{state_x}" y="{legend_y - 10}" width="14" height="14" fill="{color}" stroke="#bbb"/>')
        lines.append(f'<text x="{state_x + 19}" y="{legend_y + 2}" font-family="Arial" font-size="12" fill="#333">{state}</text>')
        state_x += 112

    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_bar_svg(result: dict, path: Path, rows: list[dict], label_key: str, value_key: str, title: str) -> None:
    width = 920
    row_height = 30
    top = 54
    left = 170
    right = 30
    height = top + len(rows) * row_height + 45
    max_value = max((float(row[value_key]) for row in rows), default=1.0) or 1.0
    plot_width = width - left - right
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="24" y="28" font-family="Arial" font-size="18" font-weight="700">{xml_escape(title)}</text>',
        f'<text x="24" y="44" font-family="Arial" font-size="12" fill="#555">{xml_escape(result["technology"])} / {xml_escape(result["scheme"])}</text>',
    ]
    for idx, row in enumerate(rows):
        y0 = top + idx * row_height
        value = float(row[value_key])
        bar_width = (value / max_value) * plot_width
        color = DOMAIN_COLORS.get(row.get("domain", ""), "#4c78a8")
        lines.append(f'<text x="{left - 10}" y="{y0 + 18}" text-anchor="end" font-family="Arial" font-size="12" fill="#333">{xml_escape(row[label_key])}</text>')
        lines.append(f'<rect x="{left}" y="{y0 + 5}" width="{bar_width:.2f}" height="18" fill="{color}" opacity="0.84"/>')
        lines.append(f'<text x="{left + bar_width + 6:.2f}" y="{y0 + 18}" font-family="Arial" font-size="11" fill="#555">{value:.4f}</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_reports(result: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "2416_power_estimate.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    block_fields = [
        "block",
        "module",
        "domain",
        "leakage_pj",
        "clock_pj",
        "event_pj",
        "toggle_pj",
        "total_pj",
        "average_mw",
    ]
    write_csv(out_dir / "2416_power_by_block.csv", result["blocks"], block_fields)
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

    state_rows = [
        {
            "state": state,
            "duration_ns": duration_ps / 1000.0,
            "residency_percent": (duration_ps / result["activity"]["duration_ps"] * 100.0)
            if result["activity"]["duration_ps"]
            else 0.0,
        }
        for state, duration_ps in sorted(result["activity"].get("state_durations_ps", {}).items())
    ]
    write_csv(out_dir / "2416_state_residency.csv", state_rows, ["state", "duration_ns", "residency_percent"])
    write_timeline_svg(result, out_dir / "2416_power_waveform.svg")
    write_bar_svg(
        result,
        out_dir / "2416_power_by_block.svg",
        result["blocks"],
        "block",
        "total_pj",
        "IEEE 2416 Energy By Block (pJ)",
    )
    write_bar_svg(
        result,
        out_dir / "2416_power_by_domain.svg",
        result["domains"],
        "domain",
        "total_pj",
        "IEEE 2416 Energy By Domain (pJ)",
    )

    summary = [
        "# IEEE 2416 RTL Power Estimate",
        "",
        f"- Technology: `{result['technology']}`",
        f"- Source VCD: `{result['source_vcd']}`",
        f"- Scheme profile: `{result['scheme']}`",
        f"- Duration: {result['duration_ns']:.3f} ns",
        f"- Total energy: {result['total_energy_pj']:.6f} pJ",
        f"- Average power: {result['average_power_mw']:.6f} mW",
        f"- Power waveform SVG: `2416_power_waveform.svg`",
        "",
        "This report evaluates IEEE 2416 XML macro power models against RTL VCD activity.",
        "",
        "## Power By Domain",
        "",
        "| Domain | Energy (pJ) | Average Power (mW) |",
        "| --- | ---: | ---: |",
    ]
    norm = result["activity"].get("time_normalization", {})
    if norm.get("applied"):
        summary.insert(
            10,
            "The VCD dump time was normalized to the configured technology clock "
            f"({norm['clock_frequency_mhz']:.3f} MHz) using {norm['top_cycles']} top-level cycles.",
        )
        summary.insert(11, "")
    for row in result["domains"]:
        summary.append(f"| {row['domain']} | {row['total_pj']:.6f} | {row['average_mw']:.6f} |")

    summary.extend(["", "## Top Blocks", "", "| Block | Domain | Energy (pJ) | Average Power (mW) |", "| --- | --- | ---: | ---: |"])
    for row in result["blocks"]:
        summary.append(f"| {row['block']} | {row['domain']} | {row['total_pj']:.6f} | {row['average_mw']:.6f} |")

    summary.extend(["", "## State Residency", "", "| State | Duration (ns) | Residency (%) |", "| --- | ---: | ---: |"])
    for row in state_rows:
        summary.append(f"| {row['state']} | {row['duration_ns']:.3f} | {row['residency_percent']:.2f} |")

    summary.extend(["", "## Dominant Events", "", "| Event | Count |", "| --- | ---: |"])
    event_counts = sorted(result["activity"].get("event_counts", {}).items(), key=lambda item: item[1], reverse=True)
    for event, count in event_counts[:20]:
        summary.append(f"| {event} | {count} |")

    (out_dir / "2416_power_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, default=Path("power_models/mobile_cpu/rtl"))
    parser.add_argument("--tech", type=Path, default=Path("configs/tech/generic_7nm.json"))
    parser.add_argument("--vcd", type=Path)
    parser.add_argument("--activity", type=Path)
    parser.add_argument("--out", type=Path, default=Path("reports/2416"))
    parser.add_argument("--scheme", default="dvfs_retention_domains")
    args = parser.parse_args()

    if not args.vcd and not args.activity:
        print("Either --vcd or --activity is required", file=sys.stderr)
        raise SystemExit(2)

    tech = json.loads(args.tech.read_text(encoding="utf-8"))
    models = load_models(args.models)
    if not models:
        print(f"No XML power models found in {args.models}", file=sys.stderr)
        raise SystemExit(2)

    if args.activity:
        activity = json.loads(args.activity.read_text(encoding="utf-8"))
    else:
        assert args.vcd is not None
        activity = VcdActivityExtractor(args.vcd).extract()
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "2416_activity.json").write_text(json.dumps(activity, indent=2) + "\n", encoding="utf-8")

    activity = normalize_activity_time(activity, tech)
    activity = apply_scheme_profile(activity, args.scheme)
    result = estimate(models, activity, tech)
    write_reports(result, args.out)
    print(f"wrote {args.out / '2416_power_summary.md'}")


if __name__ == "__main__":
    main()
