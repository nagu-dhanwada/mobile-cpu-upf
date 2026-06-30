#!/usr/bin/env python3
"""Generate a self-contained visual dashboard for mobile CPU power exploration."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


STATE_COLORS = {
    "RUN": "#2f80ed",
    "IDLE": "#56cc9d",
    "LIGHT_SLEEP": "#f2c94c",
    "DEEP_SLEEP": "#9b51e0",
    "WAKE": "#eb5757",
}

DOMAIN_COLORS = {
    "PD_AON": "#6c757d",
    "PD_CPU": "#2f80ed",
    "PD_MEM": "#27ae60",
}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def fmt(value: object, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "0.000"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def report_dir_for(report_root: Path, workload: str, tech: str, scheme: str) -> Path:
    return report_root / f"{workload}_{tech}_{scheme}"


def intent_path_for(intent_root: Path, workload: str) -> Path:
    name = workload.split("/", 1)[1] if workload.startswith("generated/") else workload
    return intent_root / name / "workload_intent.json"


def scheme_path_for(scheme_root: Path, scheme: str) -> Path:
    direct = scheme_root / f"{scheme}.json"
    if direct.exists():
        return direct
    matches = sorted(scheme_root.glob(f"*_{scheme}.json"))
    return matches[0] if matches else direct


def load_case(report_root: Path, intent_root: Path, workload: str, tech: str, scheme: str) -> dict[str, Any]:
    result_dir = report_dir_for(report_root, workload, tech, scheme)
    estimate_path = result_dir / "2416_power_estimate.json"
    profile_path = result_dir / "workload_profile" / "workload_profile.json"
    if not estimate_path.exists():
        raise FileNotFoundError(f"Missing power estimate for {workload}: {estimate_path}")
    if not profile_path.exists():
        raise FileNotFoundError(f"Missing workload profile for {workload}: {profile_path}")

    estimate = load_json(estimate_path)
    profile = load_json(profile_path)
    intent_file = intent_path_for(intent_root, workload)
    intent = load_json(intent_file) if intent_file.exists() else {}
    return {
        "workload": workload,
        "label": workload.split("/")[-1],
        "report_dir": str(result_dir),
        "estimate": estimate,
        "profile": profile,
        "intent": intent,
    }


def load_scheme(scheme_root: Path, scheme: str) -> dict[str, Any]:
    path = scheme_path_for(scheme_root, scheme)
    if not path.exists():
        return {}
    return load_json(path)


def metric(case: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = case["profile"].get(key, case["estimate"].get(key, default))
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def instruction_mix(case: dict[str, Any]) -> list[tuple[str, int]]:
    counts = case["profile"].get("instruction_counts", {})
    return sorted((str(name), int(count)) for name, count in counts.items())


def domain_rows(case: dict[str, Any]) -> list[dict[str, Any]]:
    return list(case["estimate"].get("domains", []))


def dominant_events(case: dict[str, Any], limit: int = 8) -> list[tuple[str, int]]:
    counts = case["estimate"].get("activity", {}).get("event_counts", {})
    rows = sorted(((str(name), int(count)) for name, count in counts.items()), key=lambda row: row[1], reverse=True)
    return rows[:limit]


def event_count(case: dict[str, Any], key: str) -> int:
    return int(case["estimate"].get("activity", {}).get("event_counts", {}).get(key, 0))


def instruction_count(case: dict[str, Any], key: str) -> int:
    return int(case["profile"].get("instruction_counts", {}).get(key, 0))


def block_total(case: dict[str, Any], block: str) -> float:
    for row in case["estimate"].get("blocks", []):
        if row.get("block") == block:
            return float(row.get("total_pj", 0.0))
    return 0.0


def domain_total(case: dict[str, Any], domain: str) -> float:
    for row in case["estimate"].get("domains", []):
        if row.get("domain") == domain:
            return float(row.get("total_pj", 0.0))
    return 0.0


def pct(part: float, total: float) -> float:
    return part / total * 100.0 if total else 0.0


def compact_workload_id(workload: str) -> str:
    return workload.replace("/", "_").replace("-", "_")


def severity_for(value: float, medium: float, high: float) -> str:
    if value >= high:
        return "high"
    if value >= medium:
        return "medium"
    return "low"


def card(
    *,
    card_id: str,
    card_type: str,
    severity: str,
    workload: str,
    block: str,
    rtl_hierarchy: str,
    observation: str,
    evidence: dict[str, Any],
    root_cause_class: str,
    suggested_design_change: str,
    expected_benefit: str,
    design_risk: str,
    verification_plan: list[str],
    before_metrics: dict[str, Any],
    after_metrics: dict[str, Any],
    next_rtl_change: str,
) -> dict[str, Any]:
    return {
        "card_id": card_id,
        "card_type": card_type,
        "severity": severity,
        "workload": workload,
        "block": block,
        "rtl_hierarchy": rtl_hierarchy,
        "observation": observation,
        "evidence": evidence,
        "root_cause_class": root_cause_class,
        "suggested_design_change": suggested_design_change,
        "expected_benefit": expected_benefit,
        "design_risk": design_risk,
        "verification_plan": verification_plan,
        "before_metrics": before_metrics,
        "after_metrics": after_metrics,
        "next_rtl_change": next_rtl_change,
    }


def generate_power_optimization_cards(cases: list[dict[str, Any]], scheme_name: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for case in cases:
        workload = case["workload"]
        wid = compact_workload_id(workload)
        retired = metric(case, "retired_instruction_count")
        useful = metric(case, "useful_instruction_count")
        total_energy = metric(case, "total_energy_pj")
        macs = metric(case, "dataflow_mac_count")
        stores = instruction_count(case, "ST")
        loads = instruction_count(case, "LD")
        memory_intensity = metric(case, "memory_intensity")
        mmio_requests = event_count(case, "data_bus_interconnect.mmio_route")
        operand_writes = event_count(case, "dataflow_unit.operand_write")
        command_writes = event_count(case, "dataflow_unit.command_write")
        result_reads = event_count(case, "dataflow_unit.result_read")
        status_reads = event_count(case, "dataflow_unit.status_read")
        control_per_mac = mmio_requests / macs if macs else 0.0

        if macs > 0 and (control_per_mac >= 3.0 or memory_intensity >= 0.35):
            cards.append(
                card(
                    card_id=f"dataflow-offload-amortization-{wid}",
                    card_type="dataflow_offload_amortization",
                    severity=severity_for(control_per_mac, 3.0, 4.0),
                    workload=workload,
                    block="dataflow_unit",
                    rtl_hierarchy="TOP.mobile_cpu_power_top.u_dut.u_dataflow",
                    observation=(
                        f"{case['label']} performs {fmt(macs, 0)} dataflow MACs but still issues "
                        f"{mmio_requests} dataflow MMIO requests ({fmt(control_per_mac, 2)} per MAC)."
                    ),
                    evidence={
                        "dataflow_mac_count": macs,
                        "store_instructions": stores,
                        "load_instructions": loads,
                        "dataflow_mmio_requests": mmio_requests,
                        "operand_writes": operand_writes,
                        "command_writes": command_writes,
                        "result_reads": result_reads,
                        "status_reads": status_reads,
                        "control_requests_per_mac": round(control_per_mac, 3),
                        "memory_intensity": round(memory_intensity, 3),
                    },
                    root_cause_class="offload_control_amortization",
                    suggested_design_change=(
                        "Move from MMIO-per-operation toward a descriptor or repeat-count path: CPU writes "
                        "operands/count/descriptor once, then issues one doorbell while the dataflow block does local work."
                    ),
                    expected_benefit=(
                        "Reduce MMIO requests, LSU stalls, and register-file traffic per useful MAC; target "
                        "control_requests_per_mac below 1.0 for repeated or descriptor-friendly kernels."
                    ),
                    design_risk=(
                        "Descriptor sequencing adds state, ordering, and interrupt/status corner cases; a repeat-count-only "
                        "path helps constant operands but not streamed operands."
                    ),
                    verification_plan=[
                        "Run dataflow_mac and generated/dataflow_energy_probe before and after the change.",
                        "Check accumulator correctness for single, clear-and-start, and repeated MAC cases.",
                        "Assert one command doorbell cannot launch duplicate descriptors.",
                        "Compare control_requests_per_mac and load_store_unit.stall_cycle in the visual story cards.",
                    ],
                    before_metrics={
                        "control_requests_per_mac": round(control_per_mac, 3),
                        "dataflow_mmio_requests": mmio_requests,
                        "memory_intensity": round(memory_intensity, 3),
                    },
                    after_metrics={
                        "target_control_requests_per_mac": "<= 1.0",
                        "target_mmio_requests": "one descriptor/doorbell per burst",
                    },
                    next_rtl_change="Add a tiny descriptor/repeat command path beside the existing offsets 4-7.",
                )
            )

        lsu_stalls = event_count(case, "load_store_unit.stall_cycle")
        stall_per_instruction = lsu_stalls / retired if retired else 0.0
        if lsu_stalls >= 20 or stall_per_instruction >= 0.75:
            cards.append(
                card(
                    card_id=f"lsu-stall-energy-{wid}",
                    card_type="lsu_stall_energy",
                    severity=severity_for(lsu_stalls, 20.0, 50.0),
                    workload=workload,
                    block="load_store_unit",
                    rtl_hierarchy="TOP.mobile_cpu_power_top.u_dut.u_lsu",
                    observation=(
                        f"{case['label']} spends {lsu_stalls} cycles stalled on the single-outstanding LSU "
                        f"({fmt(stall_per_instruction, 2)} stalls per retired instruction)."
                    ),
                    evidence={
                        "lsu_stall_cycles": lsu_stalls,
                        "retired_instructions": retired,
                        "stall_cycles_per_retired_instruction": round(stall_per_instruction, 3),
                        "load_store_requests": event_count(case, "load_store_unit.request_issue"),
                        "load_store_responses": event_count(case, "load_store_unit.response_complete"),
                        "lsu_energy_pj": round(block_total(case, "load_store_unit"), 3),
                    },
                    root_cause_class="memory_latency_backpressure",
                    suggested_design_change=(
                        "Make stalls explicit clock-enable boundaries: freeze fetch/decode/execute state while the LSU waits, "
                        "and let only the LSU/interconnect response tracking remain active."
                    ),
                    expected_benefit=(
                        "Lower front-end clock and combinational toggle energy during memory wait states; benefits scale with "
                        "stall_cycle count."
                    ),
                    design_risk=(
                        "Incorrect stall release can replay stores, drop load writeback, or retire the same instruction twice."
                    ),
                    verification_plan=[
                        "Keep load_store_unit_tb no-duplicate-request and delayed-response tests.",
                        "Run memory_burst, dataflow_mac, and generated/dataflow_energy_probe VCD simulations.",
                        "Check retired instruction counts and memory/MMIO request counts stay unchanged.",
                    ],
                    before_metrics={
                        "lsu_stall_cycles": lsu_stalls,
                        "stall_cycles_per_retired_instruction": round(stall_per_instruction, 3),
                    },
                    after_metrics={
                        "target_frontend_ce_during_stall": 0,
                        "target_duplicate_requests": 0,
                    },
                    next_rtl_change="Convert stall into explicit fetch_ce/decode_ce/execute_ce boundaries and assert no replay.",
                )
            )

        fetch_stall = event_count(case, "fetch_unit.stall_valid_cycle")
        decode_stall = event_count(case, "decode_unit.stall_valid_cycle")
        execute_stall = event_count(case, "execute_unit.stall_valid_cycle")
        rom_stall = event_count(case, "instr_rom.stall_hold_cycle")
        fetch_ce = event_count(case, "fetch_unit.fetch_ce_cycle")
        decode_ce = event_count(case, "decode_unit.decode_ce_cycle")
        execute_ce = event_count(case, "execute_unit.execute_ce_cycle")
        frontend_stall_valid = fetch_stall + decode_stall + execute_stall
        if lsu_stalls > 0 and frontend_stall_valid > 0:
            cards.append(
                card(
                    card_id=f"front-end-wasted-toggle-{wid}",
                    card_type="front_end_wasted_toggle",
                    severity=severity_for(frontend_stall_valid, 40.0, 120.0),
                    workload=workload,
                    block="fetch/decode/execute",
                    rtl_hierarchy="TOP.mobile_cpu_power_top.u_dut.{u_fetch,u_icache,u_decode,u_execute}",
                    observation=(
                        f"During LSU stalls, valid front-end work is held for {frontend_stall_valid} stage-cycles; "
                        f"the instruction ROM address is held for {rom_stall} stall cycles."
                    ),
                    evidence={
                        "fetch_stall_valid_cycles": fetch_stall,
                        "decode_stall_valid_cycles": decode_stall,
                        "execute_stall_valid_cycles": execute_stall,
                        "instr_rom_stall_hold_cycles": rom_stall,
                        "fetch_ce_cycles": fetch_ce,
                        "decode_ce_cycles": decode_ce,
                        "execute_ce_cycles": execute_ce,
                        "lsu_stall_cycles": lsu_stalls,
                    },
                    root_cause_class="front_end_backpressure_toggle",
                    suggested_design_change=(
                        "Add real valid-gated stage registers around fetch/decode/execute and gate instruction ROM read "
                        "enable whenever stall_fetch is asserted."
                    ),
                    expected_benefit=(
                        "Turn stall windows into clock-enable-off windows for PC, decode, and execute operand/control state; "
                        "the immediate target is zero fetch/decode/execute CE cycles while stalled."
                    ),
                    design_risk=(
                        "A valid-gated front end can hide bugs in branch redirect, WFI, and load writeback ordering if stall "
                        "priority is not specified."
                    ),
                    verification_plan=[
                        "Add assertions that PC and instruction word are stable while stall_fetch is high.",
                        "Run branch and WFI workloads with delayed LSU responses.",
                        "Compare fetch_ce/decode_ce/execute_ce cycles and instruction counts before/after.",
                    ],
                    before_metrics={
                        "frontend_stall_valid_stage_cycles": frontend_stall_valid,
                        "instr_rom_stall_hold_cycles": rom_stall,
                    },
                    after_metrics={
                        "target_ce_cycles_while_stalled": 0,
                        "target_instruction_count_delta": 0,
                    },
                    next_rtl_change="Introduce stage-valid flops and ROM read-enable gating driven by stall_fetch.",
                )
            )

        busy_cycles = event_count(case, "dataflow_unit.busy_cycle")
        idle_cycles = event_count(case, "dataflow_unit.idle_cycle")
        mac_active_cycles = event_count(case, "dataflow_unit.mac_active_cycle")
        ctrl_ce_cycles = event_count(case, "dataflow_unit.ctrl_ce_cycle")
        mac_ce_cycles = event_count(case, "dataflow_unit.mac_ce_cycle")
        utilization = mac_active_cycles / (busy_cycles + idle_cycles) if (busy_cycles + idle_cycles) else 0.0
        if macs > 0 and idle_cycles > max(10, mac_active_cycles * 4):
            cards.append(
                card(
                    card_id=f"dataflow-clock-gating-{wid}",
                    card_type="dataflow_clock_gating_opportunity",
                    severity=severity_for(1.0 - utilization, 0.80, 0.95),
                    workload=workload,
                    block="dataflow_unit",
                    rtl_hierarchy="TOP.mobile_cpu_power_top.u_dut.u_dataflow",
                    observation=(
                        f"Dataflow MAC activity is sparse: {mac_active_cycles} MAC-active cycles versus "
                        f"{idle_cycles} idle-but-clocked memory-domain cycles."
                    ),
                    evidence={
                        "dataflow_busy_cycles": busy_cycles,
                        "dataflow_idle_cycles": idle_cycles,
                        "dataflow_mac_active_cycles": mac_active_cycles,
                        "dataflow_ctrl_ce_cycles": ctrl_ce_cycles,
                        "dataflow_mac_ce_cycles": mac_ce_cycles,
                        "mac_active_utilization": round(utilization, 4),
                        "dataflow_energy_pj": round(block_total(case, "dataflow_unit"), 3),
                    },
                    root_cause_class="accelerator_idle_clocking",
                    suggested_design_change=(
                        "Split dataflow clock enables: control_ce = mmio_access || busy || status_read, "
                        "and mac_ce = mac_active. Keep MMIO/status logic alive separately from the multiplier datapath."
                    ),
                    expected_benefit=(
                        "Reduce MAC datapath clock/toggle energy during long idle and MMIO-only windows without blocking status reads."
                    ),
                    design_risk=(
                        "Over-gating can make done/status updates late or hide accumulator state from software reads."
                    ),
                    verification_plan=[
                        "Run dataflow_unit_tb for single, clear-start, held command, and repeat-count modes.",
                        "Check status reads work when MAC datapath clock enable is off.",
                        "Compare dataflow_mac_ce_cycles against dataflow_mac_active_cycles after the split.",
                    ],
                    before_metrics={
                        "mac_active_utilization": round(utilization, 4),
                        "idle_cycles": idle_cycles,
                        "mac_active_cycles": mac_active_cycles,
                    },
                    after_metrics={
                        "target_mac_ce_cycles": "approximately mac_active_cycles",
                        "target_status_read_failures": 0,
                    },
                    next_rtl_change="Add separate control and MAC datapath clock-enable terms inside dataflow_unit.",
                )
            )

        cpu_energy = domain_total(case, "PD_CPU")
        mem_energy = domain_total(case, "PD_MEM")
        total_domain_energy = sum(float(row.get("total_pj", 0.0)) for row in domain_rows(case))
        dataflow_energy = block_total(case, "dataflow_unit")
        cpu_share = pct(cpu_energy, total_domain_energy)
        dataflow_share = pct(dataflow_energy, total_domain_energy)
        if macs > 0 and cpu_share >= 50.0:
            cards.append(
                card(
                    card_id=f"power-domain-decision-{wid}",
                    card_type="power_domain_decision",
                    severity="medium",
                    workload=workload,
                    block="power domains",
                    rtl_hierarchy="PD_CPU/PD_MEM around u_lsu, u_dbus, u_dataflow",
                    observation=(
                        f"PD_CPU still dominates this dataflow workload at {fmt(cpu_share, 1)}% of domain energy; "
                        f"the dataflow block itself is {fmt(dataflow_share, 1)}%."
                    ),
                    evidence={
                        "PD_CPU_energy_pj": round(cpu_energy, 3),
                        "PD_MEM_energy_pj": round(mem_energy, 3),
                        "PD_CPU_energy_share_percent": round(cpu_share, 2),
                        "dataflow_unit_energy_pj": round(dataflow_energy, 3),
                        "dataflow_unit_energy_share_percent": round(dataflow_share, 2),
                        "scheme": scheme_name,
                    },
                    root_cause_class="premature_domain_partitioning",
                    suggested_design_change=(
                        "Do not split a separate dataflow power domain yet. First reduce CPU/LSU/MMIO control overhead and "
                        "front-end stall activity, then re-evaluate domain partitioning with lower CPU share."
                    ),
                    expected_benefit=(
                        "Avoid adding isolation, retention, wake latency, and verification cost before the dominant energy source "
                        "has moved into the accelerator domain."
                    ),
                    design_risk=(
                        "Waiting too long can miss floorplan or power-grid planning windows, so keep a placeholder domain plan."
                    ),
                    verification_plan=[
                        "Track PD_CPU energy share across cpu_mac, dataflow_mac, and generated/dataflow_energy_probe.",
                        "Re-run visual-story after descriptor and dataflow clock-gating changes.",
                        "Promote a separate dataflow domain only when dataflow energy or leakage becomes dominant.",
                    ],
                    before_metrics={
                        "PD_CPU_energy_share_percent": round(cpu_share, 2),
                        "dataflow_unit_energy_share_percent": round(dataflow_share, 2),
                    },
                    after_metrics={
                        "decision_threshold": "revisit when PD_CPU share is below 45% or dataflow leakage dominates idle",
                    },
                    next_rtl_change="Keep dataflow in the current domain while optimizing MMIO/control traffic first.",
                )
            )

    return cards


def build_summary_cards(cases: list[dict[str, Any]]) -> str:
    cards: list[str] = []
    for case in cases:
        intent = case.get("intent", {})
        profile_name = intent.get("resolved_intent", {}).get("profile", "hand-written")
        macs = metric(case, "dataflow_mac_count")
        energy = metric(case, "total_energy_pj")
        useful = metric(case, "energy_per_useful_instruction_pj")
        recovery = metric(case, "recovery_energy_percent")
        memory = metric(case, "memory_intensity")
        wfi = metric(case, "wfi_density")
        rows = "".join(
            f"<li><span>{esc(name)}</span><strong>{count}</strong></li>"
            for name, count in instruction_mix(case)
        )
        cards.append(
            f"""
            <article class="workload-card">
              <div class="card-title">
                <h3>{esc(case["label"])}</h3>
                <span>{esc(profile_name)}</span>
              </div>
              <div class="metric-grid">
                <div><b>{fmt(energy, 2)}</b><span>pJ total</span></div>
                <div><b>{fmt(useful, 2)}</b><span>pJ/useful instr</span></div>
                <div><b>{fmt(macs, 0)}</b><span>dataflow MACs</span></div>
                <div><b>{fmt(recovery, 1)}%</b><span>recovery energy</span></div>
                <div><b>{fmt(memory, 3)}</b><span>memory intensity</span></div>
                <div><b>{fmt(wfi, 3)}</b><span>WFI density</span></div>
              </div>
              <ul class="instruction-list">{rows}</ul>
            </article>
            """
        )
    return "\n".join(cards)


def build_tradeoff_chart(cases: list[dict[str, Any]], key: str, title: str, unit: str, color: str) -> str:
    width = 860
    height = 300
    left = 76
    right = 24
    top = 44
    bottom = 78
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [metric(case, key) for case in cases]
    max_value = max(values) * 1.15 if values and max(values) else 1.0
    gap = 22
    bar_w = max(34, (plot_w - gap * (len(cases) + 1)) / max(len(cases), 1))

    def y(value: float) -> float:
        return top + plot_h - (value / max_value) * plot_h

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        f'<text x="24" y="28" class="chart-title">{esc(title)}</text>',
    ]
    for idx in range(5):
        value = max_value * idx / 4
        yy = y(value)
        parts.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{width - right}" y2="{yy:.2f}" class="grid-line"/>')
        parts.append(f'<text x="{left - 8}" y="{yy + 4:.2f}" text-anchor="end" class="axis-label">{fmt(value, 1)}</text>')
    parts.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{width - right}" y2="{top + plot_h}" class="axis-line"/>')
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" class="axis-line"/>')

    for idx, case in enumerate(cases):
        value = values[idx]
        x = left + gap + idx * (bar_w + gap)
        yy = y(value)
        parts.append(
            f'<rect x="{x:.2f}" y="{yy:.2f}" width="{bar_w:.2f}" height="{top + plot_h - yy:.2f}" '
            f'fill="{color}" opacity="0.88" rx="5"/>'
        )
        parts.append(f'<text x="{x + bar_w / 2:.2f}" y="{yy - 7:.2f}" text-anchor="middle" class="value-label">{fmt(value, 2)} {esc(unit)}</text>')
        parts.append(
            f'<text x="{x + bar_w / 2:.2f}" y="{top + plot_h + 21}" text-anchor="middle" '
            f'class="axis-label rotate-label" transform="rotate(25 {x + bar_w / 2:.2f} {top + plot_h + 21})">{esc(case["label"])}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def build_domain_chart(case: dict[str, Any]) -> str:
    rows = domain_rows(case)
    total = sum(float(row.get("total_pj", 0.0)) for row in rows) or 1.0
    segments: list[str] = []
    x = 0.0
    for row in rows:
        domain = str(row.get("domain", ""))
        energy = float(row.get("total_pj", 0.0))
        width = energy / total * 100.0
        color = DOMAIN_COLORS.get(domain, "#888")
        segments.append(f'<span style="width:{width:.2f}%;background:{color}" title="{esc(domain)} {fmt(energy, 2)} pJ"></span>')
        x += width
    labels = "".join(
        f'<li><i style="background:{DOMAIN_COLORS.get(str(row.get("domain", "")), "#888")}"></i>{esc(row.get("domain", ""))}: {fmt(row.get("total_pj", 0.0), 2)} pJ</li>'
        for row in rows
    )
    return f'<div class="domain-stack">{ "".join(segments) }</div><ul class="legend compact">{labels}</ul>'


def build_datapath_animation() -> str:
    return """
    <svg class="datapath" viewBox="0 0 980 360" role="img" aria-label="Animated CPU datapath">
      <defs>
        <marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
          <path d="M0,0 L10,4 L0,8 Z" fill="#506070"/>
        </marker>
      </defs>
      <rect x="28" y="42" width="130" height="72" rx="8" class="block aon"/>
      <text x="93" y="83" text-anchor="middle">power_controller</text>
      <rect x="210" y="42" width="120" height="72" rx="8" class="block cpu"/>
      <text x="270" y="83" text-anchor="middle">fetch</text>
      <rect x="372" y="42" width="120" height="72" rx="8" class="block cpu"/>
      <text x="432" y="83" text-anchor="middle">instr_rom</text>
      <rect x="210" y="152" width="120" height="72" rx="8" class="block cpu"/>
      <text x="270" y="193" text-anchor="middle">decode</text>
      <rect x="372" y="152" width="120" height="72" rx="8" class="block cpu"/>
      <text x="432" y="193" text-anchor="middle">regfile</text>
      <rect x="534" y="152" width="108" height="72" rx="8" class="block cpu"/>
      <text x="588" y="193" text-anchor="middle">execute</text>
      <rect x="674" y="152" width="96" height="72" rx="8" class="block cpu"/>
      <text x="722" y="193" text-anchor="middle">LSU</text>
      <rect x="802" y="152" width="104" height="72" rx="8" class="block mem"/>
      <text x="854" y="193" text-anchor="middle">data bus</text>
      <rect x="802" y="48" width="130" height="72" rx="8" class="block mem"/>
      <text x="867" y="89" text-anchor="middle">data_sram</text>
      <rect x="802" y="256" width="130" height="72" rx="8" class="block cpu"/>
      <text x="867" y="297" text-anchor="middle">dataflow_unit</text>
      <path d="M330,78 H372" class="edge"/>
      <path d="M432,114 V132 C432,145 330,137 302,152" class="edge"/>
      <path d="M330,188 H372" class="edge"/>
      <path d="M492,188 H534" class="edge"/>
      <path d="M642,188 H674" class="edge"/>
      <path d="M770,188 H802" class="edge"/>
      <path d="M854,152 C854,124 858,102 867,120" class="edge"/>
      <path d="M854,224 C854,246 858,270 867,256" class="edge"/>
      <path d="M158,78 H210" class="edge dashed"/>
      <circle r="8" class="packet packet-fetch"><animateMotion dur="4.8s" repeatCount="indefinite" path="M270,78 H432 V114 V132 C432,145 330,137 302,152 H270"/></circle>
      <circle r="8" class="packet packet-exec"><animateMotion dur="4.8s" repeatCount="indefinite" begin="1.0s" path="M270,188 H432 H588"/></circle>
      <circle r="8" class="packet packet-mem"><animateMotion dur="4.8s" repeatCount="indefinite" begin="2.1s" path="M588,188 H722 H854 C854,124 858,102 867,84"/></circle>
      <circle r="8" class="packet packet-df"><animateMotion dur="4.8s" repeatCount="indefinite" begin="2.8s" path="M588,188 H722 H854 C854,246 858,270 867,292"/></circle>
      <text x="28" y="344" class="caption">Packets show instruction fetch/decode/execute, LSU request/response traffic, SRAM access, and MMIO offload into the dataflow MAC unit.</text>
    </svg>
    """


def build_power_timeline(case: dict[str, Any]) -> str:
    timeline = case["estimate"].get("power_timeline", [])
    if not timeline:
        return '<p class="muted">No power timeline found.</p>'
    duration = max(float(row.get("end_ns", 0.0)) for row in timeline) or 1.0
    max_power = max(float(row.get("total_mw", 0.0)) for row in timeline) or 1.0
    width = 980
    height = 260
    left = 64
    right = 24
    top = 34
    plot_h = 140
    plot_w = width - left - right
    band_y = top + plot_h + 28

    def x(value: float) -> float:
        return left + (value / duration) * plot_w

    def y(value: float) -> float:
        return top + plot_h - (value / (max_power * 1.15)) * plot_h

    parts = [
        f'<svg class="timeline" viewBox="0 0 {width} {height}" role="img" aria-label="Animated power timeline for {esc(case["label"])}">',
        f'<text x="22" y="23" class="chart-title">Power timeline: {esc(case["label"])}</text>',
    ]
    for row in timeline:
        x0 = x(float(row.get("start_ns", 0.0)))
        x1 = x(float(row.get("end_ns", 0.0)))
        base = 0.0
        for domain, color in DOMAIN_COLORS.items():
            value = float(row.get(f"{domain}_mw", 0.0))
            yy0 = y(base)
            yy1 = y(base + value)
            parts.append(
                f'<rect x="{x0:.2f}" y="{yy1:.2f}" width="{max(x1 - x0, 0.7):.2f}" '
                f'height="{max(yy0 - yy1, 0.0):.2f}" fill="{color}" opacity="0.8"/>'
            )
            base += value
    for row in timeline:
        x0 = x(float(row.get("start_ns", 0.0)))
        x1 = x(float(row.get("end_ns", 0.0)))
        state = str(row.get("state", ""))
        color = STATE_COLORS.get(state, "#ddd")
        parts.append(f'<rect x="{x0:.2f}" y="{band_y}" width="{max(x1 - x0, 0.7):.2f}" height="24" fill="{color}" opacity="0.9"/>')
    parts.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{width - right}" y2="{top + plot_h}" class="axis-line"/>')
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" class="axis-line"/>')
    parts.append(f'<line class="timeline-cursor" x1="{left}" y1="{top - 10}" x2="{left}" y2="{band_y + 32}"/>')
    parts.append(f'<text x="{left}" y="{band_y + 50}" class="axis-label">0 ns</text>')
    parts.append(f'<text x="{width - right}" y="{band_y + 50}" text-anchor="end" class="axis-label">{fmt(duration, 1)} ns</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def build_event_table(case: dict[str, Any]) -> str:
    rows = dominant_events(case)
    body = "".join(f"<tr><td>{esc(name)}</td><td>{count}</td></tr>" for name, count in rows)
    return f"""
    <table>
      <thead><tr><th>Dominant event</th><th>Count</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
    """


def render_evidence(evidence: dict[str, Any]) -> str:
    rows = "".join(
        f"<li><span>{esc(key)}</span><strong>{esc(value)}</strong></li>"
        for key, value in evidence.items()
    )
    return f"<ul class=\"evidence-list\">{rows}</ul>"


def render_verification(items: list[str]) -> str:
    return "".join(f"<li>{esc(item)}</li>" for item in items)


def build_optimization_cards_html(cards: list[dict[str, Any]]) -> str:
    if not cards:
        return """
        <section class="panel">
          <h2>Designer Optimization Cards</h2>
          <p class="muted">No optimization cards were triggered by the current workloads and thresholds.</p>
        </section>
        """
    body: list[str] = []
    for item in cards:
        body.append(
            f"""
            <article class="optimization-card severity-{esc(item['severity'])}">
              <div class="optimization-head">
                <div>
                  <h3>{esc(item['card_type'].replace('_', ' ').title())}</h3>
                  <p>{esc(item['workload'])} · {esc(item['block'])}</p>
                </div>
                <span>{esc(item['severity'])}</span>
              </div>
              <dl>
                <dt>Finding</dt>
                <dd>{esc(item['observation'])}</dd>
                <dt>Where</dt>
                <dd><code>{esc(item['rtl_hierarchy'])}</code></dd>
                <dt>Evidence</dt>
                <dd>{render_evidence(item.get('evidence', {}))}</dd>
                <dt>Recommendation</dt>
                <dd>{esc(item['suggested_design_change'])}</dd>
                <dt>Expected Benefit</dt>
                <dd>{esc(item['expected_benefit'])}</dd>
                <dt>Risk</dt>
                <dd>{esc(item['design_risk'])}</dd>
                <dt>Verification</dt>
                <dd><ul>{render_verification(item.get('verification_plan', []))}</ul></dd>
                <dt>Next RTL Change</dt>
                <dd>{esc(item.get('next_rtl_change', ''))}</dd>
              </dl>
            </article>
            """
        )
    return f"""
    <section>
      <h2>Designer Optimization Cards</h2>
      <p class="muted">These cards translate workload and IEEE 2416 activity into concrete RTL/microarchitecture actions. They are generated into <code>power_optimization_cards.json</code> beside this page.</p>
      <div class="optimization-grid">{''.join(body)}</div>
    </section>
    """


def build_scheme_summary(scheme: dict[str, Any], scheme_name: str) -> str:
    if not scheme:
        return f"<p>Scheme metadata for <code>{esc(scheme_name)}</code> was not found, but the report data still carries the applied scheme name.</p>"
    states = scheme.get("power_states", scheme.get("states", []))
    domains = scheme.get("domains", [])
    methodology = scheme.get("methodology", {})
    methodology_sections: list[str] = []
    for title, key in (
        ("Implemented In RTL", "gated_in_rtl"),
        ("Estimated Behavior", "estimated_behavior"),
        ("Designer Use", "designer_use"),
    ):
        values = methodology.get(key, [])
        if values:
            rows = "".join(f"<li>{esc(value)}</li>" for value in values)
            methodology_sections.append(f"<h3>{esc(title)}</h3><ul class=\"scheme-list\">{rows}</ul>")
    notes = scheme.get("notes", [])
    note_html = ""
    if notes:
        note_rows = "".join(f"<li>{esc(note)}</li>" for note in notes)
        note_html = f"<h3>Notes</h3><ul class=\"scheme-list\">{note_rows}</ul>"
    return f"""
    <div class="scheme-summary">
      <p><strong>{esc(scheme.get("name", scheme_name))}</strong>: {esc(scheme.get("description", "Power scheme metadata"))}</p>
      <p>{len(domains)} domains, {len(states)} power states, with the simulation harness checking power-domain legality, isolation, retention, DVFS requests, and level-shifter coverage.</p>
      {''.join(methodology_sections)}
      {note_html}
    </div>
    """


def html_document(
    cases: list[dict[str, Any]],
    scheme: dict[str, Any],
    optimization_cards: list[dict[str, Any]],
    tech: str,
    scheme_name: str,
) -> str:
    if not cases:
        raise ValueError("At least one workload case is required")
    primary = cases[0]
    energy_chart = build_tradeoff_chart(cases, "total_energy_pj", "Total Energy By Workload", "pJ", "#2f80ed")
    useful_chart = build_tradeoff_chart(cases, "energy_per_useful_instruction_pj", "Energy Per Useful Instruction", "pJ", "#27ae60")
    recovery_chart = build_tradeoff_chart(cases, "recovery_energy_percent", "Recovery Energy Share", "%", "#eb5757")
    cards = build_summary_cards(cases)
    domain_sections = "\n".join(
        f"<article class=\"domain-card\"><h3>{esc(case['label'])}</h3>{build_domain_chart(case)}</article>"
        for case in cases
    )
    event_sections = "\n".join(
        f"<article class=\"event-card\"><h3>{esc(case['label'])}</h3>{build_event_table(case)}</article>"
        for case in cases
    )
    optimization_section = build_optimization_cards_html(optimization_cards)
    states = "".join(
        f'<li><i style="background:{color}"></i>{esc(state)}</li>'
        for state, color in STATE_COLORS.items()
    )
    domains = "".join(
        f'<li><i style="background:{color}"></i>{esc(domain)}</li>'
        for domain, color in DOMAIN_COLORS.items()
    )
    case_json = json.dumps(
        [
            {
                "workload": case["workload"],
                "energy_pj": metric(case, "total_energy_pj"),
                "average_power_mw": metric(case, "average_power_mw"),
                "dataflow_macs": metric(case, "dataflow_mac_count"),
                "memory_intensity": metric(case, "memory_intensity"),
            }
            for case in cases
        ],
        indent=2,
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mobile CPU Visual Power Story</title>
  <style>
    :root {{
      --ink: #17202a;
      --muted: #5d6d7e;
      --line: #d8dee9;
      --panel: #ffffff;
      --soft: #f5f7fb;
      --aon: {DOMAIN_COLORS["PD_AON"]};
      --cpu: {DOMAIN_COLORS["PD_CPU"]};
      --mem: {DOMAIN_COLORS["PD_MEM"]};
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #eef2f7;
      line-height: 1.5;
    }}
    header {{
      padding: 34px max(28px, calc((100vw - 1180px) / 2)) 26px;
      background: #102033;
      color: white;
    }}
    header p {{ max-width: 820px; color: #dce6f2; margin: 8px 0 0; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    section {{ margin: 0 0 28px; }}
    h1, h2, h3 {{ margin: 0; letter-spacing: 0; }}
    h1 {{ font-size: 34px; }}
    h2 {{ font-size: 23px; margin-bottom: 12px; }}
    h3 {{ font-size: 16px; }}
    code {{ background: #e9edf5; padding: 2px 5px; border-radius: 4px; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
      box-shadow: 0 10px 26px rgba(16, 32, 51, 0.06);
    }}
    .two-col {{ display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.6fr); gap: 18px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }}
    .workload-card, .domain-card, .event-card {{
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .card-title {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }}
    .card-title span {{ color: var(--muted); font-size: 12px; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 14px 0; }}
    .metric-grid div {{ background: var(--soft); border-radius: 6px; padding: 10px; min-height: 68px; }}
    .metric-grid b {{ display: block; font-size: 18px; }}
    .metric-grid span {{ color: var(--muted); font-size: 12px; }}
    .instruction-list, .legend {{ list-style: none; padding: 0; margin: 0; }}
    .instruction-list li {{ display: flex; justify-content: space-between; border-top: 1px solid #edf0f5; padding: 5px 0; font-size: 13px; }}
    .scheme-list {{ margin: 7px 0 12px; padding-left: 18px; color: var(--muted); font-size: 13px; }}
    .optimization-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 16px; }}
    .optimization-card {{
      background: #fff;
      border: 1px solid var(--line);
      border-left: 5px solid #8a98aa;
      border-radius: 8px;
      padding: 16px;
    }}
    .optimization-card.severity-high {{ border-left-color: #d64545; }}
    .optimization-card.severity-medium {{ border-left-color: #f2994a; }}
    .optimization-card.severity-low {{ border-left-color: #2f80ed; }}
    .optimization-head {{ display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }}
    .optimization-head p {{ margin: 4px 0 0; color: var(--muted); font-size: 12px; }}
    .optimization-head span {{ text-transform: uppercase; font-size: 11px; font-weight: 700; color: #fff; background: #64748b; border-radius: 999px; padding: 4px 8px; }}
    .severity-high .optimization-head span {{ background: #d64545; }}
    .severity-medium .optimization-head span {{ background: #c26a12; }}
    .severity-low .optimization-head span {{ background: #2f80ed; }}
    .optimization-card dl {{ margin: 12px 0 0; }}
    .optimization-card dt {{ margin-top: 10px; font-size: 12px; color: var(--muted); font-weight: 700; text-transform: uppercase; }}
    .optimization-card dd {{ margin: 3px 0 0; }}
    .optimization-card ul {{ margin: 4px 0 0; padding-left: 18px; }}
    .evidence-list {{ list-style: none; padding: 0 !important; margin: 4px 0 0 !important; }}
    .evidence-list li {{ display: flex; justify-content: space-between; gap: 10px; border-top: 1px solid #edf0f5; padding: 4px 0; font-size: 12px; }}
    .evidence-list span {{ color: var(--muted); }}
    .datapath, .timeline, .chart {{ width: 100%; height: auto; display: block; }}
    .block {{ fill: #fff; stroke-width: 2; }}
    .block.aon {{ stroke: var(--aon); fill: #f6f7f8; }}
    .block.cpu {{ stroke: var(--cpu); fill: #edf5ff; }}
    .block.mem {{ stroke: var(--mem); fill: #eefaf2; }}
    .edge {{ fill: none; stroke: #506070; stroke-width: 2.2; marker-end: url(#arrow); }}
    .edge.dashed {{ stroke-dasharray: 7 5; }}
    .packet {{ fill: #f2994a; filter: drop-shadow(0 1px 2px rgba(0,0,0,0.25)); }}
    .packet-exec {{ fill: #2f80ed; }}
    .packet-mem {{ fill: #27ae60; }}
    .packet-df {{ fill: #9b51e0; }}
    .caption, .axis-label {{ fill: #5d6d7e; font-size: 12px; }}
    .chart-title {{ fill: #17202a; font-size: 18px; font-weight: 700; }}
    .grid-line {{ stroke: #e3e8f1; }}
    .axis-line {{ stroke: #1f2937; stroke-width: 1; }}
    .value-label {{ fill: #334155; font-size: 11px; }}
    .timeline-cursor {{
      stroke: #111827;
      stroke-width: 2.6;
      animation: sweep 7s linear infinite;
    }}
    @keyframes sweep {{
      from {{ transform: translateX(0); }}
      to {{ transform: translateX(892px); }}
    }}
    .domain-stack {{ display: flex; height: 24px; overflow: hidden; border-radius: 5px; margin: 12px 0; background: #e9edf5; }}
    .domain-stack span {{ display: block; min-width: 1px; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 12px; color: var(--muted); font-size: 13px; }}
    .legend.compact {{ display: block; }}
    .legend.compact li {{ margin-bottom: 4px; }}
    .legend i {{ display: inline-block; width: 12px; height: 12px; margin-right: 6px; vertical-align: -1px; border-radius: 2px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #edf0f5; padding: 7px 6px; text-align: left; }}
    th {{ color: var(--muted); font-weight: 600; }}
    .muted {{ color: var(--muted); }}
    .code-data {{ white-space: pre-wrap; overflow: auto; max-height: 220px; background: #111827; color: #d1e7ff; border-radius: 8px; padding: 14px; font-size: 12px; }}
    @media (max-width: 820px) {{
      main {{ padding: 16px; }}
      .two-col {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 28px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Mobile CPU Visual Power Story</h1>
    <p>Technology <code>{esc(tech)}</code>, scheme <code>{esc(scheme_name)}</code>. This dashboard connects workload intent, CPU activity, power states, and IEEE 2416 estimates.</p>
  </header>
  <main>
    <section class="two-col">
      <div class="panel">
        <h2>How The CPU Moves Work</h2>
        {build_datapath_animation()}
      </div>
      <aside class="panel">
        <h2>Power Strategy</h2>
        {build_scheme_summary(scheme, scheme_name)}
        <h3>States</h3>
        <ul class="legend">{states}</ul>
        <h3 style="margin-top:16px">Domains</h3>
        <ul class="legend">{domains}</ul>
      </aside>
    </section>

    <section class="panel">
      <h2>Animated Power Timeline</h2>
      <p class="muted">The stacked area shows estimated power by domain. The mode band underneath shows how the same workload moves through RUN, idle, sleep, deep sleep, and wake recovery.</p>
      {build_power_timeline(primary)}
    </section>

    <section>
      <h2>Workload Cards</h2>
      <div class="cards">{cards}</div>
    </section>

    {optimization_section}

    <section class="panel">
      <h2>Power Tradeoffs</h2>
      <p class="muted">Use these charts to compare whether energy is dominated by useful computation, offload traffic, low-power recovery, or memory behavior.</p>
      {energy_chart}
      {useful_chart}
      {recovery_chart}
    </section>

    <section>
      <h2>Energy By Domain</h2>
      <div class="cards">{domain_sections}</div>
    </section>

    <section>
      <h2>Dominant Activity Events</h2>
      <div class="cards">{event_sections}</div>
    </section>

    <section class="panel">
      <h2>Flow Map</h2>
      <p><code>workload_specs/*.json</code> or <code>workloads/*.s</code> produces ROM contents, Verilator produces VCD activity, the IEEE 2416 estimator maps activity to block/domain energy, and this dashboard explains the resulting tradeoffs.</p>
      <pre class="code-data">{esc(case_json)}</pre>
    </section>
  </main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", action="append", dest="workloads", required=True)
    parser.add_argument("--tech", default="generic_7nm")
    parser.add_argument("--scheme", default="dvfs_retention_domains")
    parser.add_argument("--report-root", type=Path, default=Path("reports/2416"))
    parser.add_argument("--intent-root", type=Path, default=Path("build/workloadgen"))
    parser.add_argument("--scheme-root", type=Path, default=Path("power_schemes"))
    parser.add_argument("--out", type=Path, default=Path("reports/visual_story/index.html"))
    parser.add_argument("--cards-out", type=Path)
    args = parser.parse_args()

    cases = [
        load_case(args.report_root, args.intent_root, workload, args.tech, args.scheme)
        for workload in args.workloads
    ]
    scheme = load_scheme(args.scheme_root, args.scheme)
    optimization_cards = generate_power_optimization_cards(cases, args.scheme)
    cards_out = args.cards_out or (args.out.parent / "power_optimization_cards.json")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cards_out.parent.mkdir(parents=True, exist_ok=True)
    cards_out.write_text(json.dumps(optimization_cards, indent=2) + "\n", encoding="utf-8")
    args.out.write_text(
        html_document(cases, scheme, optimization_cards, args.tech, args.scheme),
        encoding="utf-8",
    )
    print(f"wrote {cards_out}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
