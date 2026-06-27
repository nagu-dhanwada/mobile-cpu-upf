# Legacy Simple 2416-Style Flow

This flow is the original compact XML power-model experiment used before the
repository had the more complete OpenLowPower IEEE 2416 XSD. It is still useful
for educational experiments because the schema and XML files are small and easy
to inspect, but it is no longer the main standards-oriented path.

Use `docs/openlowpower_2416_flow.md` and the plain `make 2416-*` targets for
the real-XSD OpenLowPower IEEE 2416 flow. Use the targets in this guide only
when you intentionally want the simplified legacy format.

## Flow

```text
legacy/simple_2416_schema/schema_profile.json
        |
        v
legacy/simple_2416_schema/generated_schema.xsd
        |
        v
power_models/mobile_cpu/legacy2416/rtl/*.xml
        |
        v
waves/<workload>.vcd
        |
        v
reports/legacy2416/<workload>_<tech>/
```

The JSON file is a tiny schema profile for this repository's simplified XML
format. It is not the authoritative IEEE 2416 schema.

## Commands

Generate the legacy XSD:

```sh
make legacy2416-schema
```

Generate simplified XML macro models for the CPU blocks:

```sh
make legacy2416-characterize TECH=generic_7nm
```

Validate those simplified XML models:

```sh
make legacy2416-validate
```

Run a workload, extract VCD activity, and estimate power with the legacy model:

```sh
make legacy2416-power WORKLOAD=memory_burst TECH=generic_7nm
```

Outputs are written under:

```text
reports/legacy2416/memory_burst_generic_7nm/
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
make legacy2416-compare-workloads TECH=generic_7nm SCHEME=dvfs_retention_domains
```

This runs the default workload set and writes:

```text
reports/legacy2416/compare_workloads_generic_7nm_dvfs_retention_domains/
```

Compare power schemes for the same workload:

```sh
make legacy2416-compare-schemes WORKLOAD=memory_burst TECH=generic_7nm
```

This writes:

```text
reports/legacy2416/compare_schemes_memory_burst_generic_7nm/
```

Both comparison directories contain:

- `2416_compare_summary.md`
- `2416_compare.csv`
- `2416_compare_energy.svg`
- `2416_compare_average_power.svg`

Explore DVFS operating performance points for one workload:

```sh
make legacy2416-dvfs-explore WORKLOAD=memory_burst TECH=generic_7nm SCHEME=dvfs_retention_domains
```

This writes:

```text
reports/legacy2416/dvfs/memory_burst_generic_7nm_dvfs_retention_domains/
```

The DVFS report keeps the same workload events but replays them across the OPPs
in `configs/dvfs/mobile_cpu_opps.json`. The legacy macro-model coefficients
stay the same; only the voltage and frequency context changes.

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

The legacy macro model is a hybrid RTL model:

```text
Energy =
  leakage(state, PVT) * time
  + clock_energy * active_clock_cycles
  + event_energy * event_count
  + optional_toggle_energy * RTL_toggles
```

This lets one compact model respond to:

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
- `dataflow_unit`

Each generated XML model binds the block to its RTL hierarchy, power domain,
clock reference, operating conditions, power states, activity parameters, power
components, scaling laws, and validity range.

## Where This Still Fits

The synthesis-calibrated and mapped standard-cell/memory-macro experiments
currently reuse this legacy XML estimator while the real-XSD implementation
continues to mature. The compatibility targets named `2416-synth-power`,
`2416-mapped-power`, and `2416-compare-abstractions` print a note and delegate
to the corresponding `legacy2416-*` target.

That keeps old experiments runnable without letting the simplified JSON/XSD
look like the main IEEE 2416 source of truth.
