# IEEE 2416 RTL Power Flow

This repository includes a first reference-style IEEE 2416 RTL power modeling
flow for the mobile CPU example. The goal is to make the standard executable:
model files are XML, the schema is generated from a canonical schema
description, the models are validated, and Verilator VCD activity drives a
block-level power estimate.

## Flow

```text
spec_model/ieee2416_2025_schema.json
        |
        v
schemas/ieee2416-2025.xsd
        |
        v
power_models/mobile_cpu/rtl/*.xml
        |
        v
waves/<workload>.vcd
        |
        v
reports/2416/<workload>_<tech>/
```

## Commands

Generate the XSD:

```sh
make 2416-schema
```

Generate XML macro models for the CPU blocks:

```sh
make 2416-characterize TECH=generic_7nm
```

Validate the generated XML models:

```sh
make 2416-validate
```

Run a workload, extract VCD activity, and estimate power:

```sh
make 2416-power WORKLOAD=memory_burst TECH=generic_7nm
```

Outputs are written under:

```text
reports/2416/memory_burst_generic_7nm/
```

The main files are:

- `2416_activity.json`: events, mode residency, clock cycles, and RTL toggles.
- `2416_power_estimate.json`: machine-readable energy and power results.
- `2416_power_summary.md`: human-readable summary.
- `2416_power_by_block.csv`: per-block energy and average power.
- `2416_power_by_domain.csv`: per-domain energy and average power.
- `2416_power_waveform.csv`: estimated power waveform samples by domain.
- `2416_power_waveform.svg`: stacked domain power waveform.
- `2416_power_by_block.svg`: block energy bar chart.
- `2416_power_by_domain.svg`: domain energy bar chart.
- `2416_state_residency.csv`: state residency summary.

## Visual Comparisons

Compare workloads under the same technology and power scheme:

```sh
make 2416-compare-workloads TECH=generic_7nm SCHEME=dvfs_retention_domains
```

This runs `alu_idle`, `compute_burst`, and `memory_burst`, then writes:

```text
reports/2416/compare_workloads_generic_7nm_dvfs_retention_domains/
```

Compare power schemes for the same workload:

```sh
make 2416-compare-schemes WORKLOAD=memory_burst TECH=generic_7nm
```

This writes:

```text
reports/2416/compare_schemes_memory_burst_generic_7nm/
```

Both comparison directories contain:

- `2416_compare_summary.md`
- `2416_compare.csv`
- `2416_compare_energy.svg`
- `2416_compare_average_power.svg`

Explore DVFS operating performance points for one workload:

```sh
make 2416-dvfs-explore WORKLOAD=memory_burst TECH=generic_7nm SCHEME=dvfs_retention_domains
```

This writes:

```text
reports/2416/dvfs/memory_burst_generic_7nm_dvfs_retention_domains/
```

The DVFS report keeps the same workload events but replays them across the OPPs
in `configs/dvfs/mobile_cpu_opps.json`. The 2416 macro-model coefficients stay
the same; only the voltage and frequency context changes.

Key files:

- `dvfs_summary.md`
- `dvfs_points.csv`
- `dvfs_contributors.csv`
- `dvfs_energy.svg`
- `dvfs_average_power.svg`
- `dvfs_runtime.svg`
- `dvfs_edp.svg`
- `dvfs_contributors.svg`

## Model Abstraction

The first macro model is a hybrid RTL model:

```text
Energy =
  leakage(state, PVT) * time
  + clock_energy * active_clock_cycles
  + event_energy * event_count
  + optional_toggle_energy * RTL_toggles
```

This lets one model respond to:

- process/voltage/temperature assumptions,
- power states such as RUN, IDLE, LIGHT_SLEEP, DEEP_SLEEP, and WAKE,
- DVFS level changes,
- workload events such as ALU operations, register accesses, and SRAM accesses,
- optional RTL signal toggles from the VCD.

## CPU Blocks Modeled

- `fetch_unit`
- `instr_rom`
- `decode_unit`
- `regfile`
- `execute_unit`
- `data_sram`
- `power_controller`

Each generated XML model binds the block to its RTL hierarchy, power domain,
clock reference, operating conditions, power states, activity parameters, power
components, scaling laws, and validity range.

## Power Contributors

The XML models separate numeric coefficients from explanatory contributors:

- `powerComponents` contains executable values such as leakage in mW or event
  energy in pJ.
- `powerContributors` describes the reason for each component: static leakage,
  clocking, workload event, or RTL toggle activity.

For example, an `execute_unit` ADDI operation has an event component named
`alu_addi` and a matching contributor that says the driver is `opcode.ADDI`,
the voltage dependency uses the dynamic exponent, the frequency dependency is
event count, and the workload dependency is the instruction mix. This is the
bridge from "a number in an XML file" to "why this RTL block burns power."

## Time Normalization

The Verilator harness emits VCD dump ticks, not real nanoseconds. The estimator
normalizes VCD duration using the selected technology clock frequency. For
example, `generic_7nm` uses 900 MHz, so 35 top-level cycles become about
38.889 ns.

## Scheme Profiles

The RTL implements the richest power behavior, so scheme comparisons are applied
as estimator profiles over the same workload activity:

- `baseline_always_on`: maps all time to RUN and keeps core/memory clocks active.
- `clock_gated_idle`: models idle/sleep intervals as clock-gated idle, without
  deep power gating.
- `core_power_gated_sleep`: keeps nominal-voltage behavior but preserves deep
  sleep power gating.
- `dvfs_retention_domains`: uses the full DVFS, retention, isolation, and
  power-gating behavior.

## DVFS Exploration

The DVFS explorer answers a different question from scheme comparison:

```text
If the same workload runs at LOW, NOMINAL, or TURBO, what happens to
runtime, total energy, average power, and energy-delay product?
```

The OPP file defines CPU voltage, CPU frequency, memory voltage, and memory
frequency for each point. The tool forces the VCD activity into each OPP,
normalizes runtime by the OPP frequency, applies voltage scaling to the 2416
components, and reports leakage/clock/event/toggle contributors separately.

Use the output this way:

- `dvfs_energy.svg`: which OPP saves energy.
- `dvfs_average_power.svg`: which OPP has the lowest average draw.
- `dvfs_runtime.svg`: which OPP completes fastest.
- `dvfs_edp.svg`: the performance-vs-energy tradeoff.
- `dvfs_contributors.svg`: whether the OPP is dominated by leakage, clocks,
  events, or toggles.

## Current Scope

This is the RTL macro-model layer. The next layer should add synthesis
calibration from Yosys/OpenROAD outputs, then compare:

```text
hand-characterized RTL model
synthesis-calibrated macro model
physical-aware macro model
```
