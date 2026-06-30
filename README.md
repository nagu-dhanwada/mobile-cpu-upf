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
workload_specs/  High-level specs for generated synthetic workloads
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
summary and waveform. Use `WORKLOAD=alu_idle`, `WORKLOAD=compute_burst`,
`WORKLOAD=memory_burst`, `WORKLOAD=cpu_mac`, `WORKLOAD=dataflow_mac`, or add
another `.s` file under `workloads/`.

Open that workload waveform:

```sh
make waves-workload WORKLOAD=memory_burst
```

Generate a synthetic workload from a high-level intent spec:

```sh
make gen-workload GEN_WORKLOAD=dataflow_energy_probe
```

This reads `workload_specs/dataflow_energy_probe.json`, writes generated
assembly under `workloads/generated/`, and records the resolved instruction mix
under `build/workloadgen/dataflow_energy_probe/`.

Assemble and simulate that generated workload:

```sh
make assemble-generated GEN_WORKLOAD=dataflow_energy_probe
make sim-generated GEN_WORKLOAD=dataflow_energy_probe SCHEME=dvfs_retention_domains
```

Profile generated workload energy and instruction behavior:

```sh
make profile-generated GEN_WORKLOAD=dataflow_energy_probe TECH=generic_7nm SCHEME=dvfs_retention_domains
```

See `docs/workload_generation.md` for the intent format and supported profiles.

Generate the visual walkthrough dashboard:

```sh
make visual-story
```

This builds the default demo workload set, profiles each case through the
OpenLowPower IEEE 2416 flow, and writes a standalone animated HTML dashboard to
`reports/visual_story/index.html`. The checked-in guide is
`docs/mobile_cpu_visual_walkthrough.md`.

Run the RTL power/performance check-in methodology:

```sh
make power-baseline TECH=generic_7nm SCHEME=clock_gated_idle
make power-check TECH=generic_7nm SCHEME=clock_gated_idle
```

`power-baseline` captures the current workload-suite metrics under
`reports/baselines/power_metrics_baseline.json`. `power-check` regenerates the
same metrics, compares against the baseline, writes
`reports/power_metrics_delta.json` and `reports/checkin_summary.md`, and updates
the visual story with check-in summary, metric deltas, hierarchy attribution,
designer cards, and missing instrumentation. Thresholds are configurable in
`power_check_config.json`, and event-to-RTL attribution lives in
`power_hierarchy_map.json`. For CI-style blocking on red regressions, run:

```sh
make power-check-ci TECH=generic_7nm SCHEME=clock_gated_idle
```

See `docs/rtl_power_checkin_methodology.md`.

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

Run the real-XSD IEEE 2416 power flow:

```sh
make 2416-power WORKLOAD=memory_burst TECH=generic_7nm SCHEME=dvfs_retention_domains
```

This generates an OpenLowPower IEEE 2416 `Library` XML for the CPU blocks,
validates it against `$HOME/Downloads/2416.xsd` by default, runs the workload
VCD simulation, and writes power reports under
`reports/2416/memory_burst_generic_7nm_dvfs_retention_domains/`.

Override the XSD path when needed:

```sh
make 2416-validate OPENLOWPOWER_2416_XSD=/path/to/2416.xsd
```

The older `p2416-*` command names remain as aliases, and both aliases and
plain `2416-*` targets use the same real-XSD OpenLowPower path. See
`docs/openlowpower_2416_flow.md`.

Profile architecture-efficiency metrics for a workload:

```sh
make profile-workload WORKLOAD=dataflow_mac TECH=generic_7nm SCHEME=dvfs_retention_domains
```

This writes instruction mix, memory intensity, dataflow activity, low-power
residency, energy-per-instruction, and recovery-energy metrics under the IEEE
2416 report directory.

Compare CPU-only and dataflow-assisted MAC workloads:

```sh
make compare-dataflow TECH=generic_7nm SCHEME=dvfs_retention_domains
```

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

DVFS exploration replays the same OpenLowPower IEEE 2416 model at each
configured OPP and writes comparison charts under `reports/2416/dvfs/`.

Synthesize the CPU with Yosys and run functional gate-level simulation:

```sh
make synth WORKLOAD=memory_burst
make gls WORKLOAD=memory_burst
```

Generate synthesis-calibrated IEEE 2416 models and power estimates:

```sh
make 2416-synth-power WORKLOAD=memory_burst TECH=generic_7nm
```

Synthesis-calibrated and mapped estimates use real OpenLowPower IEEE 2416
`Library` XML models validated against the same XSD as the RTL flow.

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
- `build/workloadgen/<name>/workload_intent.json`
- `waves/<workload>.fst`
- `waves/<workload>.vcd`
- `build/joules/<workload>_run_joules_power.tcl`
- `power_models/mobile_cpu/ieee2416/mobile_cpu_library.xml`
- `power_models/mobile_cpu/ieee2416/mobile_cpu_synth_library.xml`
- `power_models/mobile_cpu/ieee2416/mobile_cpu_memory_macros.xml`
- `power_models/stdcells/nangate45/nangate45_stdcells_library.xml`
- `reports/2416/<workload>_<tech>_<scheme>/2416_power_summary.md`
- `reports/2416/<workload>_<tech>_<scheme>/2416_power_waveform.svg`
- `reports/2416/<workload>_<tech>_<scheme>/workload_profile/workload_profile.md`
- `reports/visual_story/index.html`
- `reports/2416/compare_workloads_<tech>_<scheme>/2416_compare_energy.svg`
- `reports/2416/compare_schemes_<workload>_<tech>/2416_compare_energy.svg`
- `reports/2416/dvfs/<workload>_<tech>_<scheme>/dvfs_summary.md`
- `reports/2416/dvfs/<workload>_<tech>_<scheme>/dvfs_contributors.svg`
- `build/synth/<workload>/mobile_cpu_gate.v`
- `build/synth/<workload>/mobile_cpu_synth_metrics.md`
- `waves/<workload>_gate.vcd`
- `reports/gls/<workload>_gate_summary.md`
- `reports/2416_synth/<workload>_<tech>_<scheme>/2416_power_summary.md`
- `build/mapped/nangate45/<workload>/mobile_cpu_mapped.v`
- `build/mapped/nangate45/<workload>/mobile_cpu_mapped_metrics.md`
- `waves/<workload>_nangate45_mapped_gate.vcd`
- `reports/2416_mapped/nangate45/<workload>_<tech>_<scheme>/2416_power_summary.md`
- `reports/2416_compare/<workload>_<tech>_<scheme>_nangate45/2416_abstraction_compare.md`

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

The `cpu_mac` and `dataflow_mac` workloads are paired architecture experiments.
`cpu_mac` performs a tiny multiply-accumulate style task with repeated ALU
operations. `dataflow_mac` drives the memory-mapped `u_dataflow` unit through
ordinary stores and loads, then the profiler compares instruction mix, dataflow
MAC activity, low-power residency, and energy-per-instruction.

## IEEE 2416 Power Models

The `2416-power` target is the primary standards-oriented path. It creates an
OpenLowPower IEEE 2416 `Library` XML for the RTL blocks, validates it against
the XSD supplied with `OPENLOWPOWER_2416_XSD`, extracts activity from a VCD, and
estimates energy/power by block and power domain.

The first model abstraction is:

```text
Energy =
  leakage(state, PVT) * time
  + clock energy * active cycles
  + event energy * workload events
  + optional RTL toggle energy
```

See `docs/openlowpower_2416_flow.md` for the full walkthrough.

The estimator also writes SVG charts, including a stacked domain power waveform
for each run and bar charts for workload or power-scheme comparisons.

For DVFS exploration, `make 2416-dvfs-explore` replays the same workload at the
OPPs in `configs/dvfs/mobile_cpu_opps.json` using the same OpenLowPower IEEE
2416 model coefficients. It reports energy, average power, runtime,
energy-delay product, and leakage/clock/event/toggle contributor breakdowns.
The normal Joules collateral flow is unchanged.

## Synthesis And Gate-Level Simulation

The `synth` target uses Yosys to create a post-synthesis Verilog netlist for
the CPU. It generates a workload-specific instruction ROM, emits a Yosys JSON
netlist, and extracts block-level synthesis metrics.

The `gls` target compiles the synthesized netlist with Verilator and performs a
functional gate-level simulation. The first GLS phase checks externally visible
CPU behavior, not SDF timing.

The `2416-synth-power` target turns Yosys metrics into an OpenLowPower IEEE
2416 synthesis-calibrated `Library` XML and estimates power against workload
activity. This creates a clean comparison path:

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
