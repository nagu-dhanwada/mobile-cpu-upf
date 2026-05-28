# Mapped Standard-Cell And Memory-Macro Power Flow

This phase moves the toy CPU one step closer to an implementation flow while
preserving the earlier RTL, UPF, Joules, and IEEE 2416 modes.

## Architecture

```text
workloads/<name>.s
  -> tools/asm.py
  -> build/workloads/<name>.memh

RTL logic + memory blackboxes + Nangate45 Liberty
  -> tools/run_yosys_synth.py --mapped --memory-macros
  -> build/mapped/nangate45/<name>/mobile_cpu_mapped.v
  -> build/mapped/nangate45/<name>/mobile_cpu_mapped_metrics.json

Liberty
  -> tools/gen_2416_stdcell.py
  -> power_models/stdcells/nangate45/*.xml

memory macro config
  -> tools/gen_memory_macro_2416.py
  -> power_models/mobile_cpu/macros/*.xml

RTL workload VCD + mapped gate VCD + models
  -> tools/estimate_mapped_power_2416.py
  -> reports/2416_mapped/nangate45/<name>_<tech>/
```

## Why Keep Memories As Macros

If a small SRAM is synthesized as flip-flops and gates, the result is useful for
testing the tool flow but misleading for power architecture. Real SoCs normally
use memory compilers or hardened SRAM/ROM macros. This flow therefore blackboxes
`instr_rom` and `data_sram` during mapped synthesis and models their power with
transaction-level 2416 macro coefficients.

That gives a cleaner abstraction:

- standard-cell logic power comes from Liberty-derived cell models and gate VCD
  toggles,
- ROM/SRAM power comes from read/write/fetch events and macro leakage states,
- UPF-style power-state residency still controls leakage and DVFS scaling.

## Main Commands

```sh
make techlib-nangate45
make synth-mapped WORKLOAD=memory_burst
make gls-mapped WORKLOAD=memory_burst
make 2416-mapped-power WORKLOAD=memory_burst TECH=generic_7nm
make 2416-compare-abstractions WORKLOAD=memory_burst TECH=generic_7nm
```

## What To Inspect

- `build/mapped/nangate45/memory_burst/mobile_cpu_mapped_metrics.md`
  shows mapped cell counts by CPU block.
- `power_models/stdcells/nangate45/stdcell_model_summary.md`
  summarizes generated standard-cell coefficients.
- `power_models/mobile_cpu/macros/data_sram.xml`
  shows the memory macro model and its read/write contributors.
- `reports/2416_mapped/nangate45/memory_burst_generic_7nm/2416_power_summary.md`
  shows mapped power by domain and block.
- `reports/2416_compare/memory_burst_generic_7nm_nangate45/2416_abstraction_compare.md`
  compares RTL, synthesis-calibrated, and mapped estimates.

## Current Limitations

The flow is still a reference implementation:

- Liberty internal-power tables are reduced to representative per-toggle
  coefficients.
- There is no placed/routed capacitance or SPEF yet.
- Gate-level simulation is functional, not SDF timing simulation.
- The memory macro coefficients are educational assumptions, not compiler
  characterization data.

The next logical layer is an OpenROAD/OpenLane physical flow that can add
placement, routing, timing, parasitic estimates, and physical-aware 2416 model
updates.
