# OpenLowPower IEEE 2416 Library Flow

This flow generates a schema-valid OpenLowPower IEEE 2416 `Library` XML for the
toy mobile CPU and uses that model with VCD activity to estimate power. It is a
schema-driven path built around the more complete IEEE 2416 XSD.

The plain `2416-*` Make targets are the primary path for this flow. The older
`p2416-*` target names are kept as aliases so existing notes and scripts still
work.

## Inputs

- CPU RTL block metadata from the existing educational model descriptions.
- Technology assumptions from `configs/tech/*.json`.
- Workload activity from the Verilator VCD flow.
- The complete OpenLowPower IEEE 2416 XSD, passed with
  `OPENLOWPOWER_2416_XSD=/path/to/2416.xsd` or placed at
  `$HOME/Downloads/2416.xsd`.

## Generated Model

The characterizer writes one XML library:

```sh
make 2416-characterize TECH=generic_7nm
```

Default output:

```text
power_models/mobile_cpu/ieee2416/mobile_cpu_library.xml
```

The XML root is `Library` in the `OpenLowPower` namespace. Each CPU block,
including the memory-mapped `dataflow_unit`, is a `Cell` with:

- `Pins` for power, ground, clock, activity, power mode, and DVFS state.
- `Modes` for `RUN`, `IDLE`, `LIGHT_SLEEP`, `DEEP_SLEEP`, and `WAKE`.
- `Events` for clock cycles, instruction/data activity, and RTL toggles.
- `ModelParameters` carrying module path, power domain, clock, and scaling data.
- `States` carrying static power values per power mode.

## Validation

Run schema and semantic validation:

```sh
make 2416-validate OPENLOWPOWER_2416_XSD=$HOME/Downloads/2416.xsd
```

The validator first checks the generated XML against the provided XSD, then runs
a small semantic pass for things the XSD does not enforce, such as missing cell
metadata or empty state power definitions.

## Power Estimation

Run a workload, generate the schema-valid model, validate it, and estimate power:

```sh
make 2416-power WORKLOAD=memory_burst TECH=generic_7nm SCHEME=dvfs_retention_domains
```

Default reports:

```text
reports/2416/memory_burst_generic_7nm_dvfs_retention_domains/
```

Important outputs:

- `2416_power_summary.md`
- `2416_power_estimate.json`
- `2416_power_waveform.csv`
- `2416_power_waveform.svg`
- `2416_power_by_block.svg`
- `2416_power_by_domain.svg`

## Workload Profiling

The IEEE 2416 power result can feed an architecture-efficiency profile:

```sh
make profile-workload WORKLOAD=dataflow_mac TECH=generic_7nm SCHEME=dvfs_retention_domains
```

This produces:

```text
reports/2416/dataflow_mac_generic_7nm_dvfs_retention_domains/workload_profile/
```

The profile summarizes instruction mix, memory intensity, dataflow MAC count,
energy per retired instruction, energy per dataflow MAC, low-power residency,
and recovery energy after the useful run phase.

For a paired CPU-only versus dataflow-assisted experiment:

```sh
make compare-dataflow TECH=generic_7nm SCHEME=dvfs_retention_domains
```

## Additional Abstraction Levels

The same real-XSD path is used for the other model abstraction levels:

```sh
make 2416-dvfs-explore WORKLOAD=memory_burst TECH=generic_7nm
make 2416-synth-power WORKLOAD=memory_burst TECH=generic_7nm
make 2416-mapped-power WORKLOAD=memory_burst TECH=generic_7nm
make 2416-compare-abstractions WORKLOAD=memory_burst TECH=generic_7nm
```

These targets generate and validate OpenLowPower IEEE 2416 libraries for RTL
macros, synthesis-calibrated CPU macros, Liberty standard cells, and memory
macros before producing reports.
