"""Small internal representation for OpenLowPower IEEE 2416 XML models.

The classes here intentionally mirror the high-level XSD structure: a Library
contains technology, units, parameters, conditions, expressions, and Cells.
Each Cell contains Pins, Modes, Events, model parameters, and States.
"""

from __future__ import annotations

from dataclasses import dataclass, field


OPENLOWPOWER_NS = "OpenLowPower"


def fmt_float(value: float, digits: int = 9) -> str:
    """Format floats consistently while keeping generated XML readable."""
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


@dataclass(frozen=True)
class UnitDef:
    name: str
    value: str
    min: str | None = None
    max: str | None = None


@dataclass(frozen=True)
class ProcessInfo:
    name: str
    version: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Technology:
    name: str
    version: str | None = None
    processes: tuple[ProcessInfo, ...] = ()


@dataclass(frozen=True)
class LibraryParameter:
    name: str
    value: str
    type: str = "float"
    data_type: str | None = "float"
    units: str | None = None
    alias: str | None = None
    min: str | None = None
    max: str | None = None


@dataclass(frozen=True)
class Condition:
    name: str
    value: str


@dataclass(frozen=True)
class ConditionSet:
    name: str
    conditions: tuple[Condition, ...]


@dataclass(frozen=True)
class GlobalExpression:
    name: str
    text: str
    source: str | None = None
    sink: str | None = None


@dataclass(frozen=True)
class Pin:
    name: str
    direction: str
    width: str | None = None
    data_type: str | None = None
    capacitance: float | None = None
    pin_type: str | None = None
    pin_reference: str | None = None
    related_power: str | None = None
    related_ground: str | None = None
    condition: str | None = None


@dataclass(frozen=True)
class Mode:
    name: str
    when: str
    value: float | None = None
    units: str | None = None
    expression: str | None = None
    source: str | None = None
    sink: str | None = None


@dataclass(frozen=True)
class EventEnergy:
    value: float
    contributor: str = "custom"
    type: str = "float"
    quantity: int = 1
    capacitance: float = 0.0


@dataclass(frozen=True)
class Event:
    name: str
    mode: str
    style: str = "pinTransition"
    when: str | None = None
    input_pin: str | None = "activity"
    input_transition: str | None = "rising"
    output_pin: str | None = None
    output_transition: str | None = None
    next_mode: str | None = None
    trigger: str | None = None
    trigger_transition: str | None = None
    energy: EventEnergy | None = None
    expression: str | None = None


@dataclass(frozen=True)
class PowerValue:
    value: float
    units: str
    expression: str | None = None
    source: str | None = "VDD"
    sink: str | None = "VSS"


@dataclass(frozen=True)
class State:
    name: str
    when: str
    static_power: tuple[PowerValue, ...] = ()
    dynamic_power: tuple[PowerValue, ...] = ()
    units: str | None = "mW"


@dataclass(frozen=True)
class ModelParameter:
    name: str
    value: str
    data_type: str = "string"


@dataclass(frozen=True)
class Cell:
    name: str
    pins: tuple[Pin, ...]
    modes: tuple[Mode, ...] = ()
    events: tuple[Event, ...] = ()
    model_parameters: tuple[ModelParameter, ...] = ()
    cell_parameters: tuple[LibraryParameter, ...] = ()
    states: tuple[State, ...] = ()
    condition: str | None = None
    datagen: str = "estimated"


@dataclass(frozen=True)
class Library:
    name: str
    version: str
    units: tuple[UnitDef, ...]
    technology: Technology | None = None
    parameters: tuple[LibraryParameter, ...] = ()
    conditions: tuple[ConditionSet, ...] = ()
    expressions: tuple[GlobalExpression, ...] = ()
    cells: tuple[Cell, ...] = ()
    condition: str | None = None
    datagen: str = "estimated"
    annotation: str | None = None
