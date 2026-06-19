#!/usr/bin/env python3
"""Estimate power from an OpenLowPower IEEE 2416 Library and VCD activity."""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

if __package__ in {None, ""}:
    REPO_ROOT = Path(__file__).resolve().parents[2]
    TOOLS_ROOT = REPO_ROOT / "tools"
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(TOOLS_ROOT))

from tools.estimate_power_2416 import (
    PowerModel,
    VcdActivityExtractor,
    apply_scheme_profile,
    estimate,
    normalize_activity_time,
    write_reports,
)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[1] if "}" in tag else tag


def child(element: ET.Element, name: str) -> ET.Element | None:
    for candidate in element:
        if local_name(candidate.tag) == name:
            return candidate
    return None


def children(element: ET.Element, name: str) -> list[ET.Element]:
    return [candidate for candidate in element if local_name(candidate.tag) == name]


def fattr(element: ET.Element | None, name: str, default: float = 0.0) -> float:
    if element is None:
        return default
    try:
        return float(element.attrib.get(name, default))
    except ValueError:
        return default


def model_parameters(cell: ET.Element) -> dict[str, str]:
    params: dict[str, str] = {}
    params_element = child(cell, "ModelParameters")
    if params_element is None:
        return params
    for param in children(params_element, "Parameter"):
        name = param.attrib.get("name")
        if name:
            params[name] = param.attrib.get("value", "")
    return params


def state_static_power(cell: ET.Element) -> dict[str, float]:
    leakage: dict[str, float] = {}
    for states in children(cell, "States"):
        for state in children(states, "State"):
            state_name = state.attrib.get("name", "")
            static = child(state, "StaticPower")
            if state_name and static is not None:
                leakage[state_name] = fattr(static, "value")
    return leakage


def event_energies(cell: ET.Element) -> tuple[dict[str, float], float, float]:
    event_pj: dict[str, float] = {}
    clock_pj = 0.0
    toggle_pj = 0.0
    events = child(cell, "Events")
    if events is None:
        return event_pj, clock_pj, toggle_pj
    for event in children(events, "Event"):
        name = event.attrib.get("name", "")
        energy = child(event, "EnergyContributor")
        value = fattr(energy, "value") if energy is not None else 0.0
        if name == "clock_cycle":
            clock_pj = value
        elif name == "rtl_toggle":
            toggle_pj = value
        elif name:
            event_pj[name] = value
    return event_pj, clock_pj, toggle_pj


def load_library_models(path: Path) -> list[PowerModel]:
    root = ET.parse(path).getroot()
    if local_name(root.tag) != "Library":
        raise ValueError(f"{path} is not an OpenLowPower Library")

    models: list[PowerModel] = []
    for cell in children(root, "Cell"):
        params = model_parameters(cell)
        event_pj, clock_pj, toggle_pj = event_energies(cell)
        if toggle_pj == 0.0:
            try:
                toggle_pj = float(params.get("toggle_energy_pj", 0.0))
            except ValueError:
                toggle_pj = 0.0
        models.append(
            PowerModel(
                block=cell.attrib["name"],
                module=params.get("module", cell.attrib["name"]),
                rtl_path=params.get("rtl_path", ""),
                domain=params.get("power_domain", "PD_CPU"),
                clock=params.get("clock_name", "none"),
                leakage_mw_by_state=state_static_power(cell),
                event_pj=event_pj,
                clock_pj=clock_pj,
                toggle_pj=toggle_pj,
                reference_voltage_v=float(params.get("reference_voltage_v", "1.0")),
                dynamic_voltage_exponent=float(params.get("dynamic_voltage_exponent", "2.0")),
                leakage_voltage_exponent=float(params.get("leakage_voltage_exponent", "1.0")),
            )
        )
    return models


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=Path("power_models/mobile_cpu/p2416/mobile_cpu_library.xml"))
    parser.add_argument("--tech", type=Path, default=Path("configs/tech/generic_7nm.json"))
    parser.add_argument("--vcd", type=Path)
    parser.add_argument("--activity", type=Path)
    parser.add_argument("--out", type=Path, default=Path("reports/p2416"))
    parser.add_argument("--scheme", default="dvfs_retention_domains")
    args = parser.parse_args()

    if not args.vcd and not args.activity:
        print("Either --vcd or --activity is required", file=sys.stderr)
        raise SystemExit(2)

    tech = json.loads(args.tech.read_text(encoding="utf-8"))
    models = load_library_models(args.model)
    if not models:
        print(f"No Cell models found in {args.model}", file=sys.stderr)
        raise SystemExit(2)

    if args.activity:
        activity = json.loads(args.activity.read_text(encoding="utf-8"))
    else:
        assert args.vcd is not None
        activity = VcdActivityExtractor(args.vcd).extract()
        args.out.mkdir(parents=True, exist_ok=True)
        activity_text = json.dumps(activity, indent=2) + "\n"
        (args.out / "p2416_activity.json").write_text(activity_text, encoding="utf-8")
        (args.out / "2416_activity.json").write_text(activity_text, encoding="utf-8")

    activity = normalize_activity_time(activity, tech)
    activity = apply_scheme_profile(activity, args.scheme)
    result = estimate(models, activity, tech)
    result["model_format"] = "OpenLowPower IEEE 2416 Library"
    result["model_source"] = str(args.model)
    write_reports(result, args.out)
    print(f"wrote {args.out / '2416_power_summary.md'}")


if __name__ == "__main__":
    main()

