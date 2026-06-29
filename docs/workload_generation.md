# Workload Intent Generation

This layer turns a high-level workload intent into an assembly program for the
toy mobile CPU. It is inspired by synthetic microbenchmark generation flows:
describe the behavior you want to stress, generate a bounded program, then feed
that program into simulation, waveform activity extraction, and IEEE 2416 power
estimation.

The checked-in source of truth is the JSON spec under `workload_specs/`.
Generated assembly is written under `workloads/generated/` and is intentionally
ignored by Git because it can be reproduced from the spec.

## Flow

```text
workload_specs/*.json
  -> tools/gen_workload.py
  -> workloads/generated/<name>.s
  -> tools/asm.py
  -> build/workloads/generated/<name>.memh
  -> Verilator simulation
  -> VCD/FST activity
  -> IEEE 2416 power estimation
  -> workload profile reports
```

## Spec Format

Example:

```json
{
  "name": "dataflow_energy_probe",
  "description": "Dataflow-heavy synthetic probe for comparing CPU activity, MMIO traffic, and dataflow MAC energy.",
  "intent": {
    "profile": "dataflow_heavy",
    "alu_chains": 1,
    "dependency_depth": 2,
    "memory_pairs": 1,
    "dataflow_macs": 4,
    "branch_probes": 1,
    "idle_windows": 2
  },
  "max_instructions": 64
}
```

Supported profiles:

| Profile | Purpose |
| --- | --- |
| `mixed_mobile` | Balanced ALU, memory, dataflow, branch, and idle behavior. |
| `alu_heavy` | Dependent ALU chains for core activity studies. |
| `memory_heavy` | Repeated data SRAM store/load traffic. |
| `dataflow_heavy` | MMIO operand writes and dataflow MAC operations. |
| `sleep_wake` | Short work bursts with multiple `WFI` idle hints. |

Intent knobs:

| Knob | Meaning |
| --- | --- |
| `alu_chains` | Number of dependent ALU chains to emit. |
| `dependency_depth` | Number of dependent ALU operations per chain. |
| `memory_pairs` | Number of data SRAM store/load pairs. |
| `dataflow_macs` | Number of dataflow unit MAC operations. |
| `branch_probes` | Number of bounded not-taken branch probes. |
| `idle_windows` | Number of `WFI` idle hints. |

The branch probes are intentionally not taken. This keeps generated programs
finite while still exercising branch decode and control activity.

## Commands

Generate the default workload:

```sh
make gen-workload
```

Generate a different spec:

```sh
make gen-workload GEN_WORKLOAD=sleep_wake_probe
```

The `GEN_WORKLOAD` value selects `workload_specs/<name>.json`, and the JSON
`name` field must match that same value. This keeps the generated assembly,
manifest, and later profile commands aligned.

Assemble the generated workload:

```sh
make assemble-generated GEN_WORKLOAD=dataflow_energy_probe
```

Run it through the UPF-aware Verilator flow:

```sh
make sim-generated GEN_WORKLOAD=dataflow_energy_probe SCHEME=dvfs_retention_domains
```

Generate a VCD for downstream activity or commercial-tool collateral:

```sh
make sim-generated-vcd GEN_WORKLOAD=dataflow_energy_probe
```

Run the OpenLowPower IEEE 2416 power flow and architecture profile:

```sh
make profile-generated GEN_WORKLOAD=dataflow_energy_probe TECH=generic_7nm SCHEME=dvfs_retention_domains
```

## Generated Manifest

Each generation run writes a manifest:

```text
build/workloadgen/<name>/workload_intent.json
```

The manifest records the resolved preset, final instruction count, instruction
mix, and category counts such as ALU, memory, data SRAM access, dataflow MMIO
access, branch, and idle.

This is useful because the workload intent becomes traceable:

```text
intent spec -> generated assembly -> measured activity -> power estimate
```

## Current Scope

This first layer is deterministic. It does not yet search for a workload that
matches a target measured profile. The next natural step is a feedback loop:
generate a candidate workload, simulate/profile it, compare measured metrics
against the target, then adjust the intent or generation pass.
