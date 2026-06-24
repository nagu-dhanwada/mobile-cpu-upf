"""Workload intent model for generated toy CPU programs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


PRESETS: dict[str, dict[str, int]] = {
    "mixed_mobile": {
        "alu_chains": 2,
        "dependency_depth": 3,
        "memory_pairs": 2,
        "dataflow_macs": 1,
        "branch_probes": 1,
        "idle_windows": 1,
    },
    "alu_heavy": {
        "alu_chains": 5,
        "dependency_depth": 5,
        "memory_pairs": 0,
        "dataflow_macs": 0,
        "branch_probes": 1,
        "idle_windows": 1,
    },
    "memory_heavy": {
        "alu_chains": 1,
        "dependency_depth": 2,
        "memory_pairs": 6,
        "dataflow_macs": 0,
        "branch_probes": 1,
        "idle_windows": 1,
    },
    "dataflow_heavy": {
        "alu_chains": 1,
        "dependency_depth": 2,
        "memory_pairs": 1,
        "dataflow_macs": 4,
        "branch_probes": 1,
        "idle_windows": 1,
    },
    "sleep_wake": {
        "alu_chains": 1,
        "dependency_depth": 2,
        "memory_pairs": 1,
        "dataflow_macs": 0,
        "branch_probes": 0,
        "idle_windows": 4,
    },
}


@dataclass(frozen=True)
class WorkloadIntent:
    """Resolved intent values used by the deterministic generator."""

    name: str
    description: str
    profile: str
    alu_chains: int
    dependency_depth: int
    memory_pairs: int
    dataflow_macs: int
    branch_probes: int
    idle_windows: int
    max_instructions: int = 64
    result_store: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_name(value: str) -> str:
    name = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", name):
        raise ValueError(
            f"Workload name {value!r} must use letters, digits, dots, dashes, or underscores"
        )
    if "/" in name or ".." in name:
        raise ValueError(f"Workload name {value!r} must not contain path separators")
    return name


def _nonnegative_int(values: dict[str, Any], key: str) -> int:
    raw = values.get(key, 0)
    if isinstance(raw, bool):
        raise ValueError(f"{key} must be an integer, got boolean")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer, got {raw!r}") from exc
    if value < 0:
        raise ValueError(f"{key} must be non-negative")
    return value


def intent_from_spec(spec: dict[str, Any]) -> WorkloadIntent:
    """Resolve a user workload specification into a concrete intent."""

    if not isinstance(spec, dict):
        raise ValueError("Workload spec must be a JSON object")

    name = _clean_name(str(spec.get("name", "") or "generated_workload"))
    description = str(spec.get("description", "") or "")
    raw_intent = spec.get("intent", {})
    if not isinstance(raw_intent, dict):
        raise ValueError("intent must be an object when present")

    profile = str(raw_intent.get("profile", spec.get("profile", "mixed_mobile")))
    if profile not in PRESETS:
        known = ", ".join(sorted(PRESETS))
        raise ValueError(f"Unknown workload profile {profile!r}; known profiles: {known}")

    resolved: dict[str, Any] = dict(PRESETS[profile])
    resolved.update(raw_intent)
    resolved.pop("profile", None)

    max_instructions = _nonnegative_int(
        {"max_instructions": spec.get("max_instructions", resolved.get("max_instructions", 64))},
        "max_instructions",
    )
    if max_instructions == 0:
        raise ValueError("max_instructions must be greater than zero")

    return WorkloadIntent(
        name=name,
        description=description,
        profile=profile,
        alu_chains=_nonnegative_int(resolved, "alu_chains"),
        dependency_depth=_nonnegative_int(resolved, "dependency_depth"),
        memory_pairs=_nonnegative_int(resolved, "memory_pairs"),
        dataflow_macs=_nonnegative_int(resolved, "dataflow_macs"),
        branch_probes=_nonnegative_int(resolved, "branch_probes"),
        idle_windows=_nonnegative_int(resolved, "idle_windows"),
        max_instructions=max_instructions,
        result_store=bool(spec.get("result_store", resolved.get("result_store", True))),
    )

