#!/usr/bin/env python3
"""Small Liberty parser for the 2416 mapped-power reference flow.

This is intentionally a focused parser rather than a full Liberty frontend. It
extracts the fields needed by this project: cell area, leakage, pin
capacitance, sequential/combinational classification, and a representative
internal-power table average.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class LibertyCell:
    name: str
    area_um2: float
    leakage_nw: float
    leakage_mw: float
    input_cap_ff: float
    avg_internal_power_pj: float
    switching_energy_pj: float
    is_sequential: bool
    output_functions: dict[str, str]


def strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def find_groups(text: str, group: str) -> list[tuple[str, str]]:
    pattern = re.compile(rf"\b{re.escape(group)}\s*\(\s*([^)]+?)\s*\)\s*\{{", re.S)
    groups: list[tuple[str, str]] = []
    for match in pattern.finditer(text):
        name = match.group(1).strip().strip('"')
        start = match.end() - 1
        depth = 0
        for idx in range(start, len(text)):
            char = text[idx]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    groups.append((name, text[start + 1 : idx]))
                    break
    return groups


def attr_float(body: str, name: str, default: float = 0.0) -> float:
    match = re.search(rf"\b{re.escape(name)}\s*:\s*([-+0-9.eE]+)\s*;", body)
    return float(match.group(1)) if match else default


def attr_string(body: str, name: str, default: str = "") -> str:
    match = re.search(rf"\b{re.escape(name)}\s*:\s*\"([^\"]+)\"\s*;", body)
    return match.group(1) if match else default


def numbers_from_values(body: str) -> list[float]:
    values: list[float] = []
    for block in re.finditer(r"\bvalues\s*\((.*?)\)\s*;", body, flags=re.S):
        for quoted in re.findall(r'"([^"]+)"', block.group(1)):
            values.extend(float(item) for item in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", quoted))
    return values


def parse_cap_unit_ff(text: str) -> float:
    match = re.search(r"\bcapacitive_load_unit\s*\(\s*([-+0-9.eE]+)\s*,\s*([a-zA-Z]+)\s*\)\s*;", text)
    if not match:
        return 1.0
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "ff":
        return value
    if unit == "pf":
        return value * 1000.0
    if unit == "nf":
        return value * 1_000_000.0
    return value


def parse_leakage_unit_to_nw(text: str) -> float:
    unit = attr_string(text, "leakage_power_unit", "1nW").lower().replace(" ", "")
    match = re.match(r"([-+0-9.eE]+)([a-z]+)", unit)
    if not match:
        return 1.0
    value = float(match.group(1))
    suffix = match.group(2)
    if suffix == "nw":
        return value
    if suffix == "uw":
        return value * 1000.0
    if suffix == "mw":
        return value * 1_000_000.0
    if suffix == "w":
        return value * 1_000_000_000.0
    if suffix == "pw":
        return value / 1000.0
    return value


def parse_nominal_voltage(text: str) -> float:
    match = re.search(r"\bnom_voltage\s*:\s*([-+0-9.eE]+)\s*;", text)
    return float(match.group(1)) if match else 1.0


def pin_direction(pin_body: str) -> str:
    match = re.search(r"\bdirection\s*:\s*([a-zA-Z_]+)\s*;", pin_body)
    return match.group(1) if match else ""


def parse_cell(name: str, body: str, cap_unit_ff: float, leakage_unit_nw: float, voltage_v: float) -> LibertyCell:
    area = attr_float(body, "area")
    leakage_nw = attr_float(body, "cell_leakage_power") * leakage_unit_nw
    input_cap_ff = 0.0
    output_functions: dict[str, str] = {}
    for pin_name, pin_body in find_groups(body, "pin"):
        direction = pin_direction(pin_body)
        if direction == "input":
            input_cap_ff += attr_float(pin_body, "capacitance") * cap_unit_ff
        elif direction == "output":
            function = attr_string(pin_body, "function")
            if function:
                output_functions[pin_name] = function

    internal_values = numbers_from_values("\n".join(group_body for _, group_body in find_groups(body, "internal_power")))
    # Nangate's internal_power tables are used as a relative energy proxy here.
    # Scaling by 1e-3 keeps the per-toggle values in the same pJ range as the
    # simple macro models and avoids pretending this is signoff Liberty power.
    avg_internal_power_pj = (sum(abs(value) for value in internal_values) / len(internal_values) / 1000.0) if internal_values else 0.0
    cap_switching_pj = 0.5 * input_cap_ff * voltage_v * voltage_v / 1000.0
    is_sequential = bool(re.search(r"\b(ff|latch)\s*\(", body)) or name.upper().startswith(("DFF", "SDFF", "DLH", "DLL"))
    return LibertyCell(
        name=name,
        area_um2=area,
        leakage_nw=leakage_nw,
        leakage_mw=leakage_nw / 1_000_000.0,
        input_cap_ff=input_cap_ff,
        avg_internal_power_pj=avg_internal_power_pj,
        switching_energy_pj=avg_internal_power_pj + cap_switching_pj,
        is_sequential=is_sequential,
        output_functions=output_functions,
    )


def parse_liberty(path: Path) -> dict:
    text = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
    cap_unit_ff = parse_cap_unit_ff(text)
    leakage_unit_nw = parse_leakage_unit_to_nw(text)
    voltage_v = parse_nominal_voltage(text)
    cells = [
        parse_cell(name, body, cap_unit_ff, leakage_unit_nw, voltage_v)
        for name, body in find_groups(text, "cell")
    ]
    cells = [cell for cell in cells if cell.area_um2 > 0.0 or cell.leakage_nw > 0.0 or cell.output_functions or cell.is_sequential]
    return {
        "source": str(path),
        "nominal_voltage_v": voltage_v,
        "capacitive_load_unit_ff": cap_unit_ff,
        "leakage_power_unit_nw": leakage_unit_nw,
        "cell_count": len(cells),
        "cells": {cell.name: asdict(cell) for cell in sorted(cells, key=lambda item: item.name)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--liberty", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    summary = parse_liberty(args.liberty)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
