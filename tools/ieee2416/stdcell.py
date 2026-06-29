#!/usr/bin/env python3
"""Generate OpenLowPower IEEE 2416 Library models for Liberty standard cells."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    REPO_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(REPO_ROOT))

from tools.ieee2416.characterize import default_units
from tools.ieee2416.ir import (
    Cell,
    Condition,
    ConditionSet,
    Event,
    EventEnergy,
    Library,
    LibraryParameter,
    Mode,
    ModelParameter,
    Pin,
    PowerValue,
    ProcessInfo,
    State,
    Technology,
    fmt_float,
)
from tools.ieee2416.writer import write_library
from tools.liberty_2416 import parse_liberty


POWER_STATES = ("RUN", "IDLE", "LIGHT_SLEEP", "DEEP_SLEEP", "WAKE")


def output_xml_path(path: Path, techlib_name: str) -> Path:
    if path.suffix == ".xml":
        return path
    return path / f"{techlib_name}_stdcells_library.xml"


def leakage_for_state(run_mw: float, state: str) -> float:
    if state == "DEEP_SLEEP":
        return run_mw * 0.02
    if state == "LIGHT_SLEEP":
        return run_mw * 0.35
    if state == "IDLE":
        return run_mw * 0.82
    return run_mw


def condition_set(techlib: dict, nominal_voltage: float) -> ConditionSet:
    process = techlib.get("process", {})
    return ConditionSet(
        f"{techlib['name']}_nominal",
        (
            Condition("process_corner", str(process.get("corner", "typical"))),
            Condition("node_nm", str(process.get("node_nm", 45))),
            Condition("temperature_c", fmt_float(float(techlib.get("temperature_c", 25.0)), 3)),
            Condition("VDD", fmt_float(nominal_voltage, 5)),
        ),
    )


def library_parameters(techlib: dict, nominal_voltage: float) -> tuple[LibraryParameter, ...]:
    process = techlib.get("process", {})
    return (
        LibraryParameter("node_nm", str(process.get("node_nm", 45)), type="integer", data_type="integer", units="nM"),
        LibraryParameter("temperature_c", fmt_float(float(techlib.get("temperature_c", 25.0)), 3), units="C"),
        LibraryParameter("reference_voltage_v", fmt_float(nominal_voltage, 5), units="V"),
        LibraryParameter("dynamic_voltage_exponent", "2", units="Enumerated"),
        LibraryParameter("leakage_voltage_exponent", "1.2", units="Enumerated"),
        LibraryParameter("reference_temperature_c", fmt_float(float(techlib.get("temperature_c", 25.0)), 3), units="C"),
        LibraryParameter("leakage_per_10c_factor", "1.35", units="Enumerated"),
    )


def pins_for_cell(is_sequential: bool) -> tuple[Pin, ...]:
    pins = [
        Pin("VDD", "pg", pin_type="primaryPower"),
        Pin("VSS", "pg", pin_type="primaryGround"),
        Pin("activity", "input", data_type="bit", pin_type="signal", related_power="VDD", related_ground="VSS"),
    ]
    if is_sequential:
        pins.insert(2, Pin("clk", "input", data_type="bit", pin_type="clock", related_power="VDD", related_ground="VSS"))
    return tuple(pins)


def modes_for_cell(is_sequential: bool) -> tuple[Mode, ...]:
    modes = []
    for index, state in enumerate(POWER_STATES):
        if state == "DEEP_SLEEP":
            clock = "retained" if is_sequential else "combinational"
            supply = "off"
        elif state in {"IDLE", "LIGHT_SLEEP"}:
            clock = "gated" if is_sequential else "combinational"
            supply = "on"
        else:
            clock = "enabled" if is_sequential else "combinational"
            supply = "on"
        modes.append(
            Mode(
                name=state,
                when=f"power_mode == {state}",
                value=float(index),
                expression=f"mode_is_{state.lower()} && clock_{clock} && supply_{supply}",
            )
        )
    return tuple(modes)


def states_for_cell(cell: dict) -> tuple[State, ...]:
    states = []
    run_mw = float(cell["leakage_mw"])
    for state in POWER_STATES:
        leakage = leakage_for_state(run_mw, state)
        states.append(
            State(
                name=state,
                when=f"power_mode == {state}",
                static_power=(
                    PowerValue(
                        leakage,
                        "mW",
                        expression=f"{fmt_float(leakage)} * leakage_voltage_scale * leakage_temperature_scale",
                    ),
                ),
            )
        )
    return tuple(states)


def events_for_cell(cell: dict) -> tuple[Event, ...]:
    events = [
        Event(
            name="cell_transition",
            mode="RUN",
            when="mapped_vcd_instance_toggle && domain_on",
            input_pin="activity",
            input_transition="rising",
            energy=EventEnergy(float(cell["switching_energy_pj"])),
        )
    ]
    if cell.get("is_sequential"):
        events.insert(
            0,
            Event(
                name="clock_cycle",
                mode="RUN",
                when="clock_enabled && domain_on",
                input_pin="clk",
                input_transition="rising",
                energy=EventEnergy(max(float(cell["switching_energy_pj"]) * 0.35, 0.000001)),
            ),
        )
    return tuple(events)


def model_parameters_for_cell(cell: dict, techlib: dict, nominal_voltage: float) -> tuple[ModelParameter, ...]:
    is_sequential = bool(cell.get("is_sequential", False))
    return (
        ModelParameter("module", cell["name"]),
        ModelParameter("rtl_path", f"library.{techlib['name']}.{cell['name']}"),
        ModelParameter("power_domain", "PD_CPU"),
        ModelParameter("clock_name", "core" if is_sequential else "none"),
        ModelParameter("model_class", "standard_cell"),
        ModelParameter("abstraction_level", "mapped_gate"),
        ModelParameter("library", techlib["name"]),
        ModelParameter("area_um2", fmt_float(float(cell["area_um2"]), 6), "float"),
        ModelParameter("input_cap_ff", fmt_float(float(cell["input_cap_ff"]), 6), "float"),
        ModelParameter("is_sequential", str(is_sequential).lower(), "enum"),
        ModelParameter("reference_voltage_v", fmt_float(nominal_voltage, 5), "float"),
        ModelParameter("dynamic_voltage_exponent", "2", "float"),
        ModelParameter("leakage_voltage_exponent", "1.2", "float"),
    )


def cell_model(cell: dict, techlib: dict, nominal_voltage: float, condition_name: str) -> Cell:
    is_sequential = bool(cell.get("is_sequential", False))
    return Cell(
        name=cell["name"],
        pins=pins_for_cell(is_sequential),
        modes=modes_for_cell(is_sequential),
        events=events_for_cell(cell),
        model_parameters=model_parameters_for_cell(cell, techlib, nominal_voltage),
        states=states_for_cell(cell),
        condition=condition_name,
        datagen="estimated",
    )


def build_library(techlib: dict, liberty_summary: dict) -> Library:
    nominal_voltage = float(liberty_summary["nominal_voltage_v"])
    process = techlib.get("process", {})
    conditions = condition_set(techlib, nominal_voltage)
    technology = Technology(
        name=techlib["name"],
        version="1.0",
        processes=(ProcessInfo(name=str(process.get("corner", "typical"))),),
    )
    cells = tuple(
        cell_model(cell, techlib, nominal_voltage, conditions.name)
        for cell in sorted(liberty_summary["cells"].values(), key=lambda item: item["name"])
    )
    return Library(
        name=f"{techlib['name']}_stdcells_ieee2416",
        version="0.1.0",
        technology=technology,
        units=default_units(),
        parameters=library_parameters(techlib, nominal_voltage),
        conditions=(conditions,),
        cells=cells,
        condition=conditions.name,
        datagen="estimated",
        annotation="Generated OpenLowPower IEEE 2416 standard-cell library from Liberty coefficients.",
    )


def write_summary(liberty_summary: dict, techlib: dict, out_dir: Path, xml_path: Path) -> None:
    cells = liberty_summary["cells"]
    rows = sorted(cells.values(), key=lambda row: row["switching_energy_pj"], reverse=True)
    total_area = sum(row["area_um2"] for row in cells.values())
    total_leakage = sum(row["leakage_mw"] for row in cells.values())
    lines = [
        "# IEEE 2416 Standard Cell Library Summary",
        "",
        f"- Technology library: `{techlib['name']}`",
        f"- Liberty source: `{liberty_summary['source']}`",
        f"- OpenLowPower XML: `{xml_path}`",
        f"- Cells modeled: {len(cells)}",
        f"- Nominal voltage: {liberty_summary['nominal_voltage_v']:.3f} V",
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


def write_manifest(path: Path, library: Library, techlib_path: Path, liberty_summary: dict, xml_path: Path) -> None:
    manifest = {
        "library": library.name,
        "version": library.version,
        "format": "OpenLowPower IEEE 2416 Library",
        "model_class": "standard_cell",
        "techlib_config": str(techlib_path),
        "liberty": liberty_summary["source"],
        "xml": str(xml_path),
        "cells": [cell.name for cell in library.cells],
        "cell_count": len(library.cells),
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--techlib", type=Path, default=Path("configs/techlibs/nangate45.json"))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    techlib = json.loads(args.techlib.read_text(encoding="utf-8"))
    out_path = output_xml_path(args.out or Path(techlib.get("stdcell_models_dir", "power_models/stdcells/nangate45")), techlib["name"])
    out_dir = out_path.parent
    liberty_summary = parse_liberty(Path(techlib["liberty"]))
    library = build_library(techlib, liberty_summary)
    written = write_library(library, out_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stdcells_summary.json").write_text(json.dumps(liberty_summary, indent=2) + "\n", encoding="utf-8")
    write_summary(liberty_summary, techlib, out_dir, written)
    write_manifest(args.manifest or (out_dir / "stdcells_library_manifest.json"), library, args.techlib, liberty_summary, written)
    print(f"wrote {written}")
    print(f"wrote {len(library.cells)} standard-cell model(s)")


if __name__ == "__main__":
    main()
