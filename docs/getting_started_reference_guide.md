# Getting Started Reference Guide

This project is a compact mobile CPU power-intent playground for education,
standards exploration, and repeatable low-power flow experiments.

## Project Map

Start with these files:

- `rtl/mobile_cpu_top.sv`: CPU hierarchy and power-control signals.
- `rtl/power_controller.sv`: idle, sleep, deep-sleep, wake, and DVFS controls.
- `power_schemes/04_dvfs_retention_domains.json`: the richest low-power scheme.
- `tools/gen_upf.py`: automatic UPF generator.
- `tools/asm.py`: small workload assembler for this CPU.
- `tools/ieee2416/estimate.py`: OpenLowPower IEEE 2416 power estimation from a
  schema-valid `Library` XML and VCD activity.
- `tools/ieee2416/synth_characterize.py`: synthesis-calibrated OpenLowPower
  IEEE 2416 library generator.
- `tools/ieee2416/stdcell.py`: Liberty-to-OpenLowPower IEEE 2416 standard-cell
  library generator.
- `tools/ieee2416/memory_macros.py`: OpenLowPower IEEE 2416 memory macro
  library generator.
- `tools/run_yosys_synth.py`: Yosys synthesis driver for the CPU.
- `tools/estimate_mapped_power_2416.py`: mapped netlist plus memory-macro
  power estimator.
- `upf/dvfs_retention_domains.upf`: generated power intent.
- `reports/power_summary.md`: quick comparison of schemes.

## Clone The Repo

```sh
git clone https://github.com/YOUR_USER/YOUR_REPO.git
cd YOUR_REPO
```

## Regenerate UPF

```sh
make upf
```

This reads every JSON file in `power_schemes/` and writes generated UPF to
`upf/`.

## Run The Power Exploration

```sh
make explore
```

This writes:

- `reports/power_summary.csv`
- `reports/power_summary.md`

The estimates are architectural placeholders. The useful part is the comparison
between schemes, not the exact absolute milliwatts.

## Run Tests

```sh
make test
```

The tests check UPF generation, IEEE 2416 model generation, validation, VCD
activity extraction, synthesis metrics, and mapped power-estimation utilities.

## Run The Power-Aware Verilator Demo

```sh
make lint-rtl
make sim-power
```

This generates:

- `build/power_sim/power_intent.json`
- `build/power_sim/power_intent.hpp`
- `reports/power_sim_events.json`
- `reports/power_sim_summary.md`
- `waves/mobile_cpu_power.fst`

Open the waveform:

```sh
make waves
```

This is not a full commercial UPF simulator. It is a Verilator simulation
harness that consumes the same power-intent scheme used to generate UPF and
checks the project-specific subset: domains, switches, isolation, retention,
DVFS state requests, level shifters, and legal power-state combinations.

## Run A Named Workload

The CPU can run small assembly workloads from `workloads/*.s`. The assembler
turns those files into ROM images and Verilator loads them into `instr_rom.sv`
using `+program=...`.

```sh
make sim-workload WORKLOAD=memory_burst
make waves-workload WORKLOAD=memory_burst
```

This creates:

- `build/workloads/memory_burst.memh`
- `build/workloads/memory_burst.lst`
- `reports/memory_burst_power_sim_summary.md`
- `waves/memory_burst.fst`

The workload models software activity running on the CPU. The scenario file
models platform power-manager requests such as sleep, deep sleep, wake, and
performance boost. The power intent describes what domains, switches,
isolation, retention, DVFS states, and level shifters must exist for those
transitions.

## Create Joules Inputs

For the built-in program:

```sh
make joules-input
```

For a named workload:

```sh
make joules-workload WORKLOAD=memory_burst
```

This writes a VCD plus a Cadence Joules Tcl starter script. Joules still needs
real technology `.lib` files from a process/library kit before it can produce
meaningful absolute power numbers.

## Run The IEEE 2416 Real-XSD Power Flow

```sh
make 2416-power WORKLOAD=memory_burst TECH=generic_7nm SCHEME=dvfs_retention_domains
```

This generates/uses:

- `$HOME/Downloads/2416.xsd`, or the path passed with `OPENLOWPOWER_2416_XSD`
- `power_models/mobile_cpu/ieee2416/mobile_cpu_library.xml`
- `waves/memory_burst.vcd`
- `reports/2416/memory_burst_generic_7nm_dvfs_retention_domains/2416_power_summary.md`
- `reports/2416/memory_burst_generic_7nm_dvfs_retention_domains/2416_power_waveform.svg`

The generated XML is an OpenLowPower IEEE 2416 `Library` containing executable
power models for each RTL block. The VCD supplies workload activity and
power-state residency. The estimator combines leakage, clock, event, and
optional toggle components to report power by block and by power domain.

For visual comparisons:

```sh
make 2416-compare-workloads TECH=generic_7nm SCHEME=dvfs_retention_domains
make 2416-compare-schemes WORKLOAD=memory_burst TECH=generic_7nm
make 2416-dvfs-explore WORKLOAD=memory_burst TECH=generic_7nm
```

The compare commands produce SVG bar charts for workload energy/power and
power-scheme energy/power under `reports/2416/`. The DVFS command writes
`reports/2416/dvfs/.../dvfs_summary.md`, OPP comparison CSVs, and charts for
energy, average power, runtime, energy-delay product, and contributor
breakdown.

## Generate The Visual Walkthrough

```sh
make visual-story
```

This command builds a default set of hand-written and generated workloads,
profiles them through the OpenLowPower IEEE 2416 flow, and writes a standalone
animated dashboard:

- `reports/visual_story/index.html`

The dashboard shows the CPU datapath, workload cards, an animated power
timeline, domain energy breakdowns, dominant activity events, and energy
tradeoff charts. It is generated output and is ignored by Git. The checked-in
guide is `docs/mobile_cpu_visual_walkthrough.md`.

Open it locally on macOS:

```sh
make open-visual-story
```

## Run Synthesis And Gate-Level Simulation

Install Yosys first if it is not already available:

```sh
brew install yosys
```

Then run:

```sh
make synth WORKLOAD=memory_burst
make gls WORKLOAD=memory_burst
make 2416-synth-power WORKLOAD=memory_burst TECH=generic_7nm
```

This adds a second abstraction layer using the same OpenLowPower IEEE 2416
library structure as the RTL flow. The RTL macro model is characterized from
architectural events. The synthesis-calibrated model uses Yosys cell metrics
from the generated netlist to scale those coefficients. Gate-level simulation
checks that the synthesized netlist still behaves like the CPU before those
netlist metrics are used for power modeling.

## Run The Mapped Standard-Cell Flow

Install or refresh the open reference Nangate45 files:

```sh
make techlib-nangate45
```

Then run the mapped flow:

```sh
make synth-mapped WORKLOAD=memory_burst
make gls-mapped WORKLOAD=memory_burst
make 2416-mapped-power WORKLOAD=memory_burst TECH=generic_7nm
make 2416-compare-abstractions WORKLOAD=memory_burst TECH=generic_7nm
```

The generic synthesis path checks that the RTL can synthesize. The mapped path
goes one level closer to implementation: CPU logic maps to real Nangate45
standard cells, while instruction ROM and data SRAM stay as macros. The mapped
estimator combines OpenLowPower IEEE 2416 standard-cell models,
OpenLowPower memory macro models, RTL power-state residency, and gate-level VCD
toggles.

Useful outputs:

- `build/mapped/nangate45/memory_burst/mobile_cpu_mapped.v`
- `build/mapped/nangate45/memory_burst/mobile_cpu_mapped_metrics.md`
- `power_models/stdcells/nangate45/stdcell_model_summary.md`
- `power_models/stdcells/nangate45/nangate45_stdcells_library.xml`
- `power_models/mobile_cpu/ieee2416/mobile_cpu_memory_macros.xml`
- `reports/2416_mapped/nangate45/memory_burst_generic_7nm_dvfs_retention_domains/2416_power_summary.md`
- `reports/2416_compare/memory_burst_generic_7nm_dvfs_retention_domains_nangate45/2416_abstraction_compare.md`

## Modify A Power Scheme

1. Copy one JSON file in `power_schemes/`.
2. Change the scheme `name`, domain list, states, switches, isolation,
   retention, or level shifters.
3. Run:

```sh
make upf explore test
```

4. Inspect the new UPF file in `upf/`.

## Add A New RTL Block

1. Add the SystemVerilog module under `rtl/`.
2. Instantiate it from `rtl/mobile_cpu_top.sv`.
3. Add its instance name to the right domain in the scheme JSON file.
4. Regenerate UPF:

```sh
make upf
```

## Suggested Walkthrough

Use this order when studying or demonstrating the flow:

1. Review how the RTL hierarchy is split into always-on, CPU-core, and
   memory-style blocks.
2. Inspect `power_controller.sv` and the controls `core_clk_en`, `mem_clk_en`,
   `cpu_power_gate_n`, `mem_power_gate_n`, `iso_core`, `iso_mem`, `ret_save`,
   `ret_restore`, and `dvfs_level`.
3. Inspect `power_schemes/04_dvfs_retention_domains.json` as the source of
   truth for the power strategy.
4. Run `make upf` and open `upf/dvfs_retention_domains.upf`.
5. Review generated UPF constructs: `create_power_domain`,
   `create_power_switch`, `set_isolation`, `set_retention`,
   `set_level_shifter`, and `add_pst_state`.
6. Run `make sim-power` and inspect `reports/power_sim_summary.md`.
7. Run `make sim-workload WORKLOAD=memory_burst` and observe how workload
   activity is separated from power-manager stimulus.
8. Run `make joules-workload WORKLOAD=memory_burst` to create a VCD and Joules
   Tcl starter script for an RTL power-analysis flow.
9. Run `make 2416-power WORKLOAD=memory_burst` to exercise the real-XSD
   OpenLowPower IEEE 2416 model flow.
10. Run `make visual-story` to generate the animated documentation dashboard.
11. Run `make 2416-compare-abstractions WORKLOAD=memory_burst` to compare the
    RTL, synth-calibrated, and mapped OpenLowPower IEEE 2416 estimates.
12. Run `make explore` and inspect the summary table.
13. Run `make test` to check the automation.

## Current Limitations

- This is a design exploration model, not a tapeout-ready CPU.
- The power numbers are early architectural estimates.
- Generated UPF is intentionally tool-neutral and may need small syntax
  adjustments for a specific EDA vendor flow.
- The Verilator power-aware simulation is a project-specific UPF subset model,
  not a full IEEE 1801 signoff simulator.
- The assembly workload language is intentionally tiny and exists to create
  repeatable CPU activity, not to model a production compiler or ISA.
- The Nangate45 mapped flow is an open reference technology-mapping demo, not a
  foundry PDK or signoff power result.
- A full implementation flow would add equivalence checking, timing/SDF
  simulation, UPF-aware implementation checks, extracted parasitics, and
  physical implementation signoff.
