#!/usr/bin/env python3
"""Generate OpenLowPower IEEE 2416 Library models for memory macros."""

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


POWER_STATES = ("RUN", "IDLE", "LIGHT_SLEEP", "DEEP_SLEEP", "WAKE")


def state_leakage(macro: dict, state: str) -> float:
    if state == "DEEP_SLEEP":
        return float(macro.get("power_gated_leakage_mw", macro["leakage_mw"] * 0.02))
    if state == "LIGHT_SLEEP":
        return float(macro.get("retention_leakage_mw", macro["leakage_mw"] * 0.35))
    if state == "IDLE":
        return float(macro["leakage_mw"]) * 0.82
    return float(macro["leakage_mw"])


def condition_set(config: dict) -> ConditionSet:
    return ConditionSet(
        f"{config['name']}_nominal",
        (
            Condition("process_corner", "macro_nominal"),
            Condition("temperature_c", "25"),
            Condition("reference_voltage_v", fmt_float(float(config["reference_voltage_v"]), 5)),
        ),
    )


def library_parameters(config: dict) -> tuple[LibraryParameter, ...]:
    return (
        LibraryParameter("reference_voltage_v", fmt_float(float(config["reference_voltage_v"]), 5), units="V"),
        LibraryParameter("dynamic_voltage_exponent", "2", units="Enumerated"),
        LibraryParameter("leakage_voltage_exponent", "1.2", units="Enumerated"),
        LibraryParameter("reference_temperature_c", "25", units="C"),
        LibraryParameter("leakage_per_10c_factor", "1.35", units="Enumerated"),
    )


def pins_for_macro(macro: dict) -> tuple[Pin, ...]:
    pins = [
        Pin("VDD", "pg", pin_type="primaryPower"),
        Pin("VSS", "pg", pin_type="primaryGround"),
        Pin("activity", "input", data_type="bit", pin_type="signal", related_power="VDD", related_ground="VSS"),
        Pin("power_mode", "input", width="[2:0]", data_type="integer", pin_type="signal", related_power="VDD", related_ground="VSS"),
    ]
    if macro["clock"] != "none":
        pins.insert(2, Pin("clk", "input", data_type="bit", pin_type="clock", related_power="VDD", related_ground="VSS"))
    return tuple(pins)


def modes_for_macro(macro: dict) -> tuple[Mode, ...]:
    modes = []
    has_clock = macro["clock"] != "none"
    for index, state in enumerate(POWER_STATES):
        if state == "DEEP_SLEEP":
            clock = "retained" if has_clock else "combinational"
            supply = "off"
        elif state in {"IDLE", "LIGHT_SLEEP"}:
            clock = "gated" if has_clock else "combinational"
            supply = "retention" if state == "LIGHT_SLEEP" else "on"
        else:
            clock = "enabled" if has_clock else "combinational"
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


def states_for_macro(macro: dict) -> tuple[State, ...]:
    states = []
    for state in POWER_STATES:
        leakage = state_leakage(macro, state)
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


def events_for_macro(macro: dict) -> tuple[Event, ...]:
    events = []
    if macro["clock"] != "none":
        events.append(
            Event(
                name="clock_cycle",
                mode="RUN",
                when=f"{macro['clock']}_clock_enabled && domain_on",
                input_pin="clk",
                input_transition="rising",
                energy=EventEnergy(0.010),
            )
        )
    for name, event in macro["events"].items():
        events.append(
            Event(
                name=name,
                mode="RUN",
                when=f"{event['source']} && domain_on",
                input_pin="activity",
                input_transition="rising",
                energy=EventEnergy(float(event["energy_pj"])),
            )
        )
    return tuple(events)


def model_parameters_for_macro(macro: dict, config: dict) -> tuple[ModelParameter, ...]:
    params = [
        ModelParameter("module", macro["module"]),
        ModelParameter("rtl_path", macro["rtlPath"]),
        ModelParameter("power_domain", macro["powerDomain"]),
        ModelParameter("clock_name", macro["clock"]),
        ModelParameter("model_class", "memory_macro"),
        ModelParameter("abstraction_level", "macro"),
        ModelParameter("area_um2", fmt_float(float(macro["area_um2"]), 6), "float"),
        ModelParameter("reference_voltage_v", fmt_float(float(config["reference_voltage_v"]), 5), "float"),
        ModelParameter("dynamic_voltage_exponent", "2", "float"),
        ModelParameter("leakage_voltage_exponent", "1.2", "float"),
    ]
    for key, value in macro.get("parameters", {}).items():
        params.append(ModelParameter(f"param_{key}", str(value), "string"))
    return tuple(params)


def cell_for_macro(macro: dict, config: dict, condition_name: str) -> Cell:
    return Cell(
        name=macro["block"],
        pins=pins_for_macro(macro),
        modes=modes_for_macro(macro),
        events=events_for_macro(macro),
        model_parameters=model_parameters_for_macro(macro, config),
        states=states_for_macro(macro),
        condition=condition_name,
        datagen="estimated",
    )


def build_library(config: dict) -> Library:
    conditions = condition_set(config)
    technology = Technology(
        name=config["name"],
        version="1.0",
        processes=(ProcessInfo(name="macro_nominal"),),
    )
    return Library(
        name="mobile_cpu_memory_macros_ieee2416",
        version="0.1.0",
        technology=technology,
        units=default_units(),
        parameters=library_parameters(config),
        conditions=(conditions,),
        cells=tuple(cell_for_macro(macro, config, conditions.name) for macro in config["macros"]),
        condition=conditions.name,
        datagen="estimated",
        annotation="Generated OpenLowPower IEEE 2416 memory macro library for the mobile CPU.",
    )


def write_summary(config: dict, library: Library, xml_path: Path) -> None:
    rows = []
    for macro in config["macros"]:
        rows.append(
            {
                "block": macro["block"],
                "domain": macro["powerDomain"],
                "area_um2": float(macro["area_um2"]),
                "leakage_mw": float(macro["leakage_mw"]),
                "events": ",".join(sorted(macro["events"])),
            }
        )
    summary = {
        "name": library.name,
        "source": config["name"],
        "xml": str(xml_path),
        "reference_voltage_v": float(config["reference_voltage_v"]),
        "macros": rows,
    }
    (xml_path.parent / "memory_macros_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# IEEE 2416 Memory Macro Library Summary",
        "",
        f"- Source: `{config['name']}`",
        f"- OpenLowPower XML: `{xml_path}`",
        f"- Reference voltage: {float(config['reference_voltage_v']):.3f} V",
        "",
        "| Macro | Domain | Area (um^2) | Leakage (mW) | Events |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['block']} | {row['domain']} | {row['area_um2']:.3f} | "
            f"{row['leakage_mw']:.6f} | {row['events']} |"
        )
    (xml_path.parent / "memory_macros_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest(path: Path, library: Library, config_path: Path, xml_path: Path) -> None:
    manifest = {
        "library": library.name,
        "version": library.version,
        "format": "OpenLowPower IEEE 2416 Library",
        "model_class": "memory_macro",
        "config": str(config_path),
        "xml": str(xml_path),
        "cells": [cell.name for cell in library.cells],
        "cell_count": len(library.cells),
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/memory_macros/mobile_cpu_memory_macros.json"))
    parser.add_argument("--out", type=Path, default=Path("power_models/mobile_cpu/ieee2416/mobile_cpu_memory_macros.xml"))
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    library = build_library(config)
    out_path = write_library(library, args.out)
    write_summary(config, library, out_path)
    write_manifest(args.manifest or (out_path.parent / "mobile_cpu_memory_macros_manifest.json"), library, args.config, out_path)
    print(f"wrote {out_path}")
    print(f"wrote {len(library.cells)} memory macro model(s)")


if __name__ == "__main__":
    main()
