#!/usr/bin/env python3
"""Shared power-intent helpers for UPF generation and simulation metadata."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Optional


def slug(name: str) -> str:
    allowed: list[str] = []
    for char in name.lower():
        if char.isalnum():
            allowed.append(char)
        elif char in {"-", "_", " "}:
            allowed.append("_")
    return "".join(allowed).strip("_")


@dataclass(frozen=True)
class DomainState:
    name: str
    kind: str
    voltage: Optional[float]

    @property
    def is_off(self) -> bool:
        return self.kind.upper() == "OFF"


@dataclass(frozen=True)
class Domain:
    name: str
    elements: tuple[str, ...]
    supply: str
    ground: str
    always_on: bool
    states: tuple[DomainState, ...]
    switch: Optional[dict[str, Any]]
    isolation: Optional[dict[str, Any]]
    retention: Optional[dict[str, Any]]

    def state(self, name: str) -> DomainState:
        for state in self.states:
            if state.name == name:
                return state
        raise KeyError(f"Domain {self.name} has no state {name}")


@dataclass(frozen=True)
class PowerState:
    name: str
    domain_states: dict[str, str]


@dataclass(frozen=True)
class PowerIntent:
    source: Path
    raw: dict[str, Any]
    name: str
    top: str
    domains: tuple[Domain, ...]
    level_shifters: tuple[dict[str, Any], ...]
    power_states: tuple[PowerState, ...]

    def domain(self, name: str) -> Domain:
        for domain in self.domains:
            if domain.name == name:
                return domain
        raise KeyError(f"No domain named {name}")

    def has_domain(self, name: str) -> bool:
        return any(domain.name == name for domain in self.domains)

    def power_state(self, name: str) -> PowerState:
        for power_state in self.power_states:
            if power_state.name == name:
                return power_state
        raise KeyError(f"No power state named {name}")

    def has_power_state(self, name: str) -> bool:
        return any(power_state.name == name for power_state in self.power_states)

    def state_voltage(self, domain_name: str, power_state_name: str) -> Optional[float]:
        power_state = self.power_state(power_state_name)
        domain = self.domain(domain_name)
        state = domain.state(power_state.domain_states[domain_name])
        if state.is_off:
            return None
        return state.voltage

    def state_is_on(self, domain_name: str, power_state_name: str) -> bool:
        power_state = self.power_state(power_state_name)
        domain = self.domain(domain_name)
        return not domain.state(power_state.domain_states[domain_name]).is_off

    def switched_domains(self) -> tuple[Domain, ...]:
        return tuple(domain for domain in self.domains if domain.switch)

    def retained_domains(self) -> tuple[Domain, ...]:
        return tuple(domain for domain in self.domains if domain.retention)

    def isolated_domains(self) -> tuple[Domain, ...]:
        return tuple(domain for domain in self.domains if domain.isolation)

    def voltage_crossings(self) -> list[dict[str, Any]]:
        crossings: list[dict[str, Any]] = []
        for power_state in self.power_states:
            powered: list[tuple[str, float]] = []
            for domain in self.domains:
                state_name = power_state.domain_states[domain.name]
                state = domain.state(state_name)
                if state.voltage is not None and not state.is_off:
                    powered.append((domain.name, state.voltage))

            for left_index, (left_name, left_voltage) in enumerate(powered):
                for right_name, right_voltage in powered[left_index + 1:]:
                    if abs(left_voltage - right_voltage) > 0.001:
                        crossings.append(
                            {
                                "power_state": power_state.name,
                                "from_domain": left_name,
                                "to_domain": right_name,
                                "from_voltage": left_voltage,
                                "to_voltage": right_voltage,
                            }
                        )
        return crossings

    def to_metadata(self) -> dict[str, Any]:
        return {
            "scheme": self.name,
            "top": self.top,
            "source": self.source.as_posix(),
            "domains": [
                {
                    "name": domain.name,
                    "elements": list(domain.elements),
                    "supply": domain.supply,
                    "ground": domain.ground,
                    "always_on": domain.always_on,
                    "states": [
                        {
                            "name": state.name,
                            "kind": state.kind,
                            "voltage": state.voltage,
                            "is_off": state.is_off,
                        }
                        for state in domain.states
                    ],
                    "has_switch": domain.switch is not None,
                    "has_isolation": domain.isolation is not None,
                    "has_retention": domain.retention is not None,
                    "switch": domain.switch,
                    "isolation": domain.isolation,
                    "retention": domain.retention,
                }
                for domain in self.domains
            ],
            "level_shifters": list(self.level_shifters),
            "power_states": [
                {"name": state.name, "domain_states": state.domain_states}
                for state in self.power_states
            ],
            "features": {
                "domain_count": len(self.domains),
                "power_state_count": len(self.power_states),
                "switched_domain_count": len(self.switched_domains()),
                "isolated_domain_count": len(self.isolated_domains()),
                "retained_domain_count": len(self.retained_domains()),
                "level_shifter_count": len(self.level_shifters),
                "voltage_crossing_count": len(self.voltage_crossings()),
            },
            "voltage_crossings": self.voltage_crossings(),
        }


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_scheme_path(scheme: str, schemes_dir: Path = Path("power_schemes")) -> Path:
    candidate = Path(scheme)
    if candidate.exists():
        return candidate

    if candidate.suffix != ".json":
        direct = schemes_dir / f"{scheme}.json"
        if direct.exists():
            return direct

    normalized = slug(scheme)
    matches: list[Path] = []
    for path in sorted(schemes_dir.glob("*.json")):
        raw = _read_json(path)
        names = {slug(raw.get("name", "")), slug(path.stem)}
        if normalized in names or path.stem.endswith(normalized):
            matches.append(path)

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"No power scheme found for {scheme!r} in {schemes_dir}")
    raise ValueError(f"Power scheme {scheme!r} is ambiguous: {matches}")


def load_power_intent(path: Path) -> PowerIntent:
    raw = _read_json(path)
    _validate_raw(raw, path)

    domains: list[Domain] = []
    for domain in raw["domains"]:
        states = tuple(
            DomainState(
                name=state["name"],
                kind=state.get("kind", "FULL_ON"),
                voltage=None if state.get("kind", "FULL_ON").upper() == "OFF" else float(state["voltage"]),
            )
            for state in domain.get("states", [])
        )
        domains.append(
            Domain(
                name=domain["name"],
                elements=tuple(domain["elements"]),
                supply=domain["supply"],
                ground=domain.get("ground", "VSS"),
                always_on=bool(domain.get("always_on", False)),
                states=states,
                switch=domain.get("switch"),
                isolation=domain.get("isolation"),
                retention=domain.get("retention"),
            )
        )

    power_states = tuple(
        PowerState(name=state["name"], domain_states=dict(state["domain_states"]))
        for state in raw["power_states"]
    )

    return PowerIntent(
        source=path,
        raw=raw,
        name=raw["name"],
        top=raw["top"],
        domains=tuple(domains),
        level_shifters=tuple(raw.get("level_shifters", [])),
        power_states=power_states,
    )


def load_scheme(scheme: str, schemes_dir: Path = Path("power_schemes")) -> PowerIntent:
    return load_power_intent(resolve_scheme_path(scheme, schemes_dir))


def _validate_raw(raw: dict[str, Any], source: Path) -> None:
    for key in ["name", "top", "domains", "power_states"]:
        if key not in raw:
            raise ValueError(f"{source}: missing required key {key}")
    if not raw["domains"]:
        raise ValueError(f"{source}: at least one domain is required")

    domain_names: set[str] = set()
    for domain in raw["domains"]:
        name = domain["name"]
        if name in domain_names:
            raise ValueError(f"{source}: duplicate domain {name}")
        domain_names.add(name)

        if not domain.get("elements"):
            raise ValueError(f"{source}: domain {name} needs elements")
        if not domain.get("states"):
            raise ValueError(f"{source}: domain {name} needs states")

        state_names: set[str] = set()
        for state in domain["states"]:
            state_name = state["name"]
            if state_name in state_names:
                raise ValueError(f"{source}: duplicate state {name}.{state_name}")
            state_names.add(state_name)
            if state.get("kind", "FULL_ON").upper() != "OFF" and "voltage" not in state:
                raise ValueError(f"{source}: state {name}.{state_name} needs a voltage")

        if any(state.get("kind", "FULL_ON").upper() == "OFF" for state in domain["states"]):
            if not domain.get("always_on", False) and "switch" not in domain:
                raise ValueError(f"{source}: switched domain {name} with OFF state needs a switch")

        if "switch" in domain:
            for field in ["name", "input_supply", "control"]:
                if field not in domain["switch"]:
                    raise ValueError(f"{source}: switch on {name} misses {field}")
        if "isolation" in domain:
            for field in ["name", "signal"]:
                if field not in domain["isolation"]:
                    raise ValueError(f"{source}: isolation on {name} misses {field}")
        if "retention" in domain:
            for field in ["name", "elements", "save_signal", "restore_signal"]:
                if field not in domain["retention"]:
                    raise ValueError(f"{source}: retention on {name} misses {field}")

    power_state_names: set[str] = set()
    for power_state in raw["power_states"]:
        name = power_state["name"]
        if name in power_state_names:
            raise ValueError(f"{source}: duplicate power state {name}")
        power_state_names.add(name)

        domain_states = power_state.get("domain_states", {})
        missing = domain_names - set(domain_states)
        extra = set(domain_states) - domain_names
        if missing:
            raise ValueError(f"{source}: power state {name} misses domains {sorted(missing)}")
        if extra:
            raise ValueError(f"{source}: power state {name} references unknown domains {sorted(extra)}")

        for domain in raw["domains"]:
            state_names = {state["name"] for state in domain["states"]}
            state_name = domain_states[domain["name"]]
            if state_name not in state_names:
                raise ValueError(
                    f"{source}: power state {name} uses invalid {domain['name']} state {state_name}"
                )

