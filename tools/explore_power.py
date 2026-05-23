#!/usr/bin/env python3
"""Estimate relative power for the JSON power schemes."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


MODULE_POWER_MW = {
    "u_power_controller": {"dynamic": 1.0, "leakage": 0.20},
    "u_core_clk_gate": {"dynamic": 0.2, "leakage": 0.03},
    "u_mem_clk_gate": {"dynamic": 0.2, "leakage": 0.03},
    "u_fetch": {"dynamic": 5.0, "leakage": 0.90},
    "u_icache": {"dynamic": 7.0, "leakage": 1.40},
    "u_decode": {"dynamic": 3.0, "leakage": 0.50},
    "u_regfile": {"dynamic": 5.5, "leakage": 1.10},
    "u_execute": {"dynamic": 8.0, "leakage": 1.30},
    "u_dmem": {"dynamic": 8.5, "leakage": 1.70}
}

ALL_MODULES = list(MODULE_POWER_MW)


def slug(name: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in name.lower()).strip("_")


def expand_elements(elements: list[str]) -> list[str]:
    if "." in elements:
        return ALL_MODULES
    return elements


def state_lookup(domain: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {state["name"]: state for state in domain.get("states", [])}


def voltage_for_state(domain: dict[str, Any], state_name: str) -> float:
    state = state_lookup(domain)[state_name]
    if state.get("kind", "FULL_ON").upper() == "OFF":
        return 0.0
    return float(state.get("voltage", 0.80))


def is_off(domain: dict[str, Any], state_name: str) -> bool:
    state = state_lookup(domain)[state_name]
    return state.get("kind", "FULL_ON").upper() == "OFF"


def estimate_scheme(scheme: dict[str, Any]) -> dict[str, float | str]:
    estimation = scheme.get("estimation", {})
    state_mix = estimation.get("state_mix", {})
    activity_by_state = estimation.get("activity_by_power_state", {})
    clock_gating_efficiency = float(estimation.get("clock_gating_efficiency", 0.0))
    frequency_mhz = float(estimation.get("frequency_mhz", 900.0))
    retention_overhead_mw = float(estimation.get("retention_overhead_mw", 0.0))

    power_state_lookup = {state["name"]: state for state in scheme["power_states"]}
    domain_lookup = {domain["name"]: domain for domain in scheme["domains"]}

    weighted_dynamic = 0.0
    weighted_leakage = 0.0

    for state_name, fraction in state_mix.items():
        fraction = float(fraction)
        power_state = power_state_lookup[state_name]
        activity = float(activity_by_state.get(state_name, 1.0))
        dynamic = 0.0
        leakage = 0.0

        for domain_name, domain_state in power_state["domain_states"].items():
            domain = domain_lookup[domain_name]
            elements = expand_elements(domain["elements"])
            voltage = voltage_for_state(domain, domain_state)

            for element in elements:
                module_power = MODULE_POWER_MW[element]
                if is_off(domain, domain_state):
                    leakage += module_power["leakage"] * 0.03
                    continue

                voltage_scale = voltage / 0.80
                frequency_scale = frequency_mhz / 900.0
                gated_activity = activity * (1.0 - clock_gating_efficiency)
                dynamic += module_power["dynamic"] * gated_activity * (voltage_scale ** 2) * frequency_scale
                leakage += module_power["leakage"] * max(voltage_scale, 0.30)

        if "SLEEP" in state_name or "OFF" in state_name:
            leakage += retention_overhead_mw

        weighted_dynamic += fraction * dynamic
        weighted_leakage += fraction * leakage

    total = weighted_dynamic + weighted_leakage
    return {
        "scheme": scheme["name"],
        "dynamic_mw": round(weighted_dynamic, 3),
        "leakage_mw": round(weighted_leakage, 3),
        "total_mw": round(total, 3),
        "relative_to_baseline": 0.0
    }


def load_schemes(schemes_dir: Path) -> list[dict[str, Any]]:
    schemes: list[dict[str, Any]] = []
    for path in sorted(schemes_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            schemes.append(json.load(handle))
    if not schemes:
        raise ValueError(f"No JSON schemes found in {schemes_dir}")
    return schemes


def write_csv(out_dir: Path, rows: list[dict[str, float | str]]) -> None:
    with (out_dir / "power_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["scheme", "dynamic_mw", "leakage_mw", "total_mw", "relative_to_baseline"]
        )
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(out_dir: Path, rows: list[dict[str, float | str]]) -> None:
    lines = [
        "# Power Exploration Summary",
        "",
        "These numbers are architectural estimates for comparing schemes before a real",
        "implementation power analysis flow. Treat absolute values as placeholders and",
        "relative ordering as the useful signal.",
        "",
        "| Scheme | Dynamic mW | Leakage mW | Total mW | Relative to baseline |",
        "| --- | ---: | ---: | ---: | ---: |"
    ]
    for row in rows:
        lines.append(
            f"| {row['scheme']} | {row['dynamic_mw']} | {row['leakage_mw']} | "
            f"{row['total_mw']} | {row['relative_to_baseline']}% |"
        )
    lines.append("")
    (out_dir / "power_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schemes", type=Path, default=Path("power_schemes"))
    parser.add_argument("--out", type=Path, default=Path("reports"))
    args = parser.parse_args()

    schemes = load_schemes(args.schemes)
    rows = [estimate_scheme(scheme) for scheme in schemes]
    baseline = float(rows[0]["total_mw"])
    for row in rows:
        relative = 100.0 * (float(row["total_mw"]) / baseline)
        row["relative_to_baseline"] = round(relative, 1)

    rows.sort(key=lambda row: float(row["total_mw"]))
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out, rows)
    write_markdown(args.out, rows)

    print(f"wrote {args.out / 'power_summary.csv'}")
    print(f"wrote {args.out / 'power_summary.md'}")


if __name__ == "__main__":
    main()

