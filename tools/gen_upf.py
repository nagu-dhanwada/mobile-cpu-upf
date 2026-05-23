#!/usr/bin/env python3
"""Generate UPF files from JSON power-scheme descriptions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def tcl_list(items: list[str]) -> str:
    return "{" + " ".join(items) + "}"


def slug(name: str) -> str:
    allowed = []
    for char in name.lower():
        if char.isalnum():
            allowed.append(char)
        elif char in {"-", "_", " "}:
            allowed.append("_")
    return "".join(allowed).strip("_")


def fmt_voltage(value: float) -> str:
    text = f"{value:.3f}"
    return text.rstrip("0").rstrip(".")


def supply_expr(state: dict[str, Any]) -> str:
    kind = state.get("kind", "FULL_ON").upper()
    if kind == "OFF":
        power = "{OFF}"
    else:
        if "voltage" not in state:
            raise ValueError(f"State {state.get('name')} needs a voltage")
        power = "`{" + kind + ", " + fmt_voltage(float(state["voltage"])) + "}"
    return "{power == " + power + " && ground == `{FULL_ON, 0}}"


def domain_supply_set(domain_name: str) -> str:
    clean = domain_name[3:] if domain_name.startswith("PD_") else domain_name
    return f"SS_{clean}"


def collect_supply_names(scheme: dict[str, Any]) -> list[str]:
    names: list[str] = []

    def add(name: str) -> None:
        if name not in names:
            names.append(name)

    for domain in scheme["domains"]:
        add(domain["supply"])
        add(domain.get("ground", "VSS"))
        switch = domain.get("switch")
        if switch:
            add(switch["input_supply"])
        retention = domain.get("retention")
        if retention:
            add(retention.get("retention_supply", domain["supply"]))
            add(retention.get("ground", domain.get("ground", "VSS")))
    return names


def validate_scheme(scheme: dict[str, Any], source: Path) -> None:
    for key in ["name", "top", "domains", "power_states"]:
        if key not in scheme:
            raise ValueError(f"{source}: missing required key {key}")
    if not scheme["domains"]:
        raise ValueError(f"{source}: at least one domain is required")

    domain_names = {domain["name"] for domain in scheme["domains"]}
    for power_state in scheme["power_states"]:
        missing = domain_names - set(power_state.get("domain_states", {}))
        if missing:
            raise ValueError(
                f"{source}: power state {power_state['name']} misses domains {sorted(missing)}"
            )


def emit_header(lines: list[str], scheme: dict[str, Any], source: Path) -> None:
    lines.extend(
        [
            f"# Generated from {source.as_posix()}",
            f"# Scheme: {scheme['name']}",
            f"# {scheme.get('description', '').strip()}",
            "# Regenerate with: python3 tools/gen_upf.py --schemes power_schemes --out upf",
            "",
            f"upf_version {scheme.get('upf_version', '2.1')}",
            f"set_design_top {scheme['top']}",
            "",
        ]
    )

    for note in scheme.get("notes", []):
        lines.append(f"# Note: {note}")
    if scheme.get("notes"):
        lines.append("")


def emit_supplies(lines: list[str], scheme: dict[str, Any]) -> None:
    lines.append("# Supply ports and nets")
    for supply_name in collect_supply_names(scheme):
        lines.append(f"create_supply_port {supply_name}")
        lines.append(f"create_supply_net {supply_name}")
        lines.append(f"connect_supply_net {supply_name} -ports {supply_name}")
    lines.append("")


def emit_domains(lines: list[str], scheme: dict[str, Any]) -> None:
    lines.append("# Power domains and supply sets")
    for domain in scheme["domains"]:
        name = domain["name"]
        if domain.get("include_scope"):
            lines.append(f"create_power_domain {name} -include_scope")
        else:
            lines.append(f"create_power_domain {name} -elements {tcl_list(domain['elements'])}")

        supply_set = domain_supply_set(name)
        lines.append(
            f"create_supply_set {supply_set} "
            f"-function {{power {domain['supply']}}} "
            f"-function {{ground {domain.get('ground', 'VSS')}}}"
        )
        lines.append(
            f"set_domain_supply_net {name} "
            f"-primary_power_net {domain['supply']} "
            f"-primary_ground_net {domain.get('ground', 'VSS')}"
        )

        for state in domain.get("states", []):
            lines.append(
                f"add_power_state {supply_set} -state {state['name']} "
                f"-supply_expr {supply_expr(state)}"
            )
        lines.append("")


def emit_switches(lines: list[str], scheme: dict[str, Any]) -> None:
    blocks: list[str] = []
    for domain in scheme["domains"]:
        switch = domain.get("switch")
        if not switch:
            continue
        on_when = switch.get("on_when", "CTRL")
        off_when = switch.get("off_when", "!CTRL")
        blocks.extend(
            [
                f"create_power_switch {switch['name']} \\",
                f"  -domain {domain['name']} \\",
                f"  -input_supply_port {{VIN {switch['input_supply']}}} \\",
                f"  -output_supply_port {{VOUT {domain['supply']}}} \\",
                f"  -control_port {{CTRL {switch['control']}}} \\",
                f"  -on_state {{ON VIN {{{on_when}}}}} \\",
                f"  -off_state {{OFF {{{off_when}}}}}",
                "",
            ]
        )
    if blocks:
        lines.append("# Power switches")
        lines.extend(blocks)


def emit_isolation(lines: list[str], scheme: dict[str, Any]) -> None:
    blocks: list[str] = []
    for domain in scheme["domains"]:
        isolation = domain.get("isolation")
        if not isolation:
            continue
        blocks.append(
            f"set_isolation {isolation['name']} "
            f"-domain {domain['name']} "
            f"-applies_to {isolation.get('applies_to', 'outputs')} "
            f"-clamp_value {isolation.get('clamp', 0)} "
            f"-isolation_signal {isolation['signal']} "
            f"-isolation_sense {isolation.get('sense', 'high')} "
            f"-location {isolation.get('location', 'parent')}"
        )
    if blocks:
        lines.append("# Isolation")
        lines.extend(blocks)
        lines.append("")


def emit_retention(lines: list[str], scheme: dict[str, Any]) -> None:
    blocks: list[str] = []
    for domain in scheme["domains"]:
        retention = domain.get("retention")
        if not retention:
            continue
        blocks.extend(
            [
                f"set_retention {retention['name']} "
                f"-domain {domain['name']} "
                f"-elements {tcl_list(retention.get('elements', domain['elements']))} "
                f"-retention_power_net {retention.get('retention_supply', domain['supply'])} "
                f"-retention_ground_net {retention.get('ground', domain.get('ground', 'VSS'))}",
                f"set_retention_control {retention['name']} "
                f"-domain {domain['name']} "
                f"-save_signal {{{retention['save_signal']} high}} "
                f"-restore_signal {{{retention['restore_signal']} high}}",
            ]
        )
    if blocks:
        lines.append("# Retention")
        lines.extend(blocks)
        lines.append("")


def emit_level_shifters(lines: list[str], scheme: dict[str, Any]) -> None:
    shifters = scheme.get("level_shifters", [])
    if not shifters:
        return
    lines.append("# Level shifters")
    for shifter in shifters:
        lines.append(
            f"set_level_shifter {shifter['name']} "
            f"-domain {shifter['domain']} "
            f"-applies_to {shifter.get('applies_to', 'both')} "
            f"-rule {shifter.get('rule', 'both')} "
            f"-location {shifter.get('location', 'parent')}"
        )
    lines.append("")


def emit_power_state_table(lines: list[str], scheme: dict[str, Any]) -> None:
    domains = [domain["name"] for domain in scheme["domains"]]
    supplies = [domain["supply"] for domain in scheme["domains"]]
    pst_name = "PST_" + slug(scheme["name"]).upper()

    lines.append("# System power state table")
    lines.append(f"create_pst {pst_name} -supplies {tcl_list(supplies)}")
    for power_state in scheme["power_states"]:
        state_values = [power_state["domain_states"][domain] for domain in domains]
        lines.append(
            f"add_pst_state {power_state['name']} "
            f"-pst {pst_name} "
            f"-state {tcl_list(state_values)}"
        )
    lines.append("")


def render_upf(scheme: dict[str, Any], source: Path) -> str:
    validate_scheme(scheme, source)
    lines: list[str] = []
    emit_header(lines, scheme, source)
    emit_supplies(lines, scheme)
    emit_domains(lines, scheme)
    emit_switches(lines, scheme)
    emit_isolation(lines, scheme)
    emit_retention(lines, scheme)
    emit_level_shifters(lines, scheme)
    emit_power_state_table(lines, scheme)
    return "\n".join(lines).rstrip() + "\n"


def read_schemes(schemes_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    schemes: list[tuple[Path, dict[str, Any]]] = []
    for source in sorted(schemes_dir.glob("*.json")):
        with source.open("r", encoding="utf-8") as handle:
            scheme = json.load(handle)
        validate_scheme(scheme, source)
        schemes.append((source, scheme))
    if not schemes:
        raise ValueError(f"No JSON schemes found in {schemes_dir}")
    return schemes


def write_index(out_dir: Path, schemes: list[tuple[Path, dict[str, Any]]]) -> None:
    rows = [
        "# Generated UPF Index",
        "",
        "| Scheme | UPF | Domains | Power states |",
        "| --- | --- | --- | --- |",
    ]
    for _, scheme in schemes:
        upf_name = slug(scheme["name"]) + ".upf"
        domains = ", ".join(domain["name"] for domain in scheme["domains"])
        states = ", ".join(state["name"] for state in scheme["power_states"])
        rows.append(f"| {scheme['name']} | `{upf_name}` | {domains} | {states} |")
    rows.append("")
    (out_dir / "index.md").write_text("\n".join(rows), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schemes", type=Path, default=Path("power_schemes"))
    parser.add_argument("--out", type=Path, default=Path("upf"))
    args = parser.parse_args()

    schemes = read_schemes(args.schemes)
    args.out.mkdir(parents=True, exist_ok=True)

    for source, scheme in schemes:
        upf_text = render_upf(scheme, source)
        out_file = args.out / f"{slug(scheme['name'])}.upf"
        out_file.write_text(upf_text, encoding="utf-8")
        print(f"wrote {out_file}")

    write_index(args.out, schemes)
    print(f"wrote {args.out / 'index.md'}")


if __name__ == "__main__":
    main()
