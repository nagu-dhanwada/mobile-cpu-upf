#!/usr/bin/env python3
"""Generate an OpenLowPower IEEE 2416 Library for the mobile CPU blocks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    REPO_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(REPO_ROOT))

from tools.characterize_2416 import BLOCKS, clock_state, state_leakage, supply_for_domain
from tools.p2416.ir import (
    Cell,
    Condition,
    ConditionSet,
    Event,
    EventEnergy,
    GlobalExpression,
    Library,
    LibraryParameter,
    Mode,
    ModelParameter,
    Pin,
    PowerValue,
    ProcessInfo,
    State,
    Technology,
    UnitDef,
    fmt_float,
)
from tools.p2416.writer import write_library


POWER_STATES = ("RUN", "IDLE", "LIGHT_SLEEP", "DEEP_SLEEP", "WAKE")


def default_units() -> tuple[UnitDef, ...]:
    return (
        UnitDef("currentUnit", "mA"),
        UnitDef("capacitanceUnit", "fF"),
        UnitDef("resistanceUnit", "ohm"),
        UnitDef("dimensionUnit", "nM"),
        UnitDef("frequencyUnit", "MHz"),
        UnitDef("powerUnit", "mW"),
        UnitDef("energyUnit", "pJ"),
        UnitDef("voltageUnit", "V"),
        UnitDef("temperatureTcUnit", "C"),
        UnitDef("temperatureTkUnit", "K"),
        UnitDef("temperatureUnit", "C"),
        UnitDef("timeUnit", "nS"),
    )


def library_parameters(tech: dict) -> tuple[LibraryParameter, ...]:
    scaling = tech["scaling"]
    params = [
        LibraryParameter("node_nm", str(tech["process"]["node_nm"]), type="integer", data_type="integer", units="nM"),
        LibraryParameter("temperature_c", fmt_float(float(tech["temperature_c"]), 3), units="C"),
        LibraryParameter("clock_frequency_mhz", fmt_float(float(tech["clock_frequency_mhz"]), 3), units="MHz"),
        LibraryParameter("reference_voltage_v", fmt_float(float(scaling["reference_voltage_v"]), 5), units="V"),
        LibraryParameter("dynamic_voltage_exponent", fmt_float(float(scaling["dynamic_voltage_exponent"]), 3), units="Enumerated"),
        LibraryParameter("leakage_voltage_exponent", fmt_float(float(scaling["leakage_voltage_exponent"]), 3), units="Enumerated"),
        LibraryParameter("reference_temperature_c", fmt_float(float(scaling["reference_temperature_c"]), 3), units="C"),
        LibraryParameter("leakage_per_10c_factor", fmt_float(float(scaling["leakage_per_10c_factor"]), 3), units="Enumerated"),
    ]
    for supply, voltage in sorted(tech["supplies"].items()):
        params.append(LibraryParameter(f"supply_{supply}", fmt_float(float(voltage), 5), units="V"))
    return tuple(params)


def condition_set(tech: dict) -> ConditionSet:
    conditions = [
        Condition("process_corner", str(tech["process"]["corner"])),
        Condition("node_nm", str(tech["process"]["node_nm"])),
        Condition("temperature_c", fmt_float(float(tech["temperature_c"]), 3)),
        Condition("clock_frequency_mhz", fmt_float(float(tech["clock_frequency_mhz"]), 3)),
    ]
    for supply, voltage in sorted(tech["supplies"].items()):
        conditions.append(Condition(supply, fmt_float(float(voltage), 5)))
    return ConditionSet(f"{tech['name']}_nominal", tuple(conditions))


def library_expressions() -> tuple[GlobalExpression, ...]:
    return (
        GlobalExpression(
            "dynamic_voltage_scale",
            "(voltage / reference_voltage_v) ** dynamic_voltage_exponent",
            source="VDD",
            sink="VSS",
        ),
        GlobalExpression(
            "leakage_voltage_scale",
            "(voltage / reference_voltage_v) ** leakage_voltage_exponent",
            source="VDD",
            sink="VSS",
        ),
        GlobalExpression(
            "leakage_temperature_scale",
            "leakage_per_10c_factor ** ((temperature_c - reference_temperature_c) / 10.0)",
        ),
        GlobalExpression(
            "event_power_from_count",
            "EvalEvent(event_name) * event_count / observation_time",
        ),
    )


def pins_for_block(block) -> tuple[Pin, ...]:
    pins = [
        Pin("VDD", "pg", pin_type="primaryPower"),
        Pin("VSS", "pg", pin_type="primaryGround"),
        Pin("activity", "input", data_type="bit", pin_type="signal", related_power="VDD", related_ground="VSS"),
        Pin("power_mode", "input", width="[2:0]", data_type="integer", pin_type="signal", related_power="VDD", related_ground="VSS"),
        Pin("dvfs_level", "input", width="[1:0]", data_type="integer", pin_type="signal", related_power="VDD", related_ground="VSS"),
        Pin("domain_on", "input", data_type="bit", pin_type="signal", related_power="VDD", related_ground="VSS"),
    ]
    if block.clock != "none":
        pins.insert(2, Pin("clk", "input", data_type="bit", pin_type="clock", related_power="VDD", related_ground="VSS"))
    return tuple(pins)


def modes_for_block(block) -> tuple[Mode, ...]:
    modes = []
    for index, state in enumerate(POWER_STATES):
        clock = clock_state(block, state)
        supply = supply_for_domain(block, state)
        modes.append(
            Mode(
                name=state,
                when=f"power_mode == {state}",
                value=float(index),
                units=None,
                expression=f"mode_is_{state.lower()} && clock_{clock} && supply_{supply}",
            )
        )
    return tuple(modes)


def states_for_block(block, tech: dict) -> tuple[State, ...]:
    states = []
    for state in POWER_STATES:
        leakage = state_leakage(block, tech, state)
        expression = (
            f"{fmt_float(leakage)} * leakage_voltage_scale * leakage_temperature_scale"
            if leakage > 0
            else "0"
        )
        states.append(
            State(
                name=state,
                when=f"power_mode == {state}",
                static_power=(PowerValue(leakage, "mW", expression=expression),),
            )
        )
    return tuple(states)


def events_for_block(block, tech: dict) -> tuple[Event, ...]:
    events = []
    if block.clock != "none":
        clock_energy = tech["energy"]["flop_clock_pj_per_bit"] * max(block.flop_bits, 1)
        events.append(
            Event(
                name="clock_cycle",
                mode="RUN",
                when=f"{block.clock}_clock_enabled && domain_on",
                input_pin="clk",
                input_transition="rising",
                energy=EventEnergy(clock_energy),
            )
        )
    for event in block.events:
        events.append(
            Event(
                name=event.name,
                mode="RUN",
                when=f"{event.source} && domain_on",
                input_pin="activity",
                input_transition="rising",
                energy=EventEnergy(event.energy(tech)),
            )
        )
    if block.toggle_bits:
        events.append(
            Event(
                name="rtl_toggle",
                mode="RUN",
                when=f"vcd_activity && domain_on && block == {block.name}",
                input_pin="activity",
                input_transition="rising",
                energy=EventEnergy(tech["energy"]["toggle_pj_per_bit"]),
            )
        )
    return tuple(events)


def model_parameters_for_block(block, tech: dict) -> tuple[ModelParameter, ...]:
    scaling = tech["scaling"]
    params = [
        ModelParameter("module", block.module),
        ModelParameter("rtl_path", block.rtl_path),
        ModelParameter("power_domain", block.power_domain),
        ModelParameter("clock_name", block.clock),
        ModelParameter("model_class", "rtl_macro"),
        ModelParameter("logic_gates", str(block.logic_gates), "integer"),
        ModelParameter("flop_bits", str(block.flop_bits), "integer"),
        ModelParameter("sram_bits", str(block.sram_bits), "integer"),
        ModelParameter("toggle_energy_pj", fmt_float(float(tech["energy"]["toggle_pj_per_bit"])), "float"),
        ModelParameter("reference_voltage_v", fmt_float(float(scaling["reference_voltage_v"]), 5), "float"),
        ModelParameter("dynamic_voltage_exponent", fmt_float(float(scaling["dynamic_voltage_exponent"]), 3), "float"),
        ModelParameter("leakage_voltage_exponent", fmt_float(float(scaling["leakage_voltage_exponent"]), 3), "float"),
    ]
    for name, value, unit in block.parameters:
        params.append(ModelParameter(f"param_{name}", str(value), "string"))
        params.append(ModelParameter(f"param_{name}_unit", unit, "string"))
    return tuple(params)


def cell_for_block(block, tech: dict, condition_name: str) -> Cell:
    return Cell(
        name=block.name,
        pins=pins_for_block(block),
        modes=modes_for_block(block),
        events=events_for_block(block, tech),
        model_parameters=model_parameters_for_block(block, tech),
        states=states_for_block(block, tech),
        condition=condition_name,
        datagen="estimated",
    )


def build_library(tech: dict) -> Library:
    conditions = condition_set(tech)
    technology = Technology(
        name=tech["name"],
        version="1.0",
        processes=(
            ProcessInfo(
                name=str(tech["process"]["corner"]),
            ),
        ),
    )
    return Library(
        name="mobile_cpu_p2416",
        version="0.1.0",
        technology=technology,
        units=default_units(),
        parameters=library_parameters(tech),
        conditions=(conditions,),
        expressions=library_expressions(),
        cells=tuple(cell_for_block(block, tech, conditions.name) for block in BLOCKS),
        condition=conditions.name,
        datagen="estimated",
        annotation=(
            "Generated OpenLowPower IEEE 2416 library for the mobile CPU educational "
            "power exploration platform."
        ),
    )


def write_manifest(path: Path, library: Library, tech_path: Path, xml_path: Path) -> None:
    manifest = {
        "library": library.name,
        "version": library.version,
        "technology": library.technology.name if library.technology else "",
        "tech_config": str(tech_path),
        "xml": str(xml_path),
        "cells": [cell.name for cell in library.cells],
        "cell_count": len(library.cells),
        "format": "OpenLowPower IEEE 2416 Library",
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tech", type=Path, default=Path("configs/tech/generic_7nm.json"))
    parser.add_argument("--out", type=Path, default=Path("power_models/mobile_cpu/p2416/mobile_cpu_library.xml"))
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    tech = json.loads(args.tech.read_text(encoding="utf-8"))
    library = build_library(tech)
    out_path = write_library(library, args.out)
    manifest_path = args.manifest or (out_path.parent / "mobile_cpu_library_manifest.json")
    write_manifest(manifest_path, library, args.tech, out_path)
    print(f"wrote {out_path}")
    print(f"wrote {manifest_path}")


if __name__ == "__main__":
    main()
