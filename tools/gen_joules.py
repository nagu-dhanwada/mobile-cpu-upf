#!/usr/bin/env python3
"""Generate a Cadence Joules RTL power-analysis Tcl template."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from power_intent import load_scheme


RTL_FILES = [
    "rtl/mobile_cpu_pkg.sv",
    "rtl/clock_gate.sv",
    "rtl/power_controller.sv",
    "rtl/fetch_unit.sv",
    "rtl/instr_rom.sv",
    "rtl/decode_unit.sv",
    "rtl/regfile.sv",
    "rtl/execute_unit.sv",
    "rtl/load_store_unit.sv",
    "rtl/data_sram.sv",
    "rtl/dataflow_unit.sv",
    "rtl/data_bus_interconnect.sv",
    "rtl/mobile_cpu_top.sv",
]


def tcl_list(items: Iterable[str]) -> str:
    return "[list " + " ".join("{" + item + "}" for item in items) + "]"


def render_script(args: argparse.Namespace) -> str:
    intent = load_scheme(args.scheme, args.schemes)
    rtl_files = [str((args.rtl_root / path).resolve()) for path in RTL_FILES]
    vcd_path = str(args.vcd.resolve())
    upf_path = str(args.upf.resolve())
    report_dir = str(args.report_dir.resolve())

    return f"""# Cadence Joules RTL power-analysis template.
# Generated for scheme: {intent.name}
#
# This script is intended as a practical starting point for a Joules RTL power
# run using the Verilator-generated VCD stimulus. Joules setup varies by site,
# process node, and installed release, so confirm command names/options with
# your local Cadence documentation or CAD support before treating results as
# signoff-quality.
#
# Cadence's public Joules material states that Joules supports RTL/gate-level
# VCD stimulus for time-based RTL power analysis. Meaningful power numbers also
# require real technology libraries and operating conditions from your process.

set DESIGN_TOP mobile_cpu_top
set SCHEME_NAME {intent.name}
set CLOCK_PERIOD_NS 1.111
set VCD_FILE {{{vcd_path}}}
set VCD_DUT_INSTANCE /TOP/mobile_cpu_power_top/u_dut
set UPF_FILE {{{upf_path}}}
set REPORT_DIR {{{report_dir}}}

# Provide technology libraries as a colon-separated environment variable.
# Example:
#   export JOULES_LIB_FILES="/path/slow.lib:/path/typical.lib"
if {{[info exists ::env(JOULES_LIB_FILES)] && $::env(JOULES_LIB_FILES) ne ""}} {{
  set LIB_FILES [split $::env(JOULES_LIB_FILES) ":"]
}} else {{
  set LIB_FILES {{}}
}}

set RTL_FILES {tcl_list(rtl_files)}

file mkdir $REPORT_DIR

puts "== Joules RTL power setup =="
puts "Scheme: $SCHEME_NAME"
puts "Design top: $DESIGN_TOP"
puts "VCD: $VCD_FILE"
puts "VCD DUT scope: $VCD_DUT_INSTANCE"
puts "UPF: $UPF_FILE"
puts "Report dir: $REPORT_DIR"

if {{![file exists $VCD_FILE]}} {{
  error "Missing VCD file: $VCD_FILE. Run: make sim-power-vcd"
}}

if {{[llength $LIB_FILES] == 0}} {{
  puts "WARNING: JOULES_LIB_FILES is not set."
  puts "         Joules needs real technology .lib files for meaningful power."
}} else {{
  foreach lib $LIB_FILES {{
    if {{![file exists $lib]}} {{
      error "Missing library file: $lib"
    }}
  }}
  # Common Cadence-style library read command. Adjust if your Joules release
  # uses a site-specific setup file or command wrapper.
  read_libs $LIB_FILES
}}

foreach rtl $RTL_FILES {{
  if {{![file exists $rtl]}} {{
    error "Missing RTL file: $rtl"
  }}
}}

read_hdl -sv $RTL_FILES
elaborate $DESIGN_TOP
current_design $DESIGN_TOP

# Optional power intent. Some Joules installations use read_power_intent,
# others use read_upf or source a CAD-provided low-power setup wrapper.
if {{[file exists $UPF_FILE]}} {{
  if {{[catch {{read_power_intent -upf $UPF_FILE}} msg]}} {{
    puts "WARNING: read_power_intent failed: $msg"
    if {{[catch {{read_upf $UPF_FILE}} msg2]}} {{
      puts "WARNING: read_upf also failed: $msg2"
      puts "         Continue without UPF if your Joules flow is activity-only."
    }}
  }}
}}

if {{[catch {{create_clock -name clk -period $CLOCK_PERIOD_NS [get_ports clk]}} msg]}} {{
  puts "WARNING: create_clock failed or is unnecessary in this Joules setup: $msg"
}}

# Preferred stimulus command in many recent Joules flows.
# The DUT scope maps the wrapper-generated VCD back to the real RTL top.
if {{[catch {{read_stimulus -file $VCD_FILE -dut_instance $VCD_DUT_INSTANCE}} msg]}} {{
  puts "WARNING: read_stimulus failed: $msg"
  puts "         Try your release's equivalent VCD command, for example:"
  puts "         read_vcd $VCD_FILE -vcd_module $VCD_DUT_INSTANCE"
  error "Could not read VCD stimulus. Adjust the stimulus command for your Joules release."
}}

# Power command names/options can vary between Joules releases. Keep both steps
# explicit so failures point to the exact local command that needs adjustment.
if {{[catch {{compute_power -mode time_based}} msg]}} {{
  puts "WARNING: compute_power -mode time_based failed: $msg"
  puts "         Try: compute_power"
  compute_power
}}

report_power > [file join $REPORT_DIR joules_power.rpt]
if {{[catch {{report_power -by_hierarchy > [file join $REPORT_DIR joules_power_hierarchy.rpt]}} msg]}} {{
  puts "WARNING: hierarchy report failed: $msg"
}}

puts "== Joules RTL power run complete =="
puts "Reports written under $REPORT_DIR"
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scheme", required=True)
    parser.add_argument("--schemes", type=Path, default=Path("power_schemes"))
    parser.add_argument("--rtl-root", type=Path, default=Path("."))
    parser.add_argument("--vcd", type=Path, default=Path("waves/mobile_cpu_power.vcd"))
    parser.add_argument("--upf", type=Path, default=Path("upf/dvfs_retention_domains.upf"))
    parser.add_argument("--report-dir", type=Path, default=Path("reports/joules"))
    parser.add_argument("--out", type=Path, default=Path("build/joules/run_joules_power.tcl"))
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_script(args), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
