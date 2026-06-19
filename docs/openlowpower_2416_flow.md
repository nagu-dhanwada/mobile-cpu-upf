# OpenLowPower IEEE 2416 Library Flow

This flow generates a schema-valid OpenLowPower IEEE 2416 `Library` XML for the
toy mobile CPU and uses that model with VCD activity to estimate power. It is a
newer, schema-driven path that sits beside the existing lightweight `2416-*`
targets.

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
make p2416-characterize TECH=generic_7nm
```

Default output:

```text
power_models/mobile_cpu/p2416/mobile_cpu_library.xml
```

The XML root is `Library` in the `OpenLowPower` namespace. Each CPU block is a
`Cell` with:

- `Pins` for power, ground, clock, activity, power mode, and DVFS state.
- `Modes` for `RUN`, `IDLE`, `LIGHT_SLEEP`, `DEEP_SLEEP`, and `WAKE`.
- `Events` for clock cycles, instruction/data activity, and RTL toggles.
- `ModelParameters` carrying module path, power domain, clock, and scaling data.
- `States` carrying static power values per power mode.

## Validation

Run schema and semantic validation:

```sh
make p2416-validate OPENLOWPOWER_2416_XSD=$HOME/Downloads/2416.xsd
```

The validator first checks the generated XML against the provided XSD, then runs
a small semantic pass for things the XSD does not enforce, such as missing cell
metadata or empty state power definitions.

## Power Estimation

Run a workload, generate the schema-valid model, validate it, and estimate power:

```sh
make p2416-power WORKLOAD=memory_burst TECH=generic_7nm SCHEME=dvfs_retention_domains
```

Default reports:

```text
reports/p2416/memory_burst_generic_7nm_dvfs_retention_domains/
```

Important outputs:

- `2416_power_summary.md`
- `2416_power_estimate.json`
- `2416_power_waveform.csv`
- `2416_power_waveform.svg`
- `2416_power_by_block.svg`
- `2416_power_by_domain.svg`

## Relationship To The Existing Flow

The older `2416-*` targets still generate and consume the repository's compact
reference XML format. The new `p2416-*` targets generate and consume the
OpenLowPower `Library` structure from the uploaded XSD. Keeping both flows makes
it easy to compare a small educational format with the fuller standard-oriented
model representation while the tooling evolves.

