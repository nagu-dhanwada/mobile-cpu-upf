"""XML writer for the OpenLowPower IEEE 2416 internal representation."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

from .ir import (
    OPENLOWPOWER_NS,
    Cell,
    Event,
    GlobalExpression,
    Library,
    LibraryParameter,
    Mode,
    ModelParameter,
    Pin,
    PowerValue,
    State,
    Technology,
    UnitDef,
    fmt_float,
)


ET.register_namespace("", OPENLOWPOWER_NS)


def qname(name: str) -> str:
    return f"{{{OPENLOWPOWER_NS}}}{name}"


def attrs(**items: object) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in items.items():
        if value is None:
            continue
        if isinstance(value, float):
            result[key] = fmt_float(value)
        else:
            result[key] = str(value)
    return result


def add_text(parent: ET.Element, element_name: str, text: str, **attributes: object) -> ET.Element:
    element = ET.SubElement(parent, qname(element_name), attrs(**attributes))
    element.text = text
    return element


def write_units(parent: ET.Element, units: Iterable[UnitDef]) -> None:
    units_element = ET.SubElement(parent, qname("Units"))
    for unit in units:
        ET.SubElement(
            units_element,
            qname("Unit"),
            attrs(name=unit.name, value=unit.value, min=unit.min, max=unit.max),
        )


def write_technology(parent: ET.Element, technology: Technology) -> None:
    tech_element = ET.SubElement(parent, qname("Technology"), attrs(name=technology.name, version=technology.version))
    for process in technology.processes:
        process_attrs = attrs(name=process.name, version=process.version)
        process_attrs.update(process.attributes)
        ET.SubElement(tech_element, qname("Process"), process_attrs)


def write_library_parameters(parent: ET.Element, parameters: Iterable[LibraryParameter]) -> None:
    params = list(parameters)
    if not params:
        return
    params_element = ET.SubElement(parent, qname("LibraryParameters"))
    for parameter in params:
        ET.SubElement(
            params_element,
            qname("Parameter"),
            attrs(
                name=parameter.name,
                alias=parameter.alias,
                value=parameter.value,
                type=parameter.type,
                dataType=parameter.data_type,
                units=parameter.units,
                min=parameter.min,
                max=parameter.max,
            ),
        )


def write_conditions(parent: ET.Element, library: Library) -> None:
    for condition_set in library.conditions:
        conditions = ET.SubElement(parent, qname("LibraryConditions"), attrs(name=condition_set.name))
        for condition in condition_set.conditions:
            ET.SubElement(conditions, qname("Condition"), attrs(name=condition.name, value=condition.value))


def write_expressions(parent: ET.Element, expressions: Iterable[GlobalExpression]) -> None:
    expressions = list(expressions)
    if not expressions:
        return
    element = ET.SubElement(parent, qname("LibraryExpressions"))
    for expression in expressions:
        add_text(
            element,
            "Expression",
            expression.text,
            name=expression.name,
            source=expression.source,
            sink=expression.sink,
        )


def write_pins(parent: ET.Element, pins: Iterable[Pin]) -> None:
    pins_element = ET.SubElement(parent, qname("Pins"))
    for pin in pins:
        ET.SubElement(
            pins_element,
            qname("Pin"),
            attrs(
                name=pin.name,
                width=pin.width,
                direction=pin.direction,
                dataType=pin.data_type,
                capacitance=pin.capacitance,
                pinType=pin.pin_type,
                pinReference=pin.pin_reference,
                relatedPower=pin.related_power,
                relatedGround=pin.related_ground,
                condition=pin.condition,
            ),
        )


def write_modes(parent: ET.Element, modes: Iterable[Mode]) -> None:
    modes = list(modes)
    if not modes:
        return
    modes_element = ET.SubElement(
        parent,
        qname("Modes"),
        attrs(mutuallyExclusive="true", defaultMode=modes[0].name, initialMode=modes[0].name),
    )
    for mode in modes:
        mode_element = ET.SubElement(
            modes_element,
            qname("Mode"),
            attrs(
                name=mode.name,
                when=mode.when,
                value=mode.value,
                units=mode.units,
                source=mode.source,
                sink=mode.sink,
            ),
        )
        add_text(mode_element, "Expression", mode.expression or mode.when)


def write_event(parent: ET.Element, event: Event) -> None:
    event_element = ET.SubElement(
        parent,
        qname("Event"),
        attrs(
            name=event.name,
            mode=event.mode,
            style=event.style,
            when=event.when,
            inputPin=event.input_pin,
            inputTransition=event.input_transition,
            outputPin=event.output_pin,
            outputTransition=event.output_transition,
            nextMode=event.next_mode,
            trigger=event.trigger,
            triggerTransition=event.trigger_transition,
        ),
    )
    if event.energy is not None:
        ET.SubElement(
            event_element,
            qname("EnergyContributor"),
            attrs(
                name=event.energy.contributor,
                type=event.energy.type,
                quantity=event.energy.quantity,
                capacitance=event.energy.capacitance,
                value=event.energy.value,
            ),
        )
    else:
        add_text(event_element, "Expression", event.expression or "0")


def write_events(parent: ET.Element, events: Iterable[Event]) -> None:
    events = list(events)
    if not events:
        return
    events_element = ET.SubElement(parent, qname("Events"))
    for event in events:
        write_event(events_element, event)


def write_cell_parameters(parent: ET.Element, parameters: Iterable[LibraryParameter]) -> None:
    parameters = list(parameters)
    if not parameters:
        return
    params_element = ET.SubElement(parent, qname("CellParameters"))
    for parameter in parameters:
        ET.SubElement(
            params_element,
            qname("Parameter"),
            attrs(name=parameter.name, dataType=parameter.data_type, units=parameter.units),
        )


def write_model_parameters(parent: ET.Element, parameters: Iterable[ModelParameter]) -> None:
    parameters = list(parameters)
    if not parameters:
        return
    params_element = ET.SubElement(parent, qname("ModelParameters"))
    for parameter in parameters:
        ET.SubElement(
            params_element,
            qname("Parameter"),
            attrs(name=parameter.name, value=parameter.value, dataType=parameter.data_type),
        )


def write_power_value(parent: ET.Element, tag: str, power: PowerValue) -> None:
    element = ET.SubElement(
        parent,
        qname(tag),
        attrs(value=power.value, units=power.units, source=power.source, sink=power.sink),
    )
    add_text(element, "Expression", power.expression or fmt_float(power.value))


def write_states(parent: ET.Element, states: Iterable[State]) -> None:
    states = list(states)
    if not states:
        return
    states_element = ET.SubElement(parent, qname("States"), attrs(units="mW", mutuallyExclusive="true"))
    for state in states:
        state_element = ET.SubElement(states_element, qname("State"), attrs(name=state.name, when=state.when, units=state.units))
        for static_power in state.static_power:
            write_power_value(state_element, "StaticPower", static_power)
        for dynamic_power in state.dynamic_power:
            write_power_value(state_element, "DynamicPower", dynamic_power)


def write_cell(parent: ET.Element, cell: Cell) -> None:
    cell_element = ET.SubElement(
        parent,
        qname("Cell"),
        attrs(name=cell.name, condition=cell.condition, datagen=cell.datagen),
    )
    write_pins(cell_element, cell.pins)
    write_modes(cell_element, cell.modes)
    write_events(cell_element, cell.events)
    write_cell_parameters(cell_element, cell.cell_parameters)
    write_model_parameters(cell_element, cell.model_parameters)
    write_states(cell_element, cell.states)


def write_library(library: Library, path: Path) -> Path:
    root = ET.Element(
        qname("Library"),
        attrs(name=library.name, version=library.version, condition=library.condition, datagen=library.datagen),
    )
    if library.annotation:
        annotation = ET.SubElement(root, qname("annotation"))
        annotation.text = library.annotation
    if library.technology is not None:
        write_technology(root, library.technology)
    write_units(root, library.units)
    write_conditions(root, library)
    write_library_parameters(root, library.parameters)
    write_expressions(root, library.expressions)
    for cell in library.cells:
        write_cell(root, cell)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return path
