#!/usr/bin/env python3
"""Validate OpenLowPower IEEE 2416 XML libraries."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


REQUIRED_CELL_PARAMETERS = {
    "module",
    "rtl_path",
    "power_domain",
    "clock_name",
    "reference_voltage_v",
    "dynamic_voltage_exponent",
    "leakage_voltage_exponent",
}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[1] if "}" in tag else tag


def child(element: ET.Element, name: str) -> ET.Element | None:
    for candidate in element:
        if local_name(candidate.tag) == name:
            return candidate
    return None


def children(element: ET.Element, name: str) -> list[ET.Element]:
    return [candidate for candidate in element if local_name(candidate.tag) == name]


def collect_xml_paths(inputs: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for item in inputs:
        if item.is_dir():
            paths.extend(sorted(item.glob("*.xml")))
        else:
            paths.append(item)
    return paths


def validate_with_lxml(xsd: Path, xml: Path) -> list[str] | None:
    try:
        from lxml import etree
    except Exception:
        return None

    schema_doc = etree.parse(str(xsd))
    schema = etree.XMLSchema(schema_doc)
    xml_doc = etree.parse(str(xml))
    if schema.validate(xml_doc):
        return []
    return [f"{xml}: {error.message}" for error in schema.error_log]


def validate_with_xmllint(xsd: Path, xml: Path) -> list[str]:
    xmllint = shutil.which("xmllint")
    if not xmllint:
        return [f"xmllint not found and lxml is unavailable; cannot validate {xml} against {xsd}"]
    result = subprocess.run(
        [xmllint, "--noout", "--schema", str(xsd), str(xml)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return []
    message = (result.stderr or result.stdout).strip()
    return [message or f"{xml}: XSD validation failed"]


def xsd_validate(paths: list[Path], xsd: Path | None) -> list[str]:
    if xsd is None:
        return []
    if not xsd.exists():
        return [f"XSD not found: {xsd}"]

    errors: list[str] = []
    for path in paths:
        lxml_errors = validate_with_lxml(xsd, path)
        if lxml_errors is None:
            errors.extend(validate_with_xmllint(xsd, path))
        else:
            errors.extend(lxml_errors)
    return errors


def parse_float(value: str | None) -> bool:
    if value is None:
        return False
    try:
        float(value)
        return True
    except ValueError:
        return False


def validate_semantics(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return [f"{path}: XML parse error: {exc}"]

    if local_name(root.tag) != "Library":
        errors.append(f"{path}: root element must be Library")
    if root.attrib.get("name") == "":
        errors.append(f"{path}: Library name is empty")

    units = child(root, "Units")
    if units is None or not children(units, "Unit"):
        errors.append(f"{path}: Library must define Units")

    cells = children(root, "Cell")
    if not cells:
        errors.append(f"{path}: Library must contain at least one Cell")

    for cell in cells:
        cell_name = cell.attrib.get("name", "<unnamed>")
        pins = child(cell, "Pins")
        if pins is None or not children(pins, "Pin"):
            errors.append(f"{path}: Cell {cell_name} must contain Pins")

        model_params = child(cell, "ModelParameters")
        param_names = set()
        if model_params is not None:
            for param in children(model_params, "Parameter"):
                param_names.add(param.attrib.get("name", ""))
        missing = REQUIRED_CELL_PARAMETERS - param_names
        if missing:
            errors.append(f"{path}: Cell {cell_name} missing ModelParameters {sorted(missing)}")

        states = []
        for state_container in children(cell, "States"):
            states.extend(children(state_container, "State"))
        if not states:
            errors.append(f"{path}: Cell {cell_name} must contain States")
        for state in states:
            power_values = children(state, "StaticPower") + children(state, "DynamicPower")
            if not power_values:
                errors.append(f"{path}: Cell {cell_name} state {state.attrib.get('name')} has no power values")
            for power in power_values:
                if not parse_float(power.attrib.get("value")):
                    errors.append(f"{path}: Cell {cell_name} state {state.attrib.get('name')} has nonnumeric power value")

        events = child(cell, "Events")
        if events is not None:
            for event in children(events, "Event"):
                name = event.attrib.get("name", "")
                energy = child(event, "EnergyContributor")
                expression = child(event, "Expression")
                if energy is None and expression is None:
                    errors.append(f"{path}: Cell {cell_name} event {name} has no energy contributor or expression")
                if energy is not None and "value" in energy.attrib and not parse_float(energy.attrib.get("value")):
                    errors.append(f"{path}: Cell {cell_name} event {name} has nonnumeric energy value")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--xsd", type=Path)
    args = parser.parse_args()

    paths = collect_xml_paths(args.inputs)
    if not paths:
        print("No XML libraries found", file=sys.stderr)
        raise SystemExit(2)

    errors = xsd_validate(paths, args.xsd)
    for path in paths:
        errors.extend(validate_semantics(path))

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        raise SystemExit(1)

    suffix = f" against {args.xsd}" if args.xsd else ""
    print(f"validated {len(paths)} OpenLowPower IEEE 2416 XML librar{'y' if len(paths) == 1 else 'ies'}{suffix}")


if __name__ == "__main__":
    main()

