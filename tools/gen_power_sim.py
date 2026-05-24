#!/usr/bin/env python3
"""Generate Verilator power-aware simulation metadata from a power scheme."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional

from power_intent import PowerIntent, load_scheme


def cpp_string(value: str) -> str:
    return json.dumps(value)


def cpp_bool(value: bool) -> str:
    return "true" if value else "false"


def state_is_on(intent: PowerIntent, power_state_name: str, domain_name: str) -> bool:
    if not intent.has_domain(domain_name):
        return True
    if not intent.has_power_state(power_state_name):
        return True
    return intent.state_is_on(domain_name, power_state_name)


def state_voltage(intent: PowerIntent, power_state_name: str, domain_name: str) -> float:
    if not intent.has_domain(domain_name) or not intent.has_power_state(power_state_name):
        return 0.0
    voltage = intent.state_voltage(domain_name, power_state_name)
    return 0.0 if voltage is None else voltage


def has_feature(intent: PowerIntent, domain_name: str, feature: str) -> bool:
    if not intent.has_domain(domain_name):
        return False
    return getattr(intent.domain(domain_name), feature) is not None


def emit_header(intent: PowerIntent) -> str:
    metadata = intent.to_metadata()
    crossings = metadata["features"]["voltage_crossing_count"]
    power_states = {state.name for state in intent.power_states}

    lines = [
        "#pragma once",
        "",
        "#include <array>",
        "#include <cstddef>",
        "",
        "namespace power_intent {",
        "",
        "struct LegalCombo {",
        "  const char* name;",
        "  bool pd_aon_on;",
        "  bool pd_cpu_on;",
        "  bool pd_mem_on;",
        "  double pd_aon_voltage;",
        "  double pd_cpu_voltage;",
        "  double pd_mem_voltage;",
        "};",
        "",
        f"constexpr const char* kSchemeName = {cpp_string(intent.name)};",
        f"constexpr const char* kSourcePath = {cpp_string(intent.source.as_posix())};",
        f"constexpr bool kHasPdAon = {cpp_bool(intent.has_domain('PD_AON'))};",
        f"constexpr bool kHasPdCpu = {cpp_bool(intent.has_domain('PD_CPU'))};",
        f"constexpr bool kHasPdMem = {cpp_bool(intent.has_domain('PD_MEM'))};",
        f"constexpr bool kCpuHasSwitch = {cpp_bool(has_feature(intent, 'PD_CPU', 'switch'))};",
        f"constexpr bool kMemHasSwitch = {cpp_bool(has_feature(intent, 'PD_MEM', 'switch'))};",
        f"constexpr bool kCpuHasIsolation = {cpp_bool(has_feature(intent, 'PD_CPU', 'isolation'))};",
        f"constexpr bool kMemHasIsolation = {cpp_bool(has_feature(intent, 'PD_MEM', 'isolation'))};",
        f"constexpr bool kCpuHasRetention = {cpp_bool(has_feature(intent, 'PD_CPU', 'retention'))};",
        f"constexpr bool kMemHasRetention = {cpp_bool(has_feature(intent, 'PD_MEM', 'retention'))};",
        f"constexpr bool kHasTurboState = {cpp_bool('TURBO' in power_states)};",
        f"constexpr bool kHasNominalState = {cpp_bool('NOMINAL' in power_states)};",
        f"constexpr bool kHasLowPowerState = {cpp_bool('LOW_POWER' in power_states)};",
        f"constexpr bool kHasDeepSleepState = {cpp_bool('DEEP_SLEEP' in power_states)};",
        f"constexpr int kLevelShifterCount = {len(intent.level_shifters)};",
        f"constexpr bool kNeedsVoltageLevelShifters = {cpp_bool(crossings > 0)};",
        "constexpr int kTurboDvfsLevel = 2;",
        "constexpr int kNominalDvfsLevel = 1;",
        "constexpr int kLowPowerDvfsLevel = 0;",
        "",
        f"constexpr std::array<LegalCombo, {len(intent.power_states)}> kLegalCombos = {{{{",
    ]

    for state in intent.power_states:
        lines.append(
            "  {"
            + f"{cpp_string(state.name)}, "
            + f"{cpp_bool(state_is_on(intent, state.name, 'PD_AON'))}, "
            + f"{cpp_bool(state_is_on(intent, state.name, 'PD_CPU'))}, "
            + f"{cpp_bool(state_is_on(intent, state.name, 'PD_MEM'))}, "
            + f"{state_voltage(intent, state.name, 'PD_AON'):.3f}, "
            + f"{state_voltage(intent, state.name, 'PD_CPU'):.3f}, "
            + f"{state_voltage(intent, state.name, 'PD_MEM'):.3f}"
            + "},"
        )

    lines.extend(
        [
            "}};",
            "",
            "inline bool legal_domain_combo(bool pd_aon_on, bool pd_cpu_on, bool pd_mem_on) {",
            "  for (const auto& combo : kLegalCombos) {",
            "    if (combo.pd_aon_on == pd_aon_on && combo.pd_cpu_on == pd_cpu_on &&",
            "        combo.pd_mem_on == pd_mem_on) {",
            "      return true;",
            "    }",
            "  }",
            "  return false;",
            "}",
            "",
            "}  // namespace power_intent",
            "",
        ]
    )
    return "\n".join(lines)


def emit_markdown(intent: PowerIntent, metadata: dict[str, Any]) -> str:
    rows = [
        "# Power Simulation Metadata",
        "",
        f"- Scheme: `{intent.name}`",
        f"- Source: `{intent.source.as_posix()}`",
        f"- Domains: {metadata['features']['domain_count']}",
        f"- Legal power states: {metadata['features']['power_state_count']}",
        f"- Switched domains: {metadata['features']['switched_domain_count']}",
        f"- Isolated domains: {metadata['features']['isolated_domain_count']}",
        f"- Retained domains: {metadata['features']['retained_domain_count']}",
        f"- Level shifters: {metadata['features']['level_shifter_count']}",
        f"- Voltage crossings needing level-shifter coverage: {metadata['features']['voltage_crossing_count']}",
        "",
        "| Power state | Domain states |",
        "| --- | --- |",
    ]
    for power_state in intent.power_states:
        state_text = ", ".join(
            f"{domain}={state}" for domain, state in power_state.domain_states.items()
        )
        rows.append(f"| {power_state.name} | {state_text} |")
    rows.append("")
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scheme", required=True, help="Scheme name or JSON path")
    parser.add_argument("--schemes", type=Path, default=Path("power_schemes"))
    parser.add_argument("--out", type=Path, default=Path("build/power_sim"))
    args = parser.parse_args()

    intent = load_scheme(args.scheme, args.schemes)
    metadata = intent.to_metadata()

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "power_intent.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.out / "power_intent.hpp").write_text(emit_header(intent), encoding="utf-8")
    (args.out / "power_intent.md").write_text(emit_markdown(intent, metadata), encoding="utf-8")

    print(f"wrote {args.out / 'power_intent.json'}")
    print(f"wrote {args.out / 'power_intent.hpp'}")
    print(f"wrote {args.out / 'power_intent.md'}")


if __name__ == "__main__":
    main()

