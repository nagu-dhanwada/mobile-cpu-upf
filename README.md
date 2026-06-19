# Mobile CPU Power Optimization Playground

This repository is a compact starting point for exploring low-power design ideas on
a toy mobile CPU. It includes:

- Simple SystemVerilog RTL split into blocks that map cleanly to power domains.
- JSON power-scheme descriptions.
- Automatic UPF generation for each scheme.
- IEEE 2416-style RTL, synthesis-calibrated, and mapped standard-cell power
  model flows.
- OpenLowPower IEEE 2416 `Library` generation and validation against a complete
  XSD supplied by the user.

The UPF is intentionally tool-neutral IEEE 1801-style Tcl. Commercial flows often
need small command or naming adjustments, but the generated files capture the
partitioning, supplies, switches, isolation, retention, level shifters, and power
states for each scheme.

## Layout

```text
rtl/             Toy mobile CPU RTL
power_schemes/   JSON descriptions of power optimization schemes
configs/         Technology, DVFS, and memory-macro assumptions
macros/          Synthesis blackboxes for implementation-style macros
tools/           UPF generation and exploration scripts
upf/             Generated UPF output
docs/            Architecture notes
tests/           Basic generator tests
workloads/       Small assembly workloads for the CPU model
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

Run the Verilator-based UPF-aware demo simulation:

```sh
make sim-power
```

Use a specific scheme by name:

```sh
make sim-power SCHEME=dvfs_retention_domains
```

Open the generated waveform:

```sh
make waves
```

The waveform target uses `sim/power_view.sucl` to preload the power-related
signals in Surfer when Surfer is installed.

Run a named CPU workload through the same power-aware scenario:

```sh
make sim-workload WORKLOAD=memory_burst
```

This assembles `workloads/memory_burst.s`, loads it into `instr_rom.sv` at
runtime, runs `sim/scenarios/power_modes.tcl`, and writes a workload-specific
summary and waveform. Use `WORKLOAD=alu_idle`, `WORKLOAD=compute_burst`, or
add another `.s` file under `workloads/`.

Open that workload waveform:

```sh
make waves-workload WORKLOAD=memory_burst
```

Generate a VCD and Cadence Joules RTL power-analysis starter script:

```sh
make joules-input
```

This creates `waves/mobile_cpu_power.vcd` and
`build/joules/run_joules_power.tcl`.

Generate Joules inputs for a specific workload:

```sh
make joules-workload WORKLOAD=memory_burst
```

This creates `waves/memory_burst.vcd` and
`build/joules/memory_burst_run_joules_power.tcl`.

Run the IEEE 2416 RTL macro-model power flow:

```sh
make 2416-power WORKLOAD=memory_burst TECH=generic_7nm
```

This generates a reference XSD, characterizes XML power models for the CPU
blocks, validates those models, runs the workload VCD simulation, and writes
power reports under `reports/2416/memory_burst_generic_7nm/`.

Run the schema-driven OpenLowPower IEEE 2416 library flow:

```sh
make p2416-power WORKLOAD=memory_burst TECH=generic_7nm SCHEME=dvfs_retention_domains
```

By default this validates against `$HOME/Downloads/2416.xsd`. Override the XSD
path when needed:

```sh
make p2416-validate OPENLOWPOWER_2416_XSD=/path/to/2416.xsd
```

This newer path writes a single `Library` XML containing `Cell` models for the
CPU blocks, validates it against the OpenLowPower XSD, and then estimates power
from the workload VCD. See `docs/openlowpower_2416_flow.md`.

Generate visual workload comparison charts:

```sh
make 2416-compare-workloads TECH=generic_7nm SCHEME=dvfs_retention_domains
```

Generate visual power-scheme comparison charts:

```sh
make 2416-compare-schemes WORKLOAD=memory_burst TECH=generic_7nm
```

Explore DVFS operating points for one workload:

```sh
make 2416-dvfs-explore WORKLOAD=memory_burst TECH=generic_7nm SCHEME=dvfs_retention_domains
```

Synthesize the CPU with Yosys and run functional gate-level simulation:

```sh
make synth WORKLOAD=memory_burst
make gls WORKLOAD=memory_burst
```

Generate synthesis-calibrated IEEE 2416 models and power estimates:

```sh
make 2416-synth-power WORKLOAD=memory_burst TECH=generic_7nm
```

Run the mapped standard-cell plus memory-macro flow:

```sh
make 2416-mapped-power WORKLOAD=memory_burst TECH=generic_7nm
```

Compare the three abstraction levels:

```sh
make 2416-compare-abstractions WORKLOAD=memory_burst TECH=generic_7nm
```

Generated artifacts:

- `upf/*.upf`
- `upf/index.md`
- `reports/power_summary.csv`
- `reports/power_summary.md`
- `reports/power_sim_summary.md`
- `reports/power_sim_events.json`
- `waves/mobile_cpu_power.fst`
- `waves/mobile_cpu_power.vcd`
- `build/joules/run_joules_power.tcl`
- `build/workloads/*.memh`
- `build/workloads/*.lst`
- `waves/<workload>.fst`
- `waves/<workload>.vcd`
- `build/joules/<workload>_run_joules_power.tcl`
- `schemas/ieee2416-2025.xsd`
- `power_models/mobile_cpu/rtl/*.xml`
- `power_models/mobile_cpu/p2416/mobile_cpu_library.xml`
- `reports/2416/<workload>_<tech>/2416_power_summary.md`
- `reports/2416/<workload>_<tech>/2416_power_waveform.svg`
- `reports/p2416/<workload>_<tech>_<scheme>/2416_power_summary.md`
- `reports/p2416/<workload>_<tech>_<scheme>/2416_power_waveform.svg`
- `reports/2416/compare_workloads_<tech>_<scheme>/2416_compare_energy.svg`
- `reports/2416/compare_schemes_<workload>_<tech>/2416_compare_energy.svg`
- `reports/2416/dvfs/<workload>_<tech>_<scheme>/dvfs_summary.md`
- `reports/2416/dvfs/<workload>_<tech>_<scheme>/dvfs_contributors.svg`
- `build/synth/<workload>/mobile_cpu_gate.v`
- `build/synth/<workload>/mobile_cpu_synth_metrics.md`
- `waves/<workload>_gate.vcd`
- `reports/gls/<workload>_gate_summary.md`
- `power_models/mobile_cpu/synth/*.xml`
- `reports/2416_synth/<workload>_<tech>/2416_power_summary.md`
- `power_models/stdcells/nangate45/*.xml`
- `power_models/mobile_cpu/macros/*.xml`
- `build/mapped/nangate45/<workload>/mobile_cpu_mapped.v`
- `build/mapped/nangate45/<workload>/mobile_cpu_mapped_metrics.md`
- `waves/<workload>_nangate45_mapped_gate.vcd`
- `reports/2416_mapped/nangate45/<workload>_<tech>/2416_power_summary.md`
- `reports/2416_compare/<workload>_<tech>_nangate45/2416_abstraction_compare.md`

## Power-Aware Simulation

The `sim-power` target is a practical Verilator-based approximation of
UPF-aware RTL simulation for this specific project. It uses the same JSON power
scheme that generates UPF, converts it into simulation metadata, and checks:

- legal power-state table combinations,
- power switch behavior,
- isolation behavior while switched domains are off,
- retention save and restore behavior,
- DVFS state requests,
- level-shifter coverage for voltage-crossing states.

This is not a replacement for commercial IEEE 1801 signoff in tools such as
Questa, VCS, or Xcelium. It is an educational model of the same low-power
verification ideas using open-source tooling.

## Workload Flow

The CPU has a tiny 16-bit instruction format. `tools/asm.py` lets you write
small assembly workloads instead of editing `rtl/instr_rom.sv` every time.

```sh
make assemble-workload WORKLOAD=compute_burst
```

The assembler writes:

- `build/workloads/compute_burst.memh`: ROM contents for `$readmemh`.
- `build/workloads/compute_burst.lst`: readable address/opcode listing.

`sim-workload` then passes the generated `.memh` file to Verilator with
`+program=...`, so the same RTL can run different programs without rebuilding
the ROM source. The scenario file controls external power-management pins such
as `sleep_req`, `deep_sleep_req`, `wake_irq`, and `perf_boost`, while the loaded
program creates CPU and memory activity before it reaches `WFI`.

That split is useful when explaining the project:

- the workload models what software is doing on the CPU,
- the scenario models what the platform power manager asks the chip to do,
- the power intent JSON/UPF defines which transitions are legal and protected,
- the Verilator harness checks that the RTL behavior agrees with the intent.

## IEEE 2416 RTL Power Models

The `2416-power` target turns the CPU into a small standards-based power
modeling platform. It creates XML macro models for the RTL blocks, validates
them against `schemas/ieee2416-2025.xsd`, extracts activity from a VCD, and
estimates energy/power by block and power domain.

The first model abstraction is:

```text
Energy =
  leakage(state, PVT) * time
  + clock energy * active cycles
  + event energy * workload events
  + optional RTL toggle energy
```

See `docs/ieee2416_rtl_power_flow.md` for the full walkthrough.

The estimator also writes SVG charts, including a stacked domain power waveform
for each run and bar charts for workload or power-scheme comparisons.

For DVFS exploration, `make 2416-dvfs-explore` replays the same workload at the
OPPs in `configs/dvfs/mobile_cpu_opps.json` and reports energy, average power,
runtime, energy-delay product, and leakage/clock/event/toggle contributor
breakdowns. The normal Joules collateral flow is unchanged; this is an
additional open-source estimator path.

## Synthesis And Gate-Level Simulation

The `synth` target uses Yosys to create a post-synthesis Verilog netlist for
the CPU. It generates a workload-specific instruction ROM, emits a Yosys JSON
netlist, and extracts block-level synthesis metrics.

The `gls` target compiles the synthesized netlist with Verilator and performs a
functional gate-level simulation. The first GLS phase checks externally visible
CPU behavior, not SDF timing.

The `2416-synth-power` target turns the Yosys metrics into
`synthesisCalibratedMacro` IEEE 2416 XML models and runs the same estimator
against workload activity. This creates a clean comparison path:

```text
RTL 2416 model -> synthesis-calibrated 2416 model -> mapped stdcell + memory macro model
```

See `docs/synthesis_gate_flow.md` and
`docs/mapped_stdcell_memory_flow.md` for details.

The mapped flow uses the Nangate45 Liberty file as an open reference standard
cell library. The large Liberty files are installed locally with
`make techlib-nangate45` and intentionally ignored by git. Memory blocks are
kept as ROM/SRAM macros using `macros/memory/*_blackbox.v`, so the mapped model
does not pretend the SRAM was built from random logic gates.

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
