# Tcl-like scenario for the power-aware Verilator harness.
# Commands supported by sim/power_aware_tb.cpp:
#   reset <cycles>
#   run <cycles>
#   run_until_mode <RUN|IDLE|LIGHT_SLEEP|DEEP_SLEEP|WAKE> <max_cycles>
#   set <signal> <0|1>
#   pulse <signal> [cycles]
#   expect <signal> <value|RUN|IDLE|LIGHT_SLEEP|DEEP_SLEEP|WAKE>
#   expect_seen_mode <RUN|IDLE|LIGHT_SLEEP|DEEP_SLEEP|WAKE>

reset 4

# Let the selected program execute. Hand-written and generated workloads end
# with WFI, which should produce an IDLE visit and clock-gating behavior. The
# budget covers the tiny request/response load-store bus latency as well as
# generated probes with heavier MMIO traffic.
run_until_mode IDLE 160
expect_seen_mode IDLE

# Exercise DVFS turbo and nominal transitions.
set perf_boost 1
run 3
expect power_mode RUN
expect dvfs_level 2
set perf_boost 0
run 1
expect dvfs_level 1

# Light sleep keeps the domains on but gates clocks and saves retention state.
pulse sleep_req 1
expect power_mode LIGHT_SLEEP
pulse wake_irq 1
run 1
expect power_mode RUN

# Deep sleep switches CPU/MEM domains off, asserts isolation, saves retention,
# then restores the domains on wake.
pulse deep_sleep_req 1
expect power_mode DEEP_SLEEP
run 3
pulse wake_irq 1
run 1
expect power_mode RUN
