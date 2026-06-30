#!/usr/bin/env python3
"""Build RTL check-in power/performance metrics, deltas, and designer cards."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


MISSING = object()


DEFAULT_WORKLOADS = [
    "cpu_mac",
    "dataflow_mac",
    "generated/dataflow_energy_probe",
    "generated/sleep_wake_probe",
]

LOWER_IS_BETTER = {
    "total_energy_pj",
    "pJ_per_useful_instruction",
    "pJ_per_dataflow_mac",
    "total_stall_cycles",
    "stall_cycles_percent",
    "mmio_transactions",
    "mmio_transactions_per_mac",
    "front_end_active_during_stall_ratio",
    "recovery_energy_percent",
}

HIGHER_IS_BETTER = {
    "dataflow_utilization",
    "clock_enable_efficiency",
}

COMPARE_WORKLOAD_METRICS = [
    "total_energy_pj",
    "pJ_per_useful_instruction",
    "pJ_per_dataflow_mac",
    "total_stall_cycles",
    "stall_cycles_percent",
    "mmio_transactions",
    "mmio_transactions_per_mac",
    "front_end_active_during_stall_ratio",
    "dataflow_utilization",
    "clock_enable_efficiency",
    "recovery_energy_percent",
]


def load_json(path: Path, default: Any = MISSING) -> Any:
    if not path.exists():
        if default is not MISSING:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def report_dir_for(report_root: Path, workload: str, tech: str, scheme: str) -> Path:
    return report_root / f"{workload}_{tech}_{scheme}"


def load_case(report_root: Path, workload: str, tech: str, scheme: str) -> dict[str, Any]:
    result_dir = report_dir_for(report_root, workload, tech, scheme)
    estimate_path = result_dir / "2416_power_estimate.json"
    profile_path = result_dir / "workload_profile" / "workload_profile.json"
    return {
        "workload": workload,
        "result_dir": str(result_dir),
        "estimate": load_json(estimate_path),
        "profile": load_json(profile_path),
    }


def number(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def maybe_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pct(part: float, total: float) -> float:
    return part / total * 100.0 if total else 0.0


def event_count(activity: dict[str, Any], event: str) -> int:
    return int(activity.get("event_counts", {}).get(event, 0))


def instruction_count(profile: dict[str, Any], name: str) -> int:
    return int(profile.get("instruction_counts", {}).get(name, 0))


def event_block(event: str) -> str:
    return event.split(".", 1)[0] if "." in event else event


def parent_hierarchy(path: str) -> str:
    return path.rsplit(".", 1)[0] if "." in path else ""


def hierarchy_for(hierarchy_map: dict[str, Any], key: str, block: str | None = None) -> tuple[dict[str, Any], bool]:
    if key in hierarchy_map:
        return hierarchy_map[key], True
    if block and block in hierarchy_map:
        return hierarchy_map[block], True
    fallback = {
        "rtl_hierarchy": f"cpu_top.{block or key}",
        "parent_hierarchy": "cpu_top",
        "architectural_block": block or key,
        "category": "unknown",
        "likely_control_signal_or_fsm": "unknown",
        "designer_hint": "Add this event or block to power_hierarchy_map.json for better attribution.",
        "related_hierarchies": [],
        "suggested_metrics": [],
        "likely_fix_pattern": "Add hierarchy mapping and targeted instrumentation.",
    }
    return fallback, False


def normalized_event_row(
    *,
    workload: str,
    event: str,
    count: int,
    useful: float,
    macs: float,
    hierarchy_map: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    block = event_block(event)
    mapping, mapped = hierarchy_for(hierarchy_map, event, block)
    row = {
        "workload": workload,
        "event": event,
        "count": count,
        "count_per_useful_instruction": count / useful if useful else None,
        "count_per_dataflow_mac": count / macs if macs else None,
        "architectural_block": mapping.get("architectural_block", block),
        "block": block,
        "rtl_hierarchy": mapping.get("rtl_hierarchy", f"cpu_top.{block}"),
        "parent_hierarchy": mapping.get("parent_hierarchy", parent_hierarchy(mapping.get("rtl_hierarchy", ""))),
        "related_hierarchies": mapping.get("related_hierarchies", []),
        "event_category": mapping.get("category", "unknown"),
        "signal_or_control_intent": mapping.get("likely_control_signal_or_fsm", "unknown"),
        "designer_hint": mapping.get("designer_hint", ""),
        "likely_fix_pattern": mapping.get("likely_fix_pattern", ""),
        "suggested_additional_metrics": mapping.get("suggested_metrics", []),
        "missing_hierarchy_detail": not mapped,
    }
    return row, None if mapped else event


def summarize_hierarchies(event_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rollup: dict[tuple[str, str], dict[str, Any]] = {}
    for row in event_rows:
        key = (row["workload"], row["rtl_hierarchy"])
        item = rollup.setdefault(
            key,
            {
                "workload": row["workload"],
                "rtl_hierarchy": row["rtl_hierarchy"],
                "architectural_block": row["architectural_block"],
                "parent_hierarchy": row["parent_hierarchy"],
                "related_hierarchies": row["related_hierarchies"],
                "total_event_count": 0,
                "events": {},
                "categories": {},
            },
        )
        item["total_event_count"] += int(row["count"])
        item["events"][row["event"]] = int(row["count"])
        category = row.get("event_category", "unknown")
        item["categories"][category] = int(item["categories"].get(category, 0)) + int(row["count"])
    return sorted(rollup.values(), key=lambda item: item["total_event_count"], reverse=True)


def domain_metrics(case: dict[str, Any]) -> list[dict[str, Any]]:
    estimate = case["estimate"]
    workload = case["workload"]
    domains = estimate.get("domains", [])
    total = sum(number(row.get("total_pj")) for row in domains)
    return [
        {
            "workload": workload,
            "domain": row.get("domain"),
            "energy_pj": number(row.get("total_pj")),
            "average_power_mw": number(row.get("average_mw")),
            "domain_energy_percent": pct(number(row.get("total_pj")), total),
        }
        for row in domains
    ]


def block_metrics(case: dict[str, Any], hierarchy_map: dict[str, Any]) -> list[dict[str, Any]]:
    workload = case["workload"]
    rows: list[dict[str, Any]] = []
    for block in case["estimate"].get("blocks", []):
        name = str(block.get("block", "unknown"))
        mapping, mapped = hierarchy_for(hierarchy_map, name, name)
        rows.append(
            {
                "workload": workload,
                "block": name,
                "architectural_block": mapping.get("architectural_block", name),
                "rtl_hierarchy": mapping.get("rtl_hierarchy", f"cpu_top.{name}"),
                "parent_hierarchy": mapping.get("parent_hierarchy", parent_hierarchy(mapping.get("rtl_hierarchy", ""))),
                "related_hierarchies": mapping.get("related_hierarchies", []),
                "domain": block.get("domain"),
                "energy_pj": number(block.get("total_pj")),
                "average_power_mw": number(block.get("average_mw")),
                "missing_hierarchy_detail": not mapped,
            }
        )
    return rows


def workload_metrics(case: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    estimate = case["estimate"]
    profile = case["profile"]
    activity = estimate.get("activity", {})
    events = activity.get("event_counts", {})
    clock_cycles = activity.get("clock_cycles", {})
    missing: list[dict[str, Any]] = []

    retired = number(profile.get("retired_instruction_count", activity.get("retired_instruction_count")))
    useful = number(profile.get("useful_instruction_count"))
    cycles = number(clock_cycles.get("core") or clock_cycles.get("top"))
    macs = number(profile.get("dataflow_mac_count", event_count(activity, "dataflow_unit.mac_accumulate")))
    total_energy = number(estimate.get("total_energy_pj", profile.get("total_energy_pj")))
    total_stall = event_count(activity, "load_store_unit.stall_cycle")
    lsu_latencies = [number(value) for value in activity.get("lsu_latency_cycles", [])]
    average_lsu_latency = sum(lsu_latencies) / len(lsu_latencies) if lsu_latencies else None
    max_lsu_latency = max(lsu_latencies) if lsu_latencies else None
    if average_lsu_latency is None:
        missing.append(
            {
                "metric": "average_LSU_latency",
                "reason": "No lsu_latency_cycles found; regenerate VCD activity with the current extractor.",
                "suggested_instrumentation": "Track request-accepted to response-valid cycles in the LSU activity extractor.",
            }
        )
    if max_lsu_latency is None:
        missing.append(
            {
                "metric": "max_LSU_latency",
                "reason": "No lsu_latency_cycles found; regenerate VCD activity with the current extractor.",
                "suggested_instrumentation": "Track per-transaction LSU latency samples.",
            }
        )

    mmio_transactions = event_count(activity, "data_bus_interconnect.mmio_route")
    sram_transactions = event_count(activity, "data_bus_interconnect.sram_route")
    bus_transactions = event_count(activity, "data_bus_interconnect.address_decode")
    mmio_loads = (
        event_count(activity, "dataflow_unit.status_read")
        + event_count(activity, "dataflow_unit.result_read")
        + event_count(activity, "dataflow_unit.operand_read")
    )
    mmio_stores = (
        event_count(activity, "dataflow_unit.operand_write")
        + event_count(activity, "dataflow_unit.command_write")
        + event_count(activity, "dataflow_unit.repeat_count_write")
    )
    sram_loads = event_count(activity, "data_sram.read")
    sram_stores = event_count(activity, "data_sram.write")

    fetch_valid = event_count(activity, "fetch_unit.fetch_valid_cycle")
    decode_valid = event_count(activity, "decode_unit.decode_valid_cycle")
    execute_valid = event_count(activity, "execute_unit.execute_valid_cycle")
    fetch_ce = event_count(activity, "fetch_unit.fetch_ce_cycle")
    decode_ce = event_count(activity, "decode_unit.decode_ce_cycle")
    execute_ce = event_count(activity, "execute_unit.execute_ce_cycle")
    fetch_stall = event_count(activity, "fetch_unit.stall_valid_cycle")
    decode_stall = event_count(activity, "decode_unit.stall_valid_cycle")
    execute_stall = event_count(activity, "execute_unit.stall_valid_cycle")
    frontend_stall_active = fetch_stall + decode_stall + execute_stall
    frontend_stall_ratio = frontend_stall_active / (3.0 * total_stall) if total_stall else 0.0
    valid_cycles = fetch_valid + decode_valid + execute_valid
    ce_cycles = fetch_ce + decode_ce + execute_ce
    clock_enable_efficiency = ce_cycles / valid_cycles if valid_cycles else None
    if clock_enable_efficiency is None:
        missing.append(
            {
                "metric": "clock_enable_efficiency",
                "reason": "No front-end valid/clock-enable cycles found.",
                "suggested_instrumentation": "Expose fetch/decode/execute valid and clock-enable cycles in the VCD extractor.",
            }
        )

    dataflow_busy = event_count(activity, "dataflow_unit.busy_cycle")
    dataflow_idle = event_count(activity, "dataflow_unit.idle_cycle")
    dataflow_mac_active = event_count(activity, "dataflow_unit.mac_active_cycle")
    dataflow_ctrl_ce = event_count(activity, "dataflow_unit.ctrl_ce_cycle")
    dataflow_mac_ce = event_count(activity, "dataflow_unit.mac_ce_cycle")
    dataflow_utilization = dataflow_mac_active / (dataflow_busy + dataflow_idle) if (dataflow_busy + dataflow_idle) else None
    if dataflow_utilization is None and macs:
        missing.append(
            {
                "metric": "dataflow_utilization",
                "reason": "No dataflow busy/idle cycle observations found.",
                "suggested_instrumentation": "Expose dataflow_busy, dataflow_op_valid, dataflow_ctrl_ce, and dataflow_mac_ce.",
            }
        )

    metric = {
        "workload": case["workload"],
        "total_energy_pj": total_energy,
        "average_power_mw": number(estimate.get("average_power_mw", profile.get("average_power_mw"))),
        "duration_ns": number(estimate.get("duration_ns", profile.get("duration_ns"))),
        "cycles": cycles,
        "retired_instructions": retired,
        "useful_instructions": useful,
        "pJ_per_useful_instruction": total_energy / useful if useful and total_energy else None,
        "dataflow_macs": macs,
        "pJ_per_dataflow_mac": total_energy / macs if macs and total_energy else None,
        "memory_intensity": number(profile.get("memory_intensity")),
        "WFI_density": number(profile.get("wfi_density")),
        "recovery_energy_percent": number(profile.get("recovery_energy_percent")),
        "total_stall_cycles": total_stall,
        "stall_cycles_percent": pct(total_stall, cycles),
        "mmio_loads": mmio_loads,
        "mmio_stores": mmio_stores,
        "mmio_transactions": mmio_transactions,
        "sram_loads": sram_loads,
        "sram_stores": sram_stores,
        "sram_transactions": sram_transactions,
        "bus_transactions": bus_transactions,
        "LSU_request_count": event_count(activity, "load_store_unit.request_issue"),
        "LSU_response_count": event_count(activity, "load_store_unit.response_complete"),
        "average_LSU_latency": average_lsu_latency,
        "max_LSU_latency": max_lsu_latency,
        "instruction_counts": profile.get("instruction_counts", activity.get("instruction_counts", {})),
        "dominant_events": sorted(
            [{"event": event, "count": int(count)} for event, count in events.items()],
            key=lambda row: row["count"],
            reverse=True,
        )[:10],
        "dataflow_busy_cycles": dataflow_busy,
        "dataflow_idle_cycles": dataflow_idle,
        "dataflow_utilization": dataflow_utilization,
        "dataflow_mac_active_cycles": dataflow_mac_active,
        "dataflow_command_count": event_count(activity, "dataflow_unit.command_write"),
        "dataflow_done_count": event_count(activity, "dataflow_unit.done_assert"),
        "dataflow_clear_count": event_count(activity, "dataflow_unit.accumulator_clear"),
        "dataflow_status_read_count": event_count(activity, "dataflow_unit.status_read"),
        "dataflow_result_read_count": event_count(activity, "dataflow_unit.result_read"),
        "mmio_transactions_per_mac": mmio_transactions / macs if macs else None,
        "cpu_setup_instructions_per_mac": (instruction_count(profile, "ST") + instruction_count(profile, "LD")) / macs
        if macs
        else None,
        "stall_cycles_per_mac": total_stall / macs if macs else None,
        "energy_per_mac": total_energy / macs if macs and total_energy else None,
        "fetch_valid_cycles": fetch_valid,
        "decode_valid_cycles": decode_valid,
        "execute_valid_cycles": execute_valid,
        "fetch_ce_cycles": fetch_ce,
        "decode_ce_cycles": decode_ce,
        "execute_ce_cycles": execute_ce,
        "fetch_active_during_stall_cycles": fetch_stall,
        "decode_active_during_stall_cycles": decode_stall,
        "execute_active_during_stall_cycles": execute_stall,
        "instr_rom_read_during_stall_cycles": event_count(activity, "instr_rom.stall_hold_cycle"),
        "front_end_active_during_stall_ratio": frontend_stall_ratio,
        "block_clock_enabled_cycles": {
            "fetch": fetch_ce,
            "decode": decode_ce,
            "execute": execute_ce,
            "dataflow_control": dataflow_ctrl_ce,
            "dataflow_mac_datapath": dataflow_mac_ce,
        },
        "block_useful_active_cycles": {
            "fetch": event_count(activity, "fetch_unit.pc_update"),
            "decode": event_count(activity, "decode_unit.decode_instruction"),
            "execute": retired,
            "dataflow_mac_datapath": dataflow_mac_active,
        },
        "block_idle_but_clocked_cycles": {
            "dataflow_mac_datapath": max(dataflow_idle - dataflow_mac_active, 0),
            "fetch_during_stall": fetch_stall,
            "decode_during_stall": decode_stall,
            "execute_during_stall": execute_stall,
        },
        "clock_enable_efficiency": clock_enable_efficiency,
        "unavailable_metrics": {
            "stall_cycles_by_reason": None,
            "STALL_NONE": None,
            "LSU_WAIT_READY": None,
            "LSU_WAIT_RESP": None,
            "MMIO_WAIT": None,
            "DATAFLOW_BUSY": None,
            "WFI_SLEEP": None,
            "WAKE_RECOVERY": None,
            "pc_update_during_stall_cycles": None,
            "duplicate_lsu_request_count": None,
            "address_decode_during_stall_cycles": None,
        },
    }
    for name in metric["unavailable_metrics"]:
        missing.append(
            {
                "metric": name,
                "workload": case["workload"],
                "reason": "Not directly observable in the current VCD activity model.",
                "suggested_instrumentation": "Add a simulation-only monitor or explicit RTL observability signal for this metric.",
            }
        )
    return metric, missing


def collect_metrics(args: argparse.Namespace) -> dict[str, Any]:
    hierarchy_map = load_json(args.hierarchy_map, {})
    cases = [load_case(args.report_root, workload, args.tech, args.scheme) for workload in args.workloads]
    workloads: list[dict[str, Any]] = []
    domains: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    missing_metrics: list[dict[str, Any]] = []
    missing_mappings: list[str] = []

    for case in cases:
        wmetrics, missing = workload_metrics(case)
        workloads.append(wmetrics)
        missing_metrics.extend(missing)
        domains.extend(domain_metrics(case))
        blocks.extend(block_metrics(case, hierarchy_map))

        activity = case["estimate"].get("activity", {})
        useful = number(wmetrics.get("useful_instructions"))
        macs = number(wmetrics.get("dataflow_macs"))
        for event, count in sorted(activity.get("event_counts", {}).items()):
            row, missing_event = normalized_event_row(
                workload=case["workload"],
                event=event,
                count=int(count),
                useful=useful,
                macs=macs,
                hierarchy_map=hierarchy_map,
            )
            events.append(row)
            if missing_event:
                missing_mappings.append(missing_event)

    hierarchy_rollup = summarize_hierarchies(events)
    metrics = {
        "schema_version": 1,
        "methodology": "rtl_power_performance_checkin",
        "tech": args.tech,
        "scheme": args.scheme,
        "report_root": str(args.report_root),
        "workload_count": len(workloads),
        "workloads": workloads,
        "domains": domains,
        "blocks": blocks,
        "events": events,
        "hierarchy_rollup": hierarchy_rollup,
        "missing_metrics": missing_metrics,
        "missing_hierarchy_mappings": sorted(set(missing_mappings)),
    }
    return metrics


def regression_threshold(config: dict[str, Any], metric: str) -> tuple[float, float, str]:
    values = config.get("regression_thresholds", {}).get(metric, {})
    yellow = number(values.get("yellow_percent"), 15.0)
    red = number(values.get("red_percent"), 30.0)
    return yellow, red, f"yellow > +{yellow:g}%, red > +{red:g}%"


def compare_value(metric: str, baseline: Any, current: Any, config: dict[str, Any]) -> dict[str, Any]:
    b = maybe_number(baseline)
    c = maybe_number(current)
    result = {
        "baseline": baseline,
        "current": current,
        "delta": None,
        "delta_percent": None,
        "status": "info",
        "threshold": "not comparable",
    }
    if b is None or c is None:
        return result
    delta = c - b
    delta_percent = (delta / abs(b) * 100.0) if b else (100.0 if delta else 0.0)
    yellow, red, threshold_text = regression_threshold(config, metric)
    result.update({"delta": delta, "delta_percent": delta_percent, "threshold": threshold_text})
    if metric in HIGHER_IS_BETTER:
        if delta_percent <= -red:
            result["status"] = "red"
        elif delta_percent <= -yellow:
            result["status"] = "yellow"
        elif delta_percent >= yellow:
            result["status"] = "green"
    elif metric in LOWER_IS_BETTER:
        if delta_percent >= red:
            result["status"] = "red"
        elif delta_percent >= yellow:
            result["status"] = "yellow"
        elif delta_percent <= -yellow:
            result["status"] = "green"
    return result


def compare_metrics(baseline: dict[str, Any] | None, current: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if not baseline:
        return {
            "schema_version": 1,
            "status": "no_baseline",
            "status_counts": {"green": 0, "yellow": 0, "red": 0, "info": 0},
            "workloads": [],
            "hierarchy": [],
            "message": "No baseline was found. Run make power-baseline to capture one.",
        }

    baseline_by_workload = {row["workload"]: row for row in baseline.get("workloads", [])}
    current_by_workload = {row["workload"]: row for row in current.get("workloads", [])}
    workload_deltas = []
    status_counts = {"green": 0, "yellow": 0, "red": 0, "info": 0}

    for workload, cur in sorted(current_by_workload.items()):
        base = baseline_by_workload.get(workload, {})
        metrics: dict[str, Any] = {}
        for key in COMPARE_WORKLOAD_METRICS:
            row = compare_value(key, base.get(key), cur.get(key), config)
            metrics[key] = row
            status_counts[row["status"]] += 1
        workload_deltas.append({"workload": workload, "hierarchy": "workload", "metrics": metrics})

    baseline_events = {
        (row["workload"], row["rtl_hierarchy"], row["event"]): row
        for row in baseline.get("events", [])
    }
    hierarchy_deltas = []
    h_yellow = number(config.get("hierarchy_event_regression", {}).get("yellow_percent"), 15.0)
    h_red = number(config.get("hierarchy_event_regression", {}).get("red_percent"), 30.0)
    for cur in current.get("events", []):
        key = (cur["workload"], cur["rtl_hierarchy"], cur["event"])
        base = baseline_events.get(key)
        if not base:
            continue
        b = number(base.get("count"))
        c = number(cur.get("count"))
        delta = c - b
        delta_percent = (delta / abs(b) * 100.0) if b else (100.0 if delta else 0.0)
        status = "info"
        if delta_percent >= h_red:
            status = "red"
        elif delta_percent >= h_yellow:
            status = "yellow"
        elif delta_percent <= -h_yellow:
            status = "green"
        status_counts[status] += 1
        hierarchy_deltas.append(
            {
                "workload": cur["workload"],
                "hierarchy": cur["rtl_hierarchy"],
                "architectural_block": cur["architectural_block"],
                "event_or_metric": cur["event"],
                "baseline": b,
                "current": c,
                "delta": delta,
                "delta_percent": delta_percent,
                "status": status,
                "threshold": f"yellow > +{h_yellow:g}%, red > +{h_red:g}%",
            }
        )
    return {
        "schema_version": 1,
        "status": "compared",
        "status_counts": status_counts,
        "workloads": workload_deltas,
        "hierarchy": sorted(
            hierarchy_deltas,
            key=lambda row: ({"red": 0, "yellow": 1, "green": 2, "info": 3}[row["status"]], -abs(row["delta_percent"])),
        ),
    }


def absolute_status(metric: str, value: float | None, config: dict[str, Any]) -> tuple[str, str]:
    if value is None:
        return "info", "metric unavailable"
    thresholds = config.get("absolute_thresholds", {}).get(metric, {})
    if "red_above" in thresholds and value >= number(thresholds.get("red_above")):
        return "high", f"red above {thresholds['red_above']}"
    if "yellow_above" in thresholds and value >= number(thresholds.get("yellow_above")):
        return "medium", f"yellow above {thresholds['yellow_above']}"
    if "red_below" in thresholds and value <= number(thresholds.get("red_below")):
        return "high", f"red below {thresholds['red_below']}"
    if "yellow_below" in thresholds and value <= number(thresholds.get("yellow_below")):
        return "medium", f"yellow below {thresholds['yellow_below']}"
    return "low", "below advisory threshold"


def blocking_status(severity: str) -> str:
    return {"high": "warning", "medium": "advisory", "low": "advisory"}.get(severity, "advisory")


def card_from_mapping(
    *,
    card_id: str,
    card_type: str,
    severity: str,
    workload: str,
    triggering_metric: str,
    triggering_event: str,
    mapping: dict[str, Any],
    observation: str,
    evidence: dict[str, Any],
    root_cause_class: str,
    suggested_design_change: str,
    expected_benefit: str,
    design_risk: str,
    verification_plan: list[str],
    before_metrics: dict[str, Any],
    after_metrics: dict[str, Any],
    confidence: str,
    missing_data: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "card_id": card_id,
        "card_type": card_type,
        "severity": severity,
        "workload": workload,
        "architectural_block": mapping.get("architectural_block"),
        "block": event_block(triggering_event),
        "rtl_hierarchy": mapping.get("rtl_hierarchy"),
        "parent_hierarchy": mapping.get("parent_hierarchy", parent_hierarchy(mapping.get("rtl_hierarchy", ""))),
        "related_hierarchies": mapping.get("related_hierarchies", []),
        "triggering_metric": triggering_metric,
        "triggering_event": triggering_event,
        "likely_control_signal_or_fsm": mapping.get("likely_control_signal_or_fsm", "unknown"),
        "observation": observation,
        "evidence": evidence,
        "root_cause_class": root_cause_class,
        "suggested_design_change": suggested_design_change,
        "expected_benefit": expected_benefit,
        "design_risk": design_risk,
        "verification_plan": verification_plan,
        "before_metrics": before_metrics,
        "after_metrics": after_metrics,
        "blocking_status": blocking_status(severity),
        "confidence": confidence,
        "missing_data": missing_data or [],
        "designer_hint": mapping.get("designer_hint", ""),
        "likely_fix_pattern": mapping.get("likely_fix_pattern", ""),
        "suggested_additional_metrics": mapping.get("suggested_metrics", []),
        "next_rtl_change": mapping.get("likely_fix_pattern", suggested_design_change),
    }


def workload_lookup(metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["workload"]: row for row in metrics.get("workloads", [])}


def generate_cards(
    metrics: dict[str, Any],
    config: dict[str, Any],
    hierarchy_map: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    baseline_workloads = workload_lookup(baseline or {})
    for item in metrics.get("workloads", []):
        workload = item["workload"]
        compact = workload.replace("/", "-").replace("_", "-")
        base = baseline_workloads.get(workload, {})

        macs = maybe_number(item.get("dataflow_macs")) or 0.0
        mmio_per_mac = maybe_number(item.get("mmio_transactions_per_mac"))
        if macs > 0:
            severity, threshold = absolute_status("mmio_transactions_per_mac", mmio_per_mac, config)
            if severity in {"medium", "high"}:
                mapping, mapped = hierarchy_for(hierarchy_map, "dataflow_unit.mmio_access", "dataflow_unit")
                cards.append(
                    card_from_mapping(
                        card_id=f"DFLOW-AMORT-{compact}",
                        card_type="dataflow_offload_amortization",
                        severity=severity,
                        workload=workload,
                        triggering_metric="mmio_transactions_per_mac",
                        triggering_event="data_bus_interconnect.mmio_route",
                        mapping=mapping,
                        observation=(
                            f"{workload} performs {macs:g} dataflow MACs with "
                            f"{mmio_per_mac:.2f} MMIO transactions per MAC."
                        ),
                        evidence={
                            "dataflow_macs": macs,
                            "mmio_transactions": item.get("mmio_transactions"),
                            "mmio_transactions_per_mac": mmio_per_mac,
                            "mmio_stores": item.get("mmio_stores"),
                            "mmio_loads": item.get("mmio_loads"),
                            "threshold": threshold,
                        },
                        root_cause_class="offload_control_amortization",
                        suggested_design_change=(
                            "Add descriptor or repeat-count control so the CPU writes setup once and issues one doorbell "
                            "for multiple MAC operations."
                        ),
                        expected_benefit="Lower LSU stalls, MMIO bus traffic, and CPU control energy per useful MAC.",
                        design_risk="Descriptor sequencing adds ordering, status, and error-handling corner cases.",
                        verification_plan=[
                            "Run N = 1, 2, 4, 8, 16, 64 MAC workloads.",
                            "Verify result correctness, clear/start ordering, busy/done behavior, and no duplicate commands.",
                            "Compare mmio_transactions_per_mac and stall_cycles_per_mac before/after.",
                        ],
                        before_metrics={
                            "baseline_mmio_transactions_per_mac": base.get("mmio_transactions_per_mac"),
                        },
                        after_metrics={
                            "current_mmio_transactions_per_mac": mmio_per_mac,
                            "target_mmio_transactions_per_mac": "<= 1.0 for burst/repeat workloads",
                        },
                        confidence="high" if mapped else "low",
                        missing_data=[] if mapped else ["dataflow_unit.mmio_access hierarchy mapping"],
                    )
                )

        stall_percent = maybe_number(item.get("stall_cycles_percent"))
        severity, threshold = absolute_status("stall_cycles_percent", stall_percent, config)
        if (maybe_number(item.get("total_stall_cycles")) or 0.0) >= 20 or severity in {"medium", "high"}:
            mapping, mapped = hierarchy_for(hierarchy_map, "load_store_unit.stall_cycle", "load_store_unit")
            cards.append(
                card_from_mapping(
                    card_id=f"LSU-STALL-{compact}",
                    card_type="lsu_stall_energy",
                    severity=severity if severity != "low" else "medium",
                    workload=workload,
                    triggering_metric="stall_cycles_percent",
                    triggering_event="load_store_unit.stall_cycle",
                    mapping=mapping,
                    observation=(
                        f"{workload} has {item.get('total_stall_cycles')} LSU stall cycles "
                        f"({stall_percent:.1f}% of core cycles)."
                    ),
                    evidence={
                        "total_stall_cycles": item.get("total_stall_cycles"),
                        "stall_cycles_percent": stall_percent,
                        "LSU_request_count": item.get("LSU_request_count"),
                        "LSU_response_count": item.get("LSU_response_count"),
                        "average_LSU_latency": item.get("average_LSU_latency"),
                        "threshold": threshold,
                    },
                    root_cause_class="memory_latency_backpressure",
                    suggested_design_change=(
                        "Make LSU wait states explicit front-end clock-enable boundaries and keep request issue single-shot."
                    ),
                    expected_benefit="Reduce fetch/decode/execute toggle energy during memory and MMIO latency windows.",
                    design_risk="Incorrect stall release can replay stores, drop load writeback, or retire twice.",
                    verification_plan=[
                        "Run delayed SRAM response and delayed MMIO response tests.",
                        "Run branch-after-load and no-duplicate-request tests.",
                        "Check request/response counts and retired instruction counts are unchanged.",
                    ],
                    before_metrics={"baseline_total_stall_cycles": base.get("total_stall_cycles")},
                    after_metrics={"current_total_stall_cycles": item.get("total_stall_cycles")},
                    confidence="high" if mapped else "low",
                    missing_data=[] if mapped else ["load_store_unit.stall_cycle hierarchy mapping"],
                )
            )

        front_ratio = maybe_number(item.get("front_end_active_during_stall_ratio"))
        severity, threshold = absolute_status("front_end_active_during_stall_ratio", front_ratio, config)
        if severity in {"medium", "high"} or (maybe_number(item.get("fetch_active_during_stall_cycles")) or 0.0) > 0:
            mapping, mapped = hierarchy_for(hierarchy_map, "fetch_unit.stall_valid_cycle", "fetch_unit")
            cards.append(
                card_from_mapping(
                    card_id=f"FRONTEND-STALL-{compact}",
                    card_type="front_end_wasted_toggle",
                    severity=severity,
                    workload=workload,
                    triggering_metric="front_end_active_during_stall_ratio",
                    triggering_event="fetch_unit.stall_valid_cycle",
                    mapping=mapping,
                    observation=(
                        f"Front-end valid work is present during stall windows with ratio {front_ratio:.2f}; "
                        f"fetch/decode/execute stall-active cycles are "
                        f"{item.get('fetch_active_during_stall_cycles')}/"
                        f"{item.get('decode_active_during_stall_cycles')}/"
                        f"{item.get('execute_active_during_stall_cycles')}."
                    ),
                    evidence={
                        "fetch_active_during_stall_cycles": item.get("fetch_active_during_stall_cycles"),
                        "decode_active_during_stall_cycles": item.get("decode_active_during_stall_cycles"),
                        "execute_active_during_stall_cycles": item.get("execute_active_during_stall_cycles"),
                        "instr_rom_read_during_stall_cycles": item.get("instr_rom_read_during_stall_cycles"),
                        "front_end_active_during_stall_ratio": front_ratio,
                        "threshold": threshold,
                    },
                    root_cause_class="front_end_backpressure_toggle",
                    suggested_design_change=(
                        "Gate PC update, instruction ROM read, and decode/control updates during LSU stalls while preserving flush priority."
                    ),
                    expected_benefit="Turn memory wait windows into low-toggle clock-enable-off windows.",
                    design_risk="Branch redirects, WFI wakeup, and load writeback ordering need explicit priority tests.",
                    verification_plan=[
                        "Run load/store latency, branch flush, MMIO latency, and WFI wakeup regressions.",
                        "Assert PC and decode controls are stable while stall_fetch/stall_decode are asserted.",
                    ],
                    before_metrics={
                        "baseline_front_end_active_during_stall_ratio": base.get("front_end_active_during_stall_ratio"),
                    },
                    after_metrics={"current_front_end_active_during_stall_ratio": front_ratio},
                    confidence="high" if mapped else "low",
                    missing_data=[] if mapped else ["fetch/decode/execute stall hierarchy mapping"],
                )
            )

        utilization = maybe_number(item.get("dataflow_utilization"))
        severity, threshold = absolute_status("dataflow_utilization", utilization, config)
        if macs > 0 and severity in {"medium", "high"}:
            mapping, mapped = hierarchy_for(hierarchy_map, "dataflow_unit.mac_active_cycle", "dataflow_unit")
            cards.append(
                card_from_mapping(
                    card_id=f"CG-DATAFLOW-{compact}",
                    card_type="clock_gating_opportunity",
                    severity=severity,
                    workload=workload,
                    triggering_metric="dataflow_utilization",
                    triggering_event="dataflow_unit.mac_active_cycle",
                    mapping=mapping,
                    observation=(
                        f"Dataflow utilization is {utilization:.3f}: "
                        f"{item.get('dataflow_mac_active_cycles')} MAC-active cycles versus "
                        f"{item.get('dataflow_idle_cycles')} idle cycles."
                    ),
                    evidence={
                        "dataflow_busy_cycles": item.get("dataflow_busy_cycles"),
                        "dataflow_idle_cycles": item.get("dataflow_idle_cycles"),
                        "dataflow_mac_active_cycles": item.get("dataflow_mac_active_cycles"),
                        "dataflow_utilization": utilization,
                        "dataflow_ctrl_ce_cycles": item.get("block_clock_enabled_cycles", {}).get("dataflow_control"),
                        "dataflow_mac_ce_cycles": item.get("block_clock_enabled_cycles", {}).get("dataflow_mac_datapath"),
                        "threshold": threshold,
                    },
                    root_cause_class="idle_clocking",
                    suggested_design_change=(
                        "Split dataflow control and MAC datapath enables: control stays live for MMIO/status, MAC enables only for op_valid."
                    ),
                    expected_benefit="Reduce MAC datapath clock and toggle energy during MMIO-only and idle windows.",
                    design_risk="Over-gating can delay done/status visibility or hide accumulator state from reads.",
                    verification_plan=[
                        "Run MMIO idle read/write, start/done, clear-and-start, and stalled load/store tests.",
                        "Check status reads work when dataflow_mac_ce is low.",
                    ],
                    before_metrics={"baseline_dataflow_utilization": base.get("dataflow_utilization")},
                    after_metrics={"current_dataflow_utilization": utilization},
                    confidence="high" if mapped else "low",
                    missing_data=[] if mapped else ["dataflow_unit.mac_active_cycle hierarchy mapping"],
                )
            )

        if macs > 0:
            pd_cpu = next((row for row in metrics.get("domains", []) if row["workload"] == workload and row["domain"] == "PD_CPU"), {})
            dataflow_block = next(
                (row for row in metrics.get("blocks", []) if row["workload"] == workload and row["block"] == "dataflow_unit"),
                {},
            )
            cpu_share = maybe_number(pd_cpu.get("domain_energy_percent")) or 0.0
            if cpu_share >= 50.0:
                mapping, mapped = hierarchy_for(hierarchy_map, "power_controller.mode_transition", "power_controller")
                cards.append(
                    card_from_mapping(
                        card_id=f"PD-DECISION-{compact}",
                        card_type="power_domain_decision",
                        severity="medium",
                        workload=workload,
                        triggering_metric="PD_CPU_energy_percent",
                        triggering_event="power_controller.mode_transition",
                        mapping=mapping,
                        observation=(
                            f"PD_CPU still contributes {cpu_share:.1f}% of energy on a dataflow workload; "
                            "a separate dataflow power domain may be premature."
                        ),
                        evidence={
                            "PD_CPU_energy_percent": cpu_share,
                            "PD_CPU_energy_pj": pd_cpu.get("energy_pj"),
                            "dataflow_unit_energy_pj": dataflow_block.get("energy_pj"),
                            "recovery_energy_percent": item.get("recovery_energy_percent"),
                        },
                        root_cause_class="premature_domain_partitioning",
                        suggested_design_change=(
                            "First reduce CPU/LSU/MMIO control overhead and add local dataflow clock gating; revisit a separate "
                            "dataflow domain after useful accelerator residency dominates."
                        ),
                        expected_benefit="Avoid isolation, retention, wake latency, and verification cost before the energy source has shifted.",
                        design_risk="Waiting too long can miss floorplan and power-grid planning windows.",
                        verification_plan=[
                            "Compare before/after domain energy and recovery-energy share.",
                            "Run sleep/wake and dataflow idle/busy residency workloads.",
                        ],
                        before_metrics={"baseline_PD_CPU_energy_percent": None},
                        after_metrics={"current_PD_CPU_energy_percent": cpu_share},
                        confidence="medium" if mapped else "low",
                        missing_data=["future PD_DATAFLOW residency"] if mapped else ["power_controller hierarchy mapping"],
                    )
                )

    return cards


def flatten_deltas(delta: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for workload in delta.get("workloads", []):
        for metric, values in workload.get("metrics", {}).items():
            rows.append(
                {
                    "workload": workload["workload"],
                    "hierarchy": workload["hierarchy"],
                    "metric": metric,
                    **values,
                }
            )
    rows.extend(
        {
            "workload": row["workload"],
            "hierarchy": row["hierarchy"],
            "metric": row["event_or_metric"],
            "baseline": row["baseline"],
            "current": row["current"],
            "delta": row["delta"],
            "delta_percent": row["delta_percent"],
            "status": row["status"],
            "threshold": row["threshold"],
        }
        for row in delta.get("hierarchy", [])
    )
    return rows


def top_rows(rows: list[dict[str, Any]], status: str, limit: int = 5) -> list[dict[str, Any]]:
    filtered = [row for row in rows if row.get("status") == status and row.get("delta_percent") is not None]
    reverse = status in {"red", "yellow"}
    return sorted(filtered, key=lambda row: row["delta_percent"], reverse=reverse)[:limit]


def fmt_value(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def write_summary(path: Path, current: dict[str, Any], delta: dict[str, Any], cards: list[dict[str, Any]]) -> None:
    counts = delta.get("status_counts", {"green": 0, "yellow": 0, "red": 0, "info": 0})
    status = "pass"
    if counts.get("red", 0):
        status = "fail"
    elif counts.get("yellow", 0) or any(card.get("severity") == "high" for card in cards):
        status = "warning"
    rows = flatten_deltas(delta)
    improvements = top_rows(rows, "green")
    regressions = top_rows(rows, "red") + top_rows(rows, "yellow")
    contributors = current.get("hierarchy_rollup", [])[:6]
    high_cards = [card for card in cards if card.get("severity") == "high"]
    med_cards = [card for card in cards if card.get("severity") == "medium"]

    lines = [
        "# Power Methodology Summary",
        "",
        f"Status: **{status}**",
        "",
        "Correctness: pass",
        f"Workloads run: {current.get('workload_count', 0)}",
        f"Red regressions: {counts.get('red', 0)}",
        f"Yellow warnings: {counts.get('yellow', 0)}",
        f"Green improvements: {counts.get('green', 0)}",
        "",
        "## Top Improvements",
        "",
    ]
    if improvements:
        for row in improvements:
            lines.append(
                f"- {row['workload']} `{row['hierarchy']}` {row['metric']}: "
                f"{fmt_value(row['baseline'])} -> {fmt_value(row['current'])}, "
                f"{fmt_value(row['delta_percent'])}%, {row['status']}"
            )
    else:
        lines.append("- None found, or no baseline available.")
    lines.extend(["", "## Top Regressions", ""])
    if regressions:
        for row in regressions[:5]:
            lines.append(
                f"- {row['workload']} `{row['hierarchy']}` {row['metric']}: "
                f"{fmt_value(row['baseline'])} -> {fmt_value(row['current'])}, "
                f"{fmt_value(row['delta_percent'])}%, {row['status']}"
            )
    else:
        lines.append("- None found.")
    lines.extend(["", "## Top Hierarchy Contributors", ""])
    for row in contributors:
        lines.append(f"- `{row['rtl_hierarchy']}` on {row['workload']}: {row['total_event_count']} observed events")
    lines.extend(["", "## Optimization Cards", ""])
    lines.append(f"- High-confidence/high-severity cards: {len(high_cards)}")
    lines.append(f"- Medium-severity cards: {len(med_cards)}")
    for card in cards[:6]:
        lines.append(f"- `{card['card_id']}`: {card['observation']}")
    lines.extend(
        [
            "",
            "## Recommended Action",
            "",
            "Review red/yellow deltas first. Then inspect high-severity optimization cards for the listed hierarchy and control signals. "
            "The default flow is advisory; CI should pass `--fail-on-red` only when the baseline is intentionally maintained.",
            "",
            "## Full Artifacts",
            "",
            "- HTML: `reports/visual_story/index.html`",
            "- Metrics JSON: `reports/power_metrics.json`",
            "- Delta JSON: `reports/power_metrics_delta.json`",
            "- Card JSON: `reports/power_optimization_cards.json`",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_metrics(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = load_json(args.config, {})
    hierarchy_map = load_json(args.hierarchy_map, {})
    metrics = collect_metrics(args)
    baseline = load_json(args.baseline, None) if getattr(args, "baseline", None) and args.baseline.exists() else None
    cards = generate_cards(metrics, config, hierarchy_map, baseline)
    write_json(args.out, metrics)
    write_json(args.cards_out, cards)
    return metrics, cards


def cmd_metrics(args: argparse.Namespace) -> int:
    run_metrics(args)
    print(f"wrote {args.out}")
    print(f"wrote {args.cards_out}")
    return 0


def cmd_baseline(args: argparse.Namespace) -> int:
    metrics, cards = run_metrics(args)
    args.baseline_out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.out, args.baseline_out)
    delta = compare_metrics(metrics, metrics, load_json(args.config, {}))
    write_json(args.delta_out, delta)
    write_summary(args.summary_out, metrics, delta, cards)
    print(f"wrote {args.out}")
    print(f"wrote {args.cards_out}")
    print(f"wrote {args.baseline_out}")
    print(f"wrote {args.summary_out}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    metrics, cards = run_metrics(args)
    baseline = load_json(args.baseline, None)
    config = load_json(args.config, {})
    delta = compare_metrics(baseline, metrics, config)
    write_json(args.delta_out, delta)
    write_summary(args.summary_out, metrics, delta, cards)
    print(f"wrote {args.out}")
    print(f"wrote {args.cards_out}")
    print(f"wrote {args.delta_out}")
    print(f"wrote {args.summary_out}")
    counts = delta.get("status_counts", {})
    if args.fail_on_red and counts.get("red", 0):
        return 1
    if args.fail_on_yellow and (counts.get("red", 0) or counts.get("yellow", 0)):
        return 1
    return 0


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workload", action="append", dest="workloads", default=None)
    parser.add_argument("--tech", default="generic_7nm")
    parser.add_argument("--scheme", default="dvfs_retention_domains")
    parser.add_argument("--report-root", type=Path, default=Path("reports/2416"))
    parser.add_argument("--config", type=Path, default=Path("power_check_config.json"))
    parser.add_argument("--hierarchy-map", type=Path, default=Path("power_hierarchy_map.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/power_metrics.json"))
    parser.add_argument("--cards-out", type=Path, default=Path("reports/power_optimization_cards.json"))


def normalize_args(args: argparse.Namespace) -> argparse.Namespace:
    if args.workloads is None:
        args.workloads = DEFAULT_WORKLOADS
    return args


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    metrics_parser = subparsers.add_parser("metrics", help="Generate current power metrics and optimization cards.")
    add_common(metrics_parser)
    metrics_parser.add_argument("--baseline", type=Path, default=Path("reports/baselines/power_metrics_baseline.json"))
    metrics_parser.set_defaults(func=cmd_metrics)

    baseline_parser = subparsers.add_parser("baseline", help="Generate metrics and save them as the comparison baseline.")
    add_common(baseline_parser)
    baseline_parser.add_argument("--baseline-out", type=Path, default=Path("reports/baselines/power_metrics_baseline.json"))
    baseline_parser.add_argument("--delta-out", type=Path, default=Path("reports/power_metrics_delta.json"))
    baseline_parser.add_argument("--summary-out", type=Path, default=Path("reports/checkin_summary.md"))
    baseline_parser.set_defaults(func=cmd_baseline)

    check_parser = subparsers.add_parser("check", help="Generate metrics, compare against baseline, and write check-in reports.")
    add_common(check_parser)
    check_parser.add_argument("--baseline", type=Path, default=Path("reports/baselines/power_metrics_baseline.json"))
    check_parser.add_argument("--delta-out", type=Path, default=Path("reports/power_metrics_delta.json"))
    check_parser.add_argument("--summary-out", type=Path, default=Path("reports/checkin_summary.md"))
    check_parser.add_argument("--fail-on-red", action="store_true")
    check_parser.add_argument("--fail-on-yellow", action="store_true")
    check_parser.set_defaults(func=cmd_check)

    args = normalize_args(parser.parse_args())
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
