# Cadence Joules RTL Power Flow

This project can generate a VCD stimulus file and a Joules Tcl starter script
for RTL power analysis.

## Generate Inputs

```sh
make joules-input
```

This creates:

- `waves/mobile_cpu_power.vcd`
- `reports/power_sim_vcd_summary.md`
- `build/joules/run_joules_power.tcl`

For a named workload:

```sh
make joules-workload WORKLOAD=memory_burst
```

This assembles `workloads/memory_burst.s`, runs the power-aware VCD
simulation, and creates:

- `waves/memory_burst.vcd`
- `reports/memory_burst_power_sim_vcd_summary.md`
- `build/joules/memory_burst_run_joules_power.tcl`

## Run In Joules

On a machine with Cadence Joules and real technology libraries:

```sh
export JOULES_LIB_FILES="/path/to/typical.lib:/path/to/slow.lib"
joules -files build/joules/run_joules_power.tcl
```

For the workload-specific example:

```sh
export JOULES_LIB_FILES="/path/to/typical.lib:/path/to/slow.lib"
joules -files build/joules/memory_burst_run_joules_power.tcl
```

Some sites use a wrapper command or different invocation, such as:

```sh
joules -f build/joules/run_joules_power.tcl
```

Use the invocation supported by your Cadence installation.

## Important Notes

- The VCD comes from Verilator and maps the design under
  `/TOP/mobile_cpu_power_top/u_dut`.
- The real RTL design top is `mobile_cpu_top`.
- The generated Tcl script uses that DUT instance path to map the wrapper VCD
  activity back to the RTL top.
- Joules needs technology `.lib` files and operating conditions for meaningful
  absolute power numbers.
- The generated script is a strong starting template, not a replacement for a
  site-qualified CAD flow.
