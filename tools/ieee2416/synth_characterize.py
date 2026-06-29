#!/usr/bin/env python3
"""Generate synthesis-calibrated OpenLowPower IEEE 2416 CPU library models."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

if __package__ in {None, ""}:
    REPO_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(REPO_ROOT))

from tools.characterize_2416 import BLOCKS
from tools.ieee2416.characterize import build_library
from tools.ieee2416.ir import Cell, Event, EventEnergy, Library, ModelParameter, PowerValue, State, fmt_float
from tools.ieee2416.writer import write_library


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def block_baselines() -> dict[str, float]:
    baselines: dict[str, float] = {}
    for block in BLOCKS:
        baselines[block.name] = (
            float(block.logic_gates)
            + 4.0 * float(block.flop_bits)
            + 0.05 * float(block.sram_bits)
            + 0.10 * float(block.toggle_bits)
        )
    return baselines


def calibration_for_block(metrics: dict, block_name: str, baseline: float) -> tuple[float, float, dict]:
    block_metrics = metrics.get("blocks", {}).get(block_name, {})
    eq_gates = float(block_metrics.get("estimated_equivalent_gates", 0.0))
    dynamic_factor = clamp(eq_gates / baseline, 0.25, 4.0) if baseline > 0.0 and eq_gates > 0.0 else 1.0
    leakage_factor = clamp(dynamic_factor * 0.90 + 0.10, 0.25, 4.0)
    return dynamic_factor, leakage_factor, block_metrics


def scaled_event(event: Event, factor: float) -> Event:
    if event.energy is None:
        return event
    return replace(event, energy=replace(event.energy, value=event.energy.value * factor))


def scaled_power_value(power: PowerValue, factor: float) -> PowerValue:
    value = power.value * factor
    expression = None
    if power.expression is not None:
        expression = f"{fmt_float(value)} * leakage_voltage_scale * leakage_temperature_scale"
    return replace(power, value=value, expression=expression)


def scaled_state(state: State, factor: float) -> State:
    return replace(
        state,
        static_power=tuple(scaled_power_value(power, factor) for power in state.static_power),
        dynamic_power=tuple(scaled_power_value(power, factor) for power in state.dynamic_power),
    )


def replace_param(params: list[ModelParameter], name: str, value: object, data_type: str = "string") -> None:
    for index, param in enumerate(params):
        if param.name == name:
            params[index] = ModelParameter(name, str(value), data_type)
            return
    params.append(ModelParameter(name, str(value), data_type))


def scaled_cell(cell: Cell, metrics: dict, metrics_path: Path, baseline: float) -> Cell:
    dynamic_factor, leakage_factor, block_metrics = calibration_for_block(metrics, cell.name, baseline)
    params = list(cell.model_parameters)
    replace_param(params, "model_class", "synthesis_calibrated_macro")
    replace_param(params, "abstraction_level", "gate")
    replace_param(params, "synthesis_source", metrics.get("source", ""), "string")
    replace_param(params, "synthesis_metrics", str(metrics_path), "string")
    replace_param(params, "synthesis_workload", metrics.get("workload", ""), "string")
    replace_param(params, "synthesis_cell_count", block_metrics.get("cell_count", 0), "integer")
    replace_param(params, "synthesis_comb_cells", block_metrics.get("combinational_cells", 0), "integer")
    replace_param(params, "synthesis_seq_cells", block_metrics.get("sequential_cells", 0), "integer")
    replace_param(params, "synthesis_latch_cells", block_metrics.get("latch_cells", 0), "integer")
    replace_param(params, "synthesis_memory_cells", block_metrics.get("memory_cells", 0), "integer")
    replace_param(params, "synthesis_equivalent_gates", fmt_float(float(block_metrics.get("estimated_equivalent_gates", 0.0))), "float")
    replace_param(params, "synthesis_dynamic_calibration", fmt_float(dynamic_factor, 6), "float")
    replace_param(params, "synthesis_leakage_calibration", fmt_float(leakage_factor, 6), "float")

    for index, param in enumerate(params):
        if param.name == "toggle_energy_pj":
            try:
                params[index] = replace(param, value=fmt_float(float(param.value) * dynamic_factor))
            except ValueError:
                pass

    return replace(
        cell,
        events=tuple(scaled_event(event, dynamic_factor) for event in cell.events),
        states=tuple(scaled_state(state, leakage_factor) for state in cell.states),
        model_parameters=tuple(params),
        datagen="estimated",
    )


def synth_library(tech: dict, metrics: dict, metrics_path: Path) -> Library:
    base = build_library(tech)
    baselines = block_baselines()
    cells = tuple(scaled_cell(cell, metrics, metrics_path, baselines.get(cell.name, 0.0)) for cell in base.cells)
    return replace(
        base,
        name="mobile_cpu_ieee2416_synth",
        version="0.1.0",
        cells=cells,
        datagen="estimated",
        annotation=(
            "Generated OpenLowPower IEEE 2416 synthesis-calibrated library for the "
            "mobile CPU power exploration platform."
        ),
    )


def write_manifest(path: Path, library: Library, tech_path: Path, metrics_path: Path, xml_path: Path) -> None:
    manifest = {
        "library": library.name,
        "version": library.version,
        "format": "OpenLowPower IEEE 2416 Library",
        "model_class": "synthesis_calibrated_macro",
        "tech_config": str(tech_path),
        "metrics": str(metrics_path),
        "xml": str(xml_path),
        "cells": [cell.name for cell in library.cells],
        "cell_count": len(library.cells),
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tech", type=Path, default=Path("configs/tech/generic_7nm.json"))
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("power_models/mobile_cpu/ieee2416/mobile_cpu_synth_library.xml"))
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    tech = json.loads(args.tech.read_text(encoding="utf-8"))
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    library = synth_library(tech, metrics, args.metrics)
    out_path = write_library(library, args.out)
    manifest_path = args.manifest or (out_path.parent / "mobile_cpu_synth_library_manifest.json")
    write_manifest(manifest_path, library, args.tech, args.metrics, out_path)
    print(f"wrote {out_path}")
    print(f"wrote {manifest_path}")


if __name__ == "__main__":
    main()
