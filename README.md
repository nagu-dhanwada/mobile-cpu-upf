# Mobile CPU Power Optimization Playground

This repository is a compact starting point for exploring low-power design ideas on
a toy mobile CPU. It includes:

- Simple SystemVerilog RTL split into blocks that map cleanly to power domains.
- JSON power-scheme descriptions.
- Automatic UPF generation for each scheme.
- A lightweight power-estimation script for comparing schemes early in the flow.

The UPF is intentionally tool-neutral IEEE 1801-style Tcl. Commercial flows often
need small command or naming adjustments, but the generated files capture the
partitioning, supplies, switches, isolation, retention, level shifters, and power
states for each scheme.

## Layout

```text
rtl/             Toy mobile CPU RTL
power_schemes/   JSON descriptions of power optimization schemes
tools/           UPF generation and exploration scripts
upf/             Generated UPF output
docs/            Architecture notes
tests/           Basic generator tests
```

## Quick Start

Generate UPF for every scheme:

```sh
make upf
```

Run the early power exploration:

```sh
make explore
```

Run tests:

```sh
make test
```

Generated artifacts:

- `upf/*.upf`
- `upf/index.md`
- `reports/power_summary.csv`
- `reports/power_summary.md`

## Included Schemes

1. `baseline_always_on`
   - One always-on power domain.
   - Single nominal voltage.

2. `clock_gated_idle`
   - One always-on power domain.
   - Uses RTL clock enables from the power controller to reduce idle dynamic
     power.

3. `core_power_gated_sleep`
   - Always-on controller domain plus switched CPU and memory domains.
   - Adds isolation and register retention for sleep.

4. `dvfs_retention_domains`
   - Separate always-on, CPU, and memory domains.
   - Adds multiple CPU voltage states, power switches, retention, isolation,
     and level shifters.

## Adding A New Scheme

Create another JSON file in `power_schemes/` and run:

```sh
make upf explore
```

The generator reads the domain list, supply names, power states, switches,
isolation rules, retention rules, and level-shifter requests from the JSON file.
Keep the RTL instance names aligned with `rtl/mobile_cpu_top.sv` when assigning
elements to domains.

