# Synthesis And Gate-Level Flow

This repository now has an additive synthesis layer on top of the existing RTL,
UPF, Joules, and IEEE 2416 RTL power flows.

The implementation uses Yosys as the open-source synthesis engine and
Verilator for functional post-synthesis simulation. It has two synthesis modes:

- generic Yosys synthesis, where the tiny ROM/SRAM are synthesized into logic,
- mapped Nangate45 synthesis, where ROM/SRAM stay as macros and logic maps to
  real Liberty standard cells.

## Flow

```text
workloads/<name>.s
        |
        v
build/workloads/<name>.memh
        |
        v
build/synth/<name>/instr_rom_synth.sv
        |
        v
Yosys synthesis
        |
        +--> build/synth/<name>/mobile_cpu_gate.v
        +--> build/synth/<name>/mobile_cpu_synth.json
        +--> build/synth/<name>/mobile_cpu_synth_metrics.json
        |
        v
Verilator gate-level functional simulation
        |
        +--> waves/<name>_gate.vcd
        +--> reports/gls/<name>_gate_summary.md
```

## Tool Requirements

The existing RTL and 2416 RTL flows still work without Yosys.

The synthesis targets require:

```sh
brew install yosys
```

Verilator is already used by the project for simulation.

## Synthesize The CPU

```sh
make synth WORKLOAD=memory_burst
```

This creates:

- `build/synth/memory_burst/mobile_cpu_gate.v`
- `build/synth/memory_burst/mobile_cpu_synth.json`
- `build/synth/memory_burst/mobile_cpu_synth.log`
- `build/synth/memory_burst/mobile_cpu_synth_metrics.json`
- `build/synth/memory_burst/mobile_cpu_synth_metrics.md`

The instruction ROM is generated from the workload `.memh` file so the
synthesized netlist has a fixed workload image.

## Run Functional Gate-Level Simulation

```sh
make gls WORKLOAD=memory_burst
```

This compiles the synthesized netlist with Verilator and checks externally
visible behavior:

- reset enters RUN,
- PC advances,
- WFI enters IDLE,
- low-power DVFS is requested in IDLE,
- light sleep and wake are reachable,
- deep sleep and wake are reachable.

This is functional GLS. It is not yet timing/SDF simulation.

## Generate Synthesis-Calibrated IEEE 2416 Models

```sh
make 2416-synth-power WORKLOAD=memory_burst TECH=generic_7nm
```

This does three things:

1. Generates the existing RTL 2416 models.
2. Runs Yosys synthesis and extracts cell metrics.
3. Creates synthesis-calibrated 2416 XML models under:

```text
power_models/mobile_cpu/synth/
```

The generated models use:

```text
modelClass = synthesisCalibratedMacro
abstractionLevel = gate
```

The power estimator then evaluates those synth-calibrated models against the
same workload activity. That gives an apples-to-apples comparison:

```text
RTL macro estimate
vs.
synthesis-calibrated macro estimate
```

The output report is written under:

```text
reports/2416_synth/<workload>_<tech>/
```

## What Is Calibrated

The synthesis layer extracts per-block metrics from the Yosys JSON netlist:

- cell count,
- combinational cell count,
- sequential cell count,
- latch count,
- memory cell count,
- estimated equivalent gates.

Those metrics are used to scale the existing RTL 2416 coefficients into a
synthesis-calibrated model. The model remains educational, but it now has a
real structural synthesis observation behind it.

## Mapped Standard-Cell Plus Memory-Macro Flow

Install or refresh the open reference technology files:

```sh
make techlib-nangate45
```

Then run:

```sh
make synth-mapped WORKLOAD=memory_burst
make gls-mapped WORKLOAD=memory_burst
make 2416-mapped-power WORKLOAD=memory_burst TECH=generic_7nm
```

This mode reads `third_party/nangate45/NangateOpenCellLibrary_typical.lib`,
maps CPU logic to Nangate45 cells with `dfflibmap` and `abc`, and writes:

```text
build/mapped/nangate45/<workload>/mobile_cpu_mapped.v
build/mapped/nangate45/<workload>/mobile_cpu_mapped.json
build/mapped/nangate45/<workload>/mobile_cpu_mapped_metrics.json
build/techlibs/nangate45/NangateOpenCellLibrary.functional.v
waves/<workload>_nangate45_mapped_gate.vcd
reports/gls/<workload>_nangate45_mapped_gate_summary.md
```

The memory blocks are intentionally kept as macros:

```text
macros/memory/instr_rom_blackbox.v
macros/memory/data_sram_blackbox.v
```

For simulation, Verilator links the mapped logic netlist with functional
standard-cell models generated from Liberty and the original behavioral ROM/SRAM
RTL. This keeps the gate-level simulation runnable while preserving the
implementation distinction between standard-cell logic and memory macros.

## 2416 Models At The Mapped Level

The mapped flow adds two model families:

```text
power_models/stdcells/nangate45/*.xml
power_models/mobile_cpu/macros/*.xml
```

The standard-cell XML models are generated from Liberty area, leakage,
capacitance, sequential-cell classification, and internal-power tables. The
memory macro XML models come from
`configs/memory_macros/mobile_cpu_memory_macros.json`.

The mapped estimator combines:

- standard-cell counts from the mapped Yosys JSON netlist,
- gate-level VCD toggles from `gls-mapped`,
- memory macro read/write/fetch events from the RTL workload VCD,
- the same power-state and DVFS residency profile used by the RTL 2416 flow.

Run a side-by-side abstraction comparison:

```sh
make 2416-compare-abstractions WORKLOAD=memory_burst TECH=generic_7nm
```

Example output:

```text
reports/2416_compare/memory_burst_generic_7nm_nangate45/2416_abstraction_compare.md
```

This is the intended abstraction progression:

```text
RTL macro estimate
  -> synthesis-calibrated macro estimate
  -> mapped standard-cell + memory-macro estimate
```

## Current Scope

This phase intentionally stops at functional post-synthesis netlist simulation
and Liberty-based power approximation.

The next phase should add an OpenLane/OpenROAD physical flow:

```text
Yosys netlist
  -> placement/routing
  -> DEF/GDS/SPEF/timing reports
  -> physical-aware IEEE 2416 model
```

That later model should use:

```text
modelClass = implementationMacro
abstractionLevel = physical
```
