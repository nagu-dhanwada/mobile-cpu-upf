#!/usr/bin/env python3
"""Generate IEEE 2416-style power models for Liberty standard cells."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from characterize_2416 import NS, qname
from liberty_2416 import parse_liberty


ET.register_namespace("", NS)


def add_common_operating_conditions(root: ET.Element, techlib: dict, nominal_voltage: float) -> None:
    oc = ET.SubElement(root, qname("operatingConditions"))
    process = techlib.get("process", {})
    ET.SubElement(
        oc,
        qname("process"),
        {
            "nodeNm": str(process.get("node_nm", 45)),
            "corner": str(process.get("corner", "typical")),
        },
    )
    ET.SubElement(oc, qname("temperature"), {"valueC": f'{float(techlib.get("temperature_c", 25.0)):.3f}'})
    ET.SubElement(oc, qname("supply"), {"name": "VDD_CPU_NOM", "voltageV": f"{nominal_voltage:.5f}"})
    ET.SubElement(oc, qname("clock"), {"name": "core", "frequencyMHz": "1000.000"})


def leakage_for_state(run_mw: float, state: str) -> float:
    if state == "DEEP_SLEEP":
        return run_mw * 0.02
    if state == "LIGHT_SLEEP":
        return run_mw * 0.35
    if state == "IDLE":
        return run_mw * 0.82
    return run_mw


def write_cell_model(cell: dict, techlib: dict, out_dir: Path, nominal_voltage: float) -> Path:
    name = cell["name"]
    is_seq = bool(cell.get("is_sequential", False))
    root = ET.Element(
        qname("powerModel"),
        {
            "standard": "IEEE2416-2025",
            "schemaVersion": "0.1.0",
            "modelClass": "implementationMacro",
            "abstractionLevel": "gate",
        },
    )

    metadata = ET.SubElement(root, qname("metadata"))
    ET.SubElement(metadata, qname("name")).text = name
    ET.SubElement(metadata, qname("description")).text = f"Nangate45 standard-cell power proxy for {name}."
    ET.SubElement(metadata, qname("generator")).text = "tools/gen_2416_stdcell.py"
    ET.SubElement(metadata, qname("source")).text = techlib.get("source", "")
    ET.SubElement(metadata, qname("provenance")).text = (
        "Generated from Liberty area, leakage, capacitance, and internal-power tables. "
        "This reference flow uses the model as an educational gate-level estimator, not signoff power."
    )

    design = ET.SubElement(
        root,
        qname("design"),
        {
            "block": name,
            "module": name,
            "rtlPath": f"library.{techlib['name']}.{name}",
            "powerDomain": "PD_CPU",
            "clock": "core" if is_seq else "none",
        },
    )
    ET.SubElement(design, qname("parameter"), {"name": "library", "value": techlib["name"], "unit": "name"})
    ET.SubElement(design, qname("parameter"), {"name": "area", "value": f'{cell["area_um2"]:.6f}', "unit": "um2"})
    ET.SubElement(design, qname("parameter"), {"name": "input_cap", "value": f'{cell["input_cap_ff"]:.6f}', "unit": "fF"})
    ET.SubElement(design, qname("parameter"), {"name": "sequential", "value": str(is_seq).lower(), "unit": "boolean"})

    add_common_operating_conditions(root, techlib, nominal_voltage)

    power_states = ET.SubElement(root, qname("powerStates"))
    for state in ("RUN", "IDLE", "LIGHT_SLEEP", "DEEP_SLEEP", "WAKE"):
        ET.SubElement(
            power_states,
            qname("state"),
            {
                "name": state,
                "supply": "off" if state == "DEEP_SLEEP" else "VDD_CPU_NOM",
                "clock": "enabled" if is_seq and state in {"RUN", "WAKE"} else ("gated" if is_seq else "combinational"),
                "isolation": str(state == "DEEP_SLEEP").lower(),
                "retention": str(is_seq and state in {"LIGHT_SLEEP", "DEEP_SLEEP"}).lower(),
                "leakageMw": f'{leakage_for_state(cell["leakage_mw"], state):.12f}',
            },
        )

    activity = ET.SubElement(root, qname("activityParameters"))
    if is_seq:
        ET.SubElement(
            activity,
            qname("event"),
            {
                "name": "clock_cycle",
                "source": "CK",
                "description": "One active clock edge through the sequential cell.",
            },
        )
    ET.SubElement(
        activity,
        qname("signalActivity"),
        {
            "name": "cell_transition",
            "source": "mapped_vcd_instance_toggle",
        },
    )

    components = ET.SubElement(root, qname("powerComponents"))
    for state in ("RUN", "IDLE", "LIGHT_SLEEP", "DEEP_SLEEP", "WAKE"):
        ET.SubElement(
            components,
            qname("component"),
            {
                "type": "leakage",
                "name": f"leakage_{state.lower()}",
                "ref": state,
                "value": f'{leakage_for_state(cell["leakage_mw"], state):.12f}',
                "unit": "mW",
                "voltageScaled": "true",
            },
        )
    ET.SubElement(
        components,
        qname("component"),
        {
            "type": "toggle",
            "name": "cell_transition",
            "ref": "cell_transition",
            "value": f'{cell["switching_energy_pj"]:.12f}',
            "unit": "pJ/toggle",
            "voltageScaled": "true",
        },
    )
    if is_seq:
        ET.SubElement(
            components,
            qname("component"),
            {
                "type": "clock",
                "name": "clock_cycle",
                "ref": "clock_cycle",
                "value": f'{max(cell["switching_energy_pj"] * 0.35, 0.000001):.12f}',
                "unit": "pJ",
                "voltageScaled": "true",
            },
        )

    contributors = ET.SubElement(root, qname("powerContributors"))
    for state in ("RUN", "IDLE", "LIGHT_SLEEP", "DEEP_SLEEP", "WAKE"):
        ET.SubElement(
            contributors,
            qname("contributor"),
            {
                "name": f"static_leakage_{state.lower()}",
                "type": "static",
                "domain": "PD_CPU",
                "driver": f"power_state.{state}",
                "componentRef": f"leakage_{state.lower()}",
                "pvtDependency": "process,voltage,temperature",
                "voltageDependency": "leakageExponent",
                "frequencyDependency": "none",
                "stateDependency": state,
                "workloadDependency": "state_residency_time",
            },
        )
    ET.SubElement(
        contributors,
        qname("contributor"),
        {
            "name": "mapped_cell_transition_activity",
            "type": "toggle",
            "domain": "PD_CPU",
            "driver": "mapped VCD toggles",
            "componentRef": "cell_transition",
            "pvtDependency": "process,voltage",
            "voltageDependency": "dynamicExponent",
            "frequencyDependency": "observed_toggle_rate",
            "stateDependency": "active_domain_power_states",
            "workloadDependency": "gate_level_activity",
        },
    )
    if is_seq:
        ET.SubElement(
            contributors,
            qname("contributor"),
            {
                "name": "sequential_clocking",
                "type": "clock",
                "domain": "PD_CPU",
                "driver": "CK",
                "componentRef": "clock_cycle",
                "pvtDependency": "process,voltage",
                "voltageDependency": "dynamicExponent",
                "frequencyDependency": "active_clock_cycles",
                "stateDependency": "clock_enabled_power_states",
                "workloadDependency": "clock_residency",
            },
        )

    scaling = ET.SubElement(root, qname("scaling"))
    ET.SubElement(
        scaling,
        qname("voltage"),
        {"referenceV": f"{nominal_voltage:.5f}", "dynamicExponent": "2.000", "leakageExponent": "1.200"},
    )
    ET.SubElement(
        scaling,
        qname("temperature"),
        {"referenceC": f'{float(techlib.get("temperature_c", 25.0)):.3f}', "leakagePer10cFactor": "1.350"},
    )
    validity = ET.SubElement(root, qname("validity"))
    ET.SubElement(validity, qname("voltageRange"), {"minV": f"{nominal_voltage * 0.70:.5f}", "maxV": f"{nominal_voltage * 1.20:.5f}"})
    ET.SubElement(validity, qname("temperatureRange"), {"minC": "-40.000", "maxC": "125.000"})

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}.xml"
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return out_path


def write_summary(lib_summary: dict, techlib: dict, out_dir: Path) -> None:
    cells = lib_summary["cells"]
    rows = sorted(cells.values(), key=lambda row: row["switching_energy_pj"], reverse=True)
    total_area = sum(row["area_um2"] for row in cells.values())
    total_leakage = sum(row["leakage_mw"] for row in cells.values())
    lines = [
        "# IEEE 2416 Standard Cell Model Summary",
        "",
        f"- Technology library: `{techlib['name']}`",
        f"- Liberty source: `{lib_summary['source']}`",
        f"- Cells modeled: {len(cells)}",
        f"- Nominal voltage: {lib_summary['nominal_voltage_v']:.3f} V",
        f"- Total library cell area: {total_area:.3f} um^2",
        f"- Sum of per-cell leakage coefficients: {total_leakage:.9f} mW",
        "",
        "| Cell | Area (um^2) | Leakage (mW) | Toggle Energy (pJ) | Seq? |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for row in rows[:30]:
        lines.append(
            f"| {row['name']} | {row['area_um2']:.3f} | {row['leakage_mw']:.9f} | "
            f"{row['switching_energy_pj']:.9f} | {str(row['is_sequential']).lower()} |"
        )
    (out_dir / "stdcell_model_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--techlib", type=Path, default=Path("configs/techlibs/nangate45.json"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    techlib = json.loads(args.techlib.read_text(encoding="utf-8"))
    out_dir = args.out or Path(techlib.get("stdcell_models_dir", "power_models/stdcells/nangate45"))
    lib_summary = parse_liberty(Path(techlib["liberty"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stdcells_summary.json").write_text(json.dumps(lib_summary, indent=2) + "\n", encoding="utf-8")

    written = [write_cell_model(cell, techlib, out_dir, lib_summary["nominal_voltage_v"]) for cell in lib_summary["cells"].values()]
    write_summary(lib_summary, techlib, out_dir)
    print(f"wrote {len(written)} standard-cell 2416 model(s) to {out_dir}")


if __name__ == "__main__":
    main()
