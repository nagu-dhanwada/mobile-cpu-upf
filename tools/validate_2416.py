#!/usr/bin/env python3
"""Validate IEEE 2416 reference XML power models for structural consistency."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET


NS = "https://standards.ieee.org/ieee/2416/2025/power-model"
REQUIRED_CHILDREN = {
    "metadata",
    "design",
    "operatingConditions",
    "powerStates",
    "activityParameters",
    "powerComponents",
    "powerContributors",
    "scaling",
    "validity",
}
POWER_STATES = {"RUN", "IDLE", "LIGHT_SLEEP", "DEEP_SLEEP", "WAKE"}
CONTRIBUTOR_TYPES = {"static", "clock", "event", "toggle", "transition"}


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def child(element: ET.Element, name: str) -> ET.Element | None:
    for candidate in element:
        if local_name(candidate.tag) == name:
            return candidate
    return None


def children(element: ET.Element, name: str) -> list[ET.Element]:
    return [candidate for candidate in element if local_name(candidate.tag) == name]


def collect_model_paths(inputs: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for item in inputs:
        if item.is_dir():
            paths.extend(sorted(item.glob("*.xml")))
        else:
            paths.append(item)
    return paths


def maybe_xsd_validate(paths: list[Path], xsd: Path | None) -> list[str]:
    if not xsd:
        return []
    xmllint = shutil.which("xmllint")
    if not xmllint:
        return [f"INFO: xmllint not found; skipped XSD validation against {xsd}"]
    messages: list[str] = []
    for path in paths:
        result = subprocess.run(
            [xmllint, "--noout", "--schema", str(xsd), str(path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            messages.append(result.stderr.strip() or f"{path}: XSD validation failed")
    return messages


def validate_model(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return [f"{path}: XML parse error: {exc}"]

    if local_name(root.tag) != "powerModel":
        errors.append(f"{path}: root element must be powerModel")
    if root.attrib.get("standard") != "IEEE2416-2025":
        errors.append(f"{path}: standard attribute must be IEEE2416-2025")
    if root.attrib.get("modelClass") not in {"rtlMacro", "synthesisCalibratedMacro", "implementationMacro"}:
        errors.append(f"{path}: invalid or missing modelClass")
    if root.attrib.get("abstractionLevel") not in {"rtl", "gate", "physical", "system"}:
        errors.append(f"{path}: invalid or missing abstractionLevel")

    present = {local_name(item.tag) for item in root}
    for required in sorted(REQUIRED_CHILDREN - present):
        errors.append(f"{path}: missing required element {required}")

    design = child(root, "design")
    design_domain = ""
    if design is not None:
        for attr in ("block", "module", "rtlPath", "powerDomain", "clock"):
            if not design.attrib.get(attr):
                errors.append(f"{path}: design missing {attr}")
        design_domain = design.attrib.get("powerDomain", "")

    power_states = child(root, "powerStates")
    seen_states: set[str] = set()
    if power_states is not None:
        for state in children(power_states, "state"):
            name = state.attrib.get("name", "")
            seen_states.add(name)
            for attr in ("supply", "clock", "isolation", "retention", "leakageMw"):
                if attr not in state.attrib:
                    errors.append(f"{path}: state {name} missing {attr}")
            try:
                float(state.attrib.get("leakageMw", "nan"))
            except ValueError:
                errors.append(f"{path}: state {name} leakageMw must be numeric")
    missing_states = POWER_STATES - seen_states
    if missing_states:
        errors.append(f"{path}: missing power states {sorted(missing_states)}")

    activity = child(root, "activityParameters")
    event_names = set()
    if activity is not None:
        for event in children(activity, "event"):
            event_names.add(event.attrib.get("name", ""))

    components = child(root, "powerComponents")
    component_names: set[str] = set()
    if components is not None:
        for component in children(components, "component"):
            ctype = component.attrib.get("type", "")
            ref = component.attrib.get("ref", "")
            name = component.attrib.get("name", "")
            component_names.add(name)
            for attr in ("type", "name", "value", "unit"):
                if attr not in component.attrib:
                    errors.append(f"{path}: component {name} missing {attr}")
            try:
                float(component.attrib.get("value", "nan"))
            except ValueError:
                errors.append(f"{path}: component {name} value must be numeric")
            if ctype in {"event", "clock"} and ref not in event_names:
                errors.append(f"{path}: component {name} references undefined event {ref}")
            if ctype == "leakage" and ref not in POWER_STATES:
                errors.append(f"{path}: leakage component {name} references invalid state {ref}")

    contributors = child(root, "powerContributors")
    if contributors is not None:
        for contributor in children(contributors, "contributor"):
            name = contributor.attrib.get("name", "")
            for attr in (
                "name",
                "type",
                "domain",
                "driver",
                "componentRef",
                "pvtDependency",
                "voltageDependency",
                "frequencyDependency",
                "stateDependency",
                "workloadDependency",
            ):
                if attr not in contributor.attrib:
                    errors.append(f"{path}: contributor {name} missing {attr}")
            ctype = contributor.attrib.get("type", "")
            if ctype not in CONTRIBUTOR_TYPES:
                errors.append(f"{path}: contributor {name} has invalid type {ctype}")
            domain = contributor.attrib.get("domain", "")
            if design_domain and domain != design_domain:
                errors.append(f"{path}: contributor {name} domain {domain} does not match design domain {design_domain}")
            component_ref = contributor.attrib.get("componentRef", "")
            if component_ref and component_ref not in component_names:
                errors.append(f"{path}: contributor {name} references undefined component {component_ref}")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--xsd", type=Path)
    args = parser.parse_args()

    paths = collect_model_paths(args.inputs)
    if not paths:
        print("No XML models found", file=sys.stderr)
        raise SystemExit(2)

    messages = maybe_xsd_validate(paths, args.xsd)
    errors: list[str] = []
    for path in paths:
        errors.extend(validate_model(path))

    for message in messages:
        print(message)
        if not message.startswith("INFO:"):
            errors.append(message)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        raise SystemExit(1)

    print(f"validated {len(paths)} IEEE 2416 power model(s)")


if __name__ == "__main__":
    main()
