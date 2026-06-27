#!/usr/bin/env python3
"""Generate IEEE 2416-style implementation models for memory macros."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from characterize_2416 import NS, qname


ET.register_namespace("", NS)


def state_leakage(macro: dict, state: str) -> float:
    if state == "DEEP_SLEEP":
        return float(macro.get("power_gated_leakage_mw", macro["leakage_mw"] * 0.02))
    if state == "LIGHT_SLEEP":
        return float(macro.get("retention_leakage_mw", macro["leakage_mw"] * 0.35))
    if state == "IDLE":
        return float(macro["leakage_mw"]) * 0.82
    return float(macro["leakage_mw"])


def write_macro_model(macro: dict, config: dict, out_dir: Path) -> Path:
    root = ET.Element(
        qname("powerModel"),
        {
            "standard": "IEEE2416-2025",
            "schemaVersion": "0.1.0",
            "modelClass": "implementationMacro",
            "abstractionLevel": "physical",
        },
    )

    metadata = ET.SubElement(root, qname("metadata"))
    ET.SubElement(metadata, qname("name")).text = macro["block"]
    ET.SubElement(metadata, qname("description")).text = macro["description"]
    ET.SubElement(metadata, qname("generator")).text = "tools/gen_memory_macro_2416.py"
    ET.SubElement(metadata, qname("source")).text = config["name"]
    ET.SubElement(metadata, qname("provenance")).text = (
        "Generated from the mobile CPU memory macro configuration. "
        "These are simple macro coefficients used to keep SRAM/ROM behavior distinct from synthesized logic."
    )

    design = ET.SubElement(
        root,
        qname("design"),
        {
            "block": macro["block"],
            "module": macro["module"],
            "rtlPath": macro["rtlPath"],
            "powerDomain": macro["powerDomain"],
            "clock": macro["clock"],
        },
    )
    for key, value in macro.get("parameters", {}).items():
        ET.SubElement(design, qname("parameter"), {"name": key, "value": str(value), "unit": "config"})
    ET.SubElement(design, qname("parameter"), {"name": "area", "value": f'{float(macro["area_um2"]):.6f}', "unit": "um2"})

    oc = ET.SubElement(root, qname("operatingConditions"))
    ET.SubElement(oc, qname("process"), {"nodeNm": "45", "corner": "macro_nominal"})
    ET.SubElement(oc, qname("temperature"), {"valueC": "25.000"})
    ET.SubElement(
        oc,
        qname("supply"),
        {"name": "VDD_MEM" if macro["powerDomain"] == "PD_MEM" else "VDD_CPU_NOM", "voltageV": f'{float(config["reference_voltage_v"]):.5f}'},
    )
    if macro["clock"] != "none":
        ET.SubElement(oc, qname("clock"), {"name": macro["clock"], "frequencyMHz": "1000.000"})

    power_states = ET.SubElement(root, qname("powerStates"))
    for state in ("RUN", "IDLE", "LIGHT_SLEEP", "DEEP_SLEEP", "WAKE"):
        ET.SubElement(
            power_states,
            qname("state"),
            {
                "name": state,
                "supply": "off" if state == "DEEP_SLEEP" else ("VDD_MEM" if macro["powerDomain"] == "PD_MEM" else "VDD_CPU_NOM"),
                "clock": "gated" if state in {"IDLE", "LIGHT_SLEEP", "DEEP_SLEEP"} and macro["clock"] != "none" else ("combinational" if macro["clock"] == "none" else "enabled"),
                "isolation": str(state == "DEEP_SLEEP").lower(),
                "retention": str(state in {"LIGHT_SLEEP", "DEEP_SLEEP"}).lower(),
                "leakageMw": f"{state_leakage(macro, state):.9f}",
            },
        )

    activity = ET.SubElement(root, qname("activityParameters"))
    if macro["clock"] != "none":
        ET.SubElement(activity, qname("event"), {"name": "clock_cycle", "source": f'{macro["clock"]}_clock_posedge'})
    for name, event in macro["events"].items():
        ET.SubElement(activity, qname("event"), {"name": name, "source": event["source"], "description": event["description"]})

    components = ET.SubElement(root, qname("powerComponents"))
    for state in ("RUN", "IDLE", "LIGHT_SLEEP", "DEEP_SLEEP", "WAKE"):
        ET.SubElement(
            components,
            qname("component"),
            {
                "type": "leakage",
                "name": f"leakage_{state.lower()}",
                "ref": state,
                "value": f"{state_leakage(macro, state):.9f}",
                "unit": "mW",
                "voltageScaled": "true",
            },
        )
    if macro["clock"] != "none":
        ET.SubElement(
            components,
            qname("component"),
            {
                "type": "clock",
                "name": "clock_cycle",
                "ref": "clock_cycle",
                "value": "0.010000000",
                "unit": "pJ",
                "voltageScaled": "true",
            },
        )
    for name, event in macro["events"].items():
        ET.SubElement(
            components,
            qname("component"),
            {
                "type": "event",
                "name": name,
                "ref": name,
                "value": f'{float(event["energy_pj"]):.9f}',
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
                "domain": macro["powerDomain"],
                "driver": f"power_state.{state}",
                "componentRef": f"leakage_{state.lower()}",
                "pvtDependency": "process,voltage,temperature",
                "voltageDependency": "leakageExponent",
                "frequencyDependency": "none",
                "stateDependency": state,
                "workloadDependency": "state_residency_time",
            },
        )
    if macro["clock"] != "none":
        ET.SubElement(
            contributors,
            qname("contributor"),
            {
                "name": "macro_clocking",
                "type": "clock",
                "domain": macro["powerDomain"],
                "driver": f'{macro["clock"]}_clock_posedge',
                "componentRef": "clock_cycle",
                "pvtDependency": "process,voltage",
                "voltageDependency": "dynamicExponent",
                "frequencyDependency": "active_clock_cycles",
                "stateDependency": "clock_enabled_power_states",
                "workloadDependency": "clock_residency",
            },
        )
    for name, event in macro["events"].items():
        ET.SubElement(
            contributors,
            qname("contributor"),
            {
                "name": f"event_{name}",
                "type": "event",
                "domain": macro["powerDomain"],
                "driver": event["source"],
                "componentRef": name,
                "pvtDependency": "process,voltage",
                "voltageDependency": "dynamicExponent",
                "frequencyDependency": "event_count",
                "stateDependency": "active_domain_power_states",
                "workloadDependency": "memory_transaction_count",
            },
        )

    scaling = ET.SubElement(root, qname("scaling"))
    ET.SubElement(
        scaling,
        qname("voltage"),
        {"referenceV": f'{float(config["reference_voltage_v"]):.5f}', "dynamicExponent": "2.000", "leakageExponent": "1.200"},
    )
    ET.SubElement(scaling, qname("temperature"), {"referenceC": "25.000", "leakagePer10cFactor": "1.350"})
    validity = ET.SubElement(root, qname("validity"))
    ET.SubElement(validity, qname("voltageRange"), {"minV": "0.60000", "maxV": "1.32000"})
    ET.SubElement(validity, qname("temperatureRange"), {"minC": "-40.000", "maxC": "125.000"})

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{macro['block']}.xml"
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/memory_macros/mobile_cpu_memory_macros.json"))
    parser.add_argument("--out", type=Path, default=Path("power_models/mobile_cpu/legacy2416/macros"))
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    written = [write_macro_model(macro, config, args.out) for macro in config["macros"]]
    for path in written:
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
