#!/usr/bin/env python3
"""Generate IEEE 2416 RTL macro power models for the mobile CPU blocks."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


NS = "https://standards.ieee.org/ieee/2416/2025/power-model"
ET.register_namespace("", NS)


def qname(name: str) -> str:
    return f"{{{NS}}}{name}"


@dataclass(frozen=True)
class EventSpec:
    name: str
    source: str
    description: str
    energy: Callable[[dict], float]


@dataclass(frozen=True)
class BlockSpec:
    name: str
    module: str
    rtl_path: str
    power_domain: str
    clock: str
    description: str
    logic_gates: int = 0
    flop_bits: int = 0
    sram_bits: int = 0
    parameters: tuple[tuple[str, str, str], ...] = ()
    events: tuple[EventSpec, ...] = ()
    toggle_bits: int = 0


def op_energy(bits: int, factor: float = 1.0) -> Callable[[dict], float]:
    return lambda tech: tech["energy"]["logic_op_pj_per_bit"] * bits * factor


def const_energy(key: str) -> Callable[[dict], float]:
    return lambda tech: tech["energy"][key]


def decode_energy(tech: dict) -> float:
    return tech["energy"]["decode_pj_per_instruction_bit"] * 16


def reg_read_energy(tech: dict) -> float:
    return tech["energy"]["logic_op_pj_per_bit"] * 32 * 0.45


def reg_write_energy(tech: dict) -> float:
    return tech["energy"]["logic_op_pj_per_bit"] * 32 * 0.65 + tech["energy"]["flop_clock_pj_per_bit"] * 32


BLOCKS: tuple[BlockSpec, ...] = (
    BlockSpec(
        name="fetch_unit",
        module="fetch_unit",
        rtl_path="TOP.mobile_cpu_power_top.u_dut.u_fetch",
        power_domain="PD_CPU",
        clock="core",
        description="Program counter and instruction fetch address generation.",
        logic_gates=90,
        flop_bits=32,
        parameters=(("pc_width", "32", "bit"),),
        events=(
            EventSpec("pc_update", "core_clk_posedge", "PC advances or holds branch target.", op_energy(32, 0.40)),
            EventSpec("branch_redirect", "branch_taken", "Branch target redirects the fetch PC.", op_energy(32, 0.75)),
        ),
        toggle_bits=48,
    ),
    BlockSpec(
        name="instr_rom",
        module="instr_rom",
        rtl_path="TOP.mobile_cpu_power_top.u_dut.u_icache",
        power_domain="PD_CPU",
        clock="none",
        description="Small instruction ROM used as an instruction-cache stand-in.",
        logic_gates=120,
        sram_bits=64 * 16,
        parameters=(("depth", "64", "word"), ("width", "16", "bit")),
        events=(
            EventSpec("instruction_fetch", "instr_addr_sample", "Instruction word read from ROM.", const_energy("rom_read_pj_per_16b")),
        ),
        toggle_bits=64,
    ),
    BlockSpec(
        name="decode_unit",
        module="decode_unit",
        rtl_path="TOP.mobile_cpu_power_top.u_dut.u_decode",
        power_domain="PD_CPU",
        clock="none",
        description="Instruction field extraction and opcode decode.",
        logic_gates=70,
        parameters=(("instruction_width", "16", "bit"),),
        events=(
            EventSpec("decode_instruction", "retired_instruction", "Decode one instruction.", decode_energy),
        ),
        toggle_bits=32,
    ),
    BlockSpec(
        name="regfile",
        module="regfile",
        rtl_path="TOP.mobile_cpu_power_top.u_dut.u_regfile",
        power_domain="PD_CPU",
        clock="core",
        description="Sixteen 32-bit architectural registers with retention behavior.",
        logic_gates=180,
        flop_bits=16 * 32,
        parameters=(("registers", "16", "count"), ("width", "32", "bit")),
        events=(
            EventSpec("read", "rs_read", "One architectural register read.", reg_read_energy),
            EventSpec("write", "wb_en", "One architectural register writeback.", reg_write_energy),
        ),
        toggle_bits=16 * 32,
    ),
    BlockSpec(
        name="execute_unit",
        module="execute_unit",
        rtl_path="TOP.mobile_cpu_power_top.u_dut.u_execute",
        power_domain="PD_CPU",
        clock="none",
        description="ALU, branch, memory request, and WFI control logic.",
        logic_gates=380,
        parameters=(("datapath_width", "32", "bit"),),
        events=(
            EventSpec("alu_add", "opcode.ADD", "ADD operation.", op_energy(32, 1.00)),
            EventSpec("alu_sub", "opcode.SUB", "SUB operation.", op_energy(32, 1.05)),
            EventSpec("alu_and", "opcode.AND", "AND operation.", op_energy(32, 0.42)),
            EventSpec("alu_or", "opcode.OR", "OR operation.", op_energy(32, 0.42)),
            EventSpec("alu_addi", "opcode.ADDI", "ADDI operation.", op_energy(32, 0.92)),
            EventSpec("branch_compare", "opcode.BEQ", "BEQ comparison.", op_energy(32, 0.70)),
            EventSpec("wait_for_interrupt", "opcode.WFI", "WFI idle request.", op_energy(8, 0.20)),
        ),
        toggle_bits=128,
    ),
    BlockSpec(
        name="data_sram",
        module="data_sram",
        rtl_path="TOP.mobile_cpu_power_top.u_dut.u_dmem",
        power_domain="PD_MEM",
        clock="mem",
        description="Small synchronous data SRAM model.",
        logic_gates=120,
        flop_bits=32,
        sram_bits=256 * 32,
        parameters=(("depth", "256", "word"), ("width", "32", "bit")),
        events=(
            EventSpec("read", "mem_req && !mem_we", "Data memory read.", const_energy("sram_read_pj_per_32b")),
            EventSpec("write", "mem_req && mem_we", "Data memory write.", const_energy("sram_write_pj_per_32b")),
        ),
        toggle_bits=96,
    ),
    BlockSpec(
        name="power_controller",
        module="power_controller",
        rtl_path="TOP.mobile_cpu_power_top.u_dut.u_power_controller",
        power_domain="PD_AON",
        clock="top",
        description="Always-on power mode controller for clock gating, power gating, retention, isolation, and DVFS.",
        logic_gates=210,
        flop_bits=6,
        parameters=(("modes", "5", "count"),),
        events=(
            EventSpec("mode_transition", "power_mode_change", "Power state machine transition.", const_energy("mode_transition_pj")),
        ),
        toggle_bits=48,
    ),
)


def leakage_mw(block: BlockSpec, tech: dict) -> float:
    leakage = tech["leakage"]
    n_watts = (
        block.logic_gates * leakage["logic_nw_per_gate"]
        + block.flop_bits * leakage["flop_nw_per_bit"]
        + block.sram_bits * leakage["sram_nw_per_bit"]
    )
    return n_watts / 1_000_000.0


def state_leakage(block: BlockSpec, tech: dict, state: str) -> float:
    base = leakage_mw(block, tech)
    leakage = tech["leakage"]
    if block.power_domain == "PD_AON":
        return base if state in {"RUN", "WAKE"} else base * leakage["idle_factor"]
    if state == "DEEP_SLEEP":
        return base * leakage["power_gated_factor"]
    if state == "LIGHT_SLEEP":
        return base * leakage["retention_factor"]
    if state == "IDLE":
        return base * leakage["idle_factor"]
    return base


def supply_for_domain(block: BlockSpec, state: str) -> str:
    if block.power_domain == "PD_AON":
        return "VDD_AON"
    if block.power_domain == "PD_MEM":
        return "off" if state == "DEEP_SLEEP" else "VDD_MEM"
    if state == "DEEP_SLEEP":
        return "off"
    if state in {"IDLE", "LIGHT_SLEEP"}:
        return "VDD_CPU_LOW"
    return "VDD_CPU_NOM"


def clock_state(block: BlockSpec, state: str) -> str:
    if block.clock == "none":
        return "combinational"
    if state in {"IDLE", "LIGHT_SLEEP", "DEEP_SLEEP"} and block.clock in {"core", "mem"}:
        return "gated"
    return "enabled"


def write_model(block: BlockSpec, tech: dict, out_dir: Path) -> Path:
    root = ET.Element(
        qname("powerModel"),
        {
            "standard": "IEEE2416-2025",
            "schemaVersion": "0.1.0",
            "modelClass": "rtlMacro",
            "abstractionLevel": "rtl",
        },
    )

    metadata = ET.SubElement(root, qname("metadata"))
    ET.SubElement(metadata, qname("name")).text = block.name
    ET.SubElement(metadata, qname("description")).text = block.description
    ET.SubElement(metadata, qname("generator")).text = "tools/characterize_2416.py"
    ET.SubElement(metadata, qname("source")).text = "mobile_cpu RTL example"
    ET.SubElement(metadata, qname("provenance")).text = (
        "Generated from educational technology assumptions and block-level RTL metadata."
    )

    design = ET.SubElement(
        root,
        qname("design"),
        {
            "block": block.name,
            "module": block.module,
            "rtlPath": block.rtl_path,
            "powerDomain": block.power_domain,
            "clock": block.clock,
        },
    )
    for name, value, unit in block.parameters:
        ET.SubElement(design, qname("parameter"), {"name": name, "value": value, "unit": unit})

    oc = ET.SubElement(root, qname("operatingConditions"))
    ET.SubElement(
        oc,
        qname("process"),
        {
            "nodeNm": str(tech["process"]["node_nm"]),
            "corner": tech["process"]["corner"],
        },
    )
    ET.SubElement(oc, qname("temperature"), {"valueC": f'{tech["temperature_c"]:.3f}'})
    for supply, voltage in tech["supplies"].items():
        ET.SubElement(oc, qname("supply"), {"name": supply, "voltageV": f"{voltage:.5f}"})
    for clock in ("top", "core", "mem"):
        ET.SubElement(
            oc,
            qname("clock"),
            {"name": clock, "frequencyMHz": f'{tech["clock_frequency_mhz"]:.3f}'},
        )

    power_states = ET.SubElement(root, qname("powerStates"))
    for state in ("RUN", "IDLE", "LIGHT_SLEEP", "DEEP_SLEEP", "WAKE"):
        ET.SubElement(
            power_states,
            qname("state"),
            {
                "name": state,
                "supply": supply_for_domain(block, state),
                "clock": clock_state(block, state),
                "isolation": str(block.power_domain in {"PD_CPU", "PD_MEM"} and state == "DEEP_SLEEP").lower(),
                "retention": str(block.power_domain in {"PD_CPU", "PD_MEM"} and state in {"LIGHT_SLEEP", "DEEP_SLEEP"}).lower(),
                "leakageMw": f"{state_leakage(block, tech, state):.9f}",
            },
        )

    activity = ET.SubElement(root, qname("activityParameters"))
    if block.clock != "none":
        ET.SubElement(
            activity,
            qname("event"),
            {
                "name": "clock_cycle",
                "source": f"{block.clock}_clock_posedge",
                "description": "One active clock edge for this macro.",
            },
        )
    for event in block.events:
        ET.SubElement(
            activity,
            qname("event"),
            {"name": event.name, "source": event.source, "description": event.description},
        )
    if block.toggle_bits:
        ET.SubElement(
            activity,
            qname("signalActivity"),
            {"name": "rtl_toggles", "source": f"vcd:{block.rtl_path}"},
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
                "value": f"{state_leakage(block, tech, state):.9f}",
                "unit": "mW",
                "voltageScaled": "true",
            },
        )
    if block.clock != "none":
        clock_energy = tech["energy"]["flop_clock_pj_per_bit"] * max(block.flop_bits, 1)
        ET.SubElement(
            components,
            qname("component"),
            {
                "type": "clock",
                "name": "clock_cycle",
                "ref": "clock_cycle",
                "value": f"{clock_energy:.9f}",
                "unit": "pJ",
                "voltageScaled": "true",
            },
        )
    for event in block.events:
        ET.SubElement(
            components,
            qname("component"),
            {
                "type": "event",
                "name": event.name,
                "ref": event.name,
                "value": f"{event.energy(tech):.9f}",
                "unit": "pJ",
                "voltageScaled": "true",
            },
        )
    if block.toggle_bits:
        ET.SubElement(
            components,
            qname("component"),
            {
                "type": "toggle",
                "name": "rtl_toggle",
                "ref": "rtl_toggles",
                "value": f'{tech["energy"]["toggle_pj_per_bit"]:.9f}',
                "unit": "pJ/toggle",
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
                "domain": block.power_domain,
                "driver": f"power_state.{state}",
                "componentRef": f"leakage_{state.lower()}",
                "pvtDependency": "process,voltage,temperature",
                "voltageDependency": "leakageExponent",
                "frequencyDependency": "none",
                "stateDependency": state,
                "workloadDependency": "state_residency_time",
            },
        )
    if block.clock != "none":
        ET.SubElement(
            contributors,
            qname("contributor"),
            {
                "name": "clock_tree_and_register_clocking",
                "type": "clock",
                "domain": block.power_domain,
                "driver": f"{block.clock}_clock_posedge",
                "componentRef": "clock_cycle",
                "pvtDependency": "process,voltage",
                "voltageDependency": "dynamicExponent",
                "frequencyDependency": "active_clock_cycles",
                "stateDependency": "clock_enabled_power_states",
                "workloadDependency": "clock_residency",
            },
        )
    for event in block.events:
        ET.SubElement(
            contributors,
            qname("contributor"),
            {
                "name": f"event_{event.name}",
                "type": "event",
                "domain": block.power_domain,
                "driver": event.source,
                "componentRef": event.name,
                "pvtDependency": "process,voltage",
                "voltageDependency": "dynamicExponent",
                "frequencyDependency": "event_count",
                "stateDependency": "active_domain_power_states",
                "workloadDependency": "instruction_mix_or_transaction_count",
            },
        )
    if block.toggle_bits:
        ET.SubElement(
            contributors,
            qname("contributor"),
            {
                "name": "rtl_signal_toggle_activity",
                "type": "toggle",
                "domain": block.power_domain,
                "driver": f"vcd:{block.rtl_path}",
                "componentRef": "rtl_toggle",
                "pvtDependency": "process,voltage",
                "voltageDependency": "dynamicExponent",
                "frequencyDependency": "observed_toggle_rate",
                "stateDependency": "active_domain_power_states",
                "workloadDependency": "rtl_signal_activity",
            },
        )

    scaling = ET.SubElement(root, qname("scaling"))
    tech_scaling = tech["scaling"]
    ET.SubElement(
        scaling,
        qname("voltage"),
        {
            "referenceV": f'{tech_scaling["reference_voltage_v"]:.5f}',
            "dynamicExponent": f'{tech_scaling["dynamic_voltage_exponent"]:.3f}',
            "leakageExponent": f'{tech_scaling["leakage_voltage_exponent"]:.3f}',
        },
    )
    ET.SubElement(
        scaling,
        qname("temperature"),
        {
            "referenceC": f'{tech_scaling["reference_temperature_c"]:.3f}',
            "leakagePer10cFactor": f'{tech_scaling["leakage_per_10c_factor"]:.3f}',
        },
    )

    validity = ET.SubElement(root, qname("validity"))
    supplies = tech["supplies"].values()
    min_v = min(supplies) * 0.80
    max_v = max(supplies) * 1.15
    ET.SubElement(validity, qname("voltageRange"), {"minV": f"{min_v:.5f}", "maxV": f"{max_v:.5f}"})
    ET.SubElement(validity, qname("temperatureRange"), {"minC": "-40.000", "maxC": "125.000"})

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{block.name}.xml"
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tech", type=Path, default=Path("configs/tech/generic_7nm.json"))
    parser.add_argument("--out", type=Path, default=Path("power_models/mobile_cpu/rtl"))
    args = parser.parse_args()

    tech = json.loads(args.tech.read_text(encoding="utf-8"))
    written = [write_model(block, tech, args.out) for block in BLOCKS]
    for path in written:
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
