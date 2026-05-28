#!/usr/bin/env python3
"""Generate synthesis-calibrated IEEE 2416 power models from RTL models and Yosys metrics."""

from __future__ import annotations

import argparse
import copy
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from characterize_2416 import BLOCKS, NS, qname


ET.register_namespace("", NS)


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


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def block_baselines() -> dict[str, float]:
    baselines = {}
    for block in BLOCKS:
        baselines[block.name] = (
            float(block.logic_gates)
            + 4.0 * float(block.flop_bits)
            + 0.05 * float(block.sram_bits)
            + 0.10 * float(block.toggle_bits)
        )
    return baselines


def add_parameter(design: ET.Element, name: str, value: object, unit: str = "count") -> None:
    ET.SubElement(design, qname("parameter"), {"name": name, "value": str(value), "unit": unit})


def scale_components(root: ET.Element, leakage_factor: float, dynamic_factor: float) -> None:
    components = child(root, "powerComponents")
    if components is None:
        return
    for component in children(components, "component"):
        ctype = component.attrib.get("type", "")
        factor = leakage_factor if ctype == "leakage" else dynamic_factor
        try:
            value = float(component.attrib.get("value", "0"))
        except ValueError:
            continue
        component.attrib["value"] = f"{value * factor:.9f}"


def update_metadata(root: ET.Element, metrics_path: Path, block_metrics: dict, dynamic_factor: float) -> None:
    metadata = child(root, "metadata")
    if metadata is None:
        return
    name = child(metadata, "name")
    if name is not None:
        name.text = f"{name.text}_synth"
    generator = child(metadata, "generator")
    if generator is not None:
        generator.text = "tools/characterize_2416_synth.py"
    provenance = child(metadata, "provenance")
    if provenance is not None:
        provenance.text = (
            "Synthesis-calibrated from RTL IEEE 2416 model coefficients and "
            f"Yosys block metrics in {metrics_path}. Dynamic calibration factor "
            f"{dynamic_factor:.4f}; estimated equivalent gates "
            f"{block_metrics.get('estimated_equivalent_gates', 0.0):.1f}."
        )


def synth_model(root: ET.Element, metrics: dict, metrics_path: Path, block_name: str, baseline: float) -> ET.Element:
    updated = copy.deepcopy(root)
    updated.attrib["modelClass"] = "synthesisCalibratedMacro"
    updated.attrib["abstractionLevel"] = "gate"

    block_metrics = metrics.get("blocks", {}).get(block_name, {})
    eq_gates = float(block_metrics.get("estimated_equivalent_gates", 0.0))
    if baseline > 0.0 and eq_gates > 0.0:
        dynamic_factor = clamp(eq_gates / baseline, 0.25, 4.0)
    else:
        dynamic_factor = 1.0
    leakage_factor = clamp(dynamic_factor * 0.90 + 0.10, 0.25, 4.0)

    design = child(updated, "design")
    if design is not None:
        add_parameter(design, "synthesis_source", metrics.get("source", ""), "path")
        add_parameter(design, "synthesis_workload", metrics.get("workload", ""), "name")
        add_parameter(design, "synthesis_cell_count", block_metrics.get("cell_count", 0))
        add_parameter(design, "synthesis_comb_cells", block_metrics.get("combinational_cells", 0))
        add_parameter(design, "synthesis_seq_cells", block_metrics.get("sequential_cells", 0))
        add_parameter(design, "synthesis_latch_cells", block_metrics.get("latch_cells", 0))
        add_parameter(design, "synthesis_memory_cells", block_metrics.get("memory_cells", 0))
        add_parameter(design, "synthesis_equivalent_gates", f"{eq_gates:.3f}", "gate")
        add_parameter(design, "synthesis_dynamic_calibration", f"{dynamic_factor:.6f}", "ratio")
        add_parameter(design, "synthesis_leakage_calibration", f"{leakage_factor:.6f}", "ratio")

    scale_components(updated, leakage_factor, dynamic_factor)
    update_metadata(updated, metrics_path, block_metrics, dynamic_factor)
    return updated


def write_model(tree_root: ET.Element, out_path: Path) -> None:
    tree = ET.ElementTree(tree_root)
    ET.indent(tree, space="  ")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rtl-models", type=Path, default=Path("power_models/mobile_cpu/rtl"))
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("power_models/mobile_cpu/synth"))
    args = parser.parse_args()

    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    baselines = block_baselines()
    written = []
    for rtl_model in sorted(args.rtl_models.glob("*.xml")):
        root = ET.parse(rtl_model).getroot()
        design = child(root, "design")
        if design is None:
            continue
        block_name = design.attrib["block"]
        updated = synth_model(root, metrics, args.metrics, block_name, baselines.get(block_name, 0.0))
        out_path = args.out / rtl_model.name
        write_model(updated, out_path)
        written.append(out_path)

    for path in written:
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
