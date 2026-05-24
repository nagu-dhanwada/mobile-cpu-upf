# Getting Started And Interview Guide

This project is a compact mobile CPU power-intent playground. It is designed to
show that you understand both RTL hierarchy and UPF-driven low-power
implementation planning.

## What To Show First

Start with the problem statement:

> This is a small SystemVerilog mobile CPU partitioned so different power
> optimization schemes can be explored automatically. Each JSON scheme generates
> a matching UPF file, and a simple estimator compares expected power impact.

Then show these files:

- `rtl/mobile_cpu_top.sv`: CPU hierarchy and power-control signals.
- `rtl/power_controller.sv`: idle, sleep, deep-sleep, wake, and DVFS controls.
- `power_schemes/04_dvfs_retention_domains.json`: the richest low-power scheme.
- `tools/gen_upf.py`: automatic UPF generator.
- `tools/asm.py`: small workload assembler for this CPU.
- `tools/estimate_power_2416.py`: RTL power estimation from IEEE 2416 XML
  models and VCD activity.
- `upf/dvfs_retention_domains.upf`: generated power intent.
- `reports/power_summary.md`: quick comparison of schemes.

## How To Clone The Repo

After this project is pushed to GitHub:

```sh
git clone https://github.com/YOUR_USER/YOUR_REPO.git
cd YOUR_REPO
```

## How To Regenerate UPF

```sh
make upf
```

This reads every JSON file in `power_schemes/` and writes generated UPF to
`upf/`.

## How To Run The Power Exploration

```sh
make explore
```

This writes:

- `reports/power_summary.csv`
- `reports/power_summary.md`

The estimates are architectural placeholders. The useful part is the comparison
between schemes, not the exact absolute milliwatts.

## How To Run Tests

```sh
make test
```

The current test verifies that every scheme can generate UPF and that important
constructs such as power switches, isolation, retention, PST states, and level
shifters appear where expected.

## How To Run The Power-Aware Verilator Demo

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

Explain it honestly:

> This is not a full commercial UPF simulator. It is a Verilator simulation
> harness that consumes the same power-intent scheme used to generate UPF and
> checks the project-specific subset: domains, switches, isolation, retention,
> DVFS state requests, level shifters, and legal power-state combinations.

## How To Run A Named Workload

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

Explain the split this way:

> The workload is the software activity running on the CPU. The scenario file is
> the platform power manager driving sleep, deep sleep, wake, and performance
> boost requests. The power intent describes what domains, switches, isolation,
> retention, DVFS states, and level shifters must exist for those transitions.

## How To Create Joules Inputs

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

## How To Run The IEEE 2416 RTL Power Flow

```sh
make 2416-power WORKLOAD=memory_burst TECH=generic_7nm
```

This generates/uses:

- `schemas/ieee2416-2025.xsd`
- `power_models/mobile_cpu/rtl/*.xml`
- `waves/memory_burst.vcd`
- `reports/2416/memory_burst_generic_7nm/2416_power_summary.md`
- `reports/2416/memory_burst_generic_7nm/2416_power_waveform.svg`

Explain it this way:

> The XML files are executable macro power models for each RTL block. The VCD
> supplies workload activity and power-state residency. The estimator combines
> leakage, clock, event, and optional toggle components to report power by block
> and by power domain.

For visual comparisons:

```sh
make 2416-compare-workloads TECH=generic_7nm SCHEME=dvfs_retention_domains
make 2416-compare-schemes WORKLOAD=memory_burst TECH=generic_7nm
make 2416-dvfs-explore WORKLOAD=memory_burst TECH=generic_7nm
```

Those commands produce SVG bar charts for workload energy/power and
power-scheme energy/power. The DVFS command additionally writes
`reports/2416/dvfs/.../dvfs_summary.md`, OPP comparison CSVs, and charts for
energy, average power, runtime, energy-delay product, and contributor breakdown.

In an interview, explain DVFS this way:

> The same workload activity is replayed at LOW, NOMINAL, and TURBO operating
> points. Frequency changes runtime, voltage changes dynamic and leakage
> scaling, and the 2416 contributors show whether the result is dominated by
> leakage, clocking, workload events, or RTL toggles.

## How To Modify A Power Scheme

1. Copy one JSON file in `power_schemes/`.
2. Change the scheme `name`, domain list, states, switches, isolation,
   retention, or level shifters.
3. Run:

```sh
make upf explore test
```

4. Inspect the new UPF file in `upf/`.

## How To Add A New RTL Block

1. Add the SystemVerilog module under `rtl/`.
2. Instantiate it from `rtl/mobile_cpu_top.sv`.
3. Add its instance name to the right domain in the scheme JSON file.
4. Regenerate UPF:

```sh
make upf
```

## Interview Walkthrough

Use this order:

1. Explain that the RTL hierarchy was intentionally split into always-on,
   CPU-core, and memory-style blocks.
2. Show `power_controller.sv` and point out these controls:
   `core_clk_en`, `mem_clk_en`, `cpu_power_gate_n`, `mem_power_gate_n`,
   `iso_core`, `iso_mem`, `ret_save`, `ret_restore`, and `dvfs_level`.
3. Show `power_schemes/04_dvfs_retention_domains.json` and explain that it is
   the source of truth for the power strategy.
4. Run `make upf` and open `upf/dvfs_retention_domains.upf`.
5. Point out generated UPF constructs:
   `create_power_domain`, `create_power_switch`, `set_isolation`,
   `set_retention`, `set_level_shifter`, and `add_pst_state`.
6. Run `make sim-power` and show `reports/power_sim_summary.md`.
7. Run `make sim-workload WORKLOAD=memory_burst` and show how workload activity
   is separated from power-manager stimulus.
8. Run `make joules-workload WORKLOAD=memory_burst` and explain that it creates
   a VCD and Joules Tcl starter script for an industry RTL power-analysis flow.
9. Run `make 2416-power WORKLOAD=memory_burst` and show the standards-based
   XML model flow replacing the placeholder estimator.
10. Run `make explore` and show the summary table.
11. Run `make test` to show the automation is checked.

## Honest Limitations To Mention

- This is a design exploration model, not a tapeout-ready CPU.
- The power numbers are early architectural estimates.
- Generated UPF is intentionally tool-neutral and may need small syntax
  adjustments for a specific EDA vendor flow.
- The Verilator power-aware simulation is a project-specific UPF subset model,
  not a full IEEE 1801 signoff simulator.
- The assembly workload language is intentionally tiny and exists to create
  repeatable CPU activity, not to model a production compiler or ISA.
- A real flow would add synthesis, simulation, UPF-aware verification,
  equivalence checks, and physical implementation signoff.

## Strong Interview Closing

You can say:

> I built this to demonstrate the workflow: design hierarchy, define power
> domains, express strategies declaratively, generate UPF automatically, and
> compare schemes. I also added workload-driven Verilator runs that produce VCD
> activity and a Joules Tcl starter script, so the same demo can connect to a
> real RTL power-analysis environment when technology libraries are available.
