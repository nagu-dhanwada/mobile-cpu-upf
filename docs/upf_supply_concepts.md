# UPF Supply Concepts

This note explains three related UPF concepts used in this project:

- `create_supply_set`
- `add_power_state -supply_expr`
- `set_domain_supply_net`

The examples below come from the generated DVFS UPF for the mobile CPU.

## Mental Model

```text
Power domain = which logic belongs together
Supply set   = which electrical rails power that logic
Power state  = what condition those rails are in
```

For this CPU:

```text
PD_CPU = fetch, decode, register file, and execute logic
SS_CPU = VDD_CPU plus VSS
LOW/NOMINAL/TURBO/OFF = possible electrical conditions of SS_CPU
```

## Supply Set

A supply set is a named bundle of power-related nets that together define how a
logic block is powered.

In the generated UPF:

```tcl
create_supply_set SS_CPU \
  -function {power VDD_CPU} \
  -function {ground VSS}
```

This means:

```text
SS_CPU is the CPU supply set.
Its power function is VDD_CPU.
Its ground function is VSS.
```

The words `power` and `ground` are supply-set functions. They are not RTL
signals. They are abstract roles that UPF uses to describe the electrical supply
context of a domain.

## Supply Expression In `add_power_state`

`add_power_state` defines named electrical states for a supply set.

Example:

```tcl
add_power_state SS_CPU -state TURBO \
  -supply_expr {power == `{FULL_ON, 0.95} && ground == `{FULL_ON, 0}}

add_power_state SS_CPU -state NOMINAL \
  -supply_expr {power == `{FULL_ON, 0.8} && ground == `{FULL_ON, 0}}

add_power_state SS_CPU -state LOW \
  -supply_expr {power == `{FULL_ON, 0.6} && ground == `{FULL_ON, 0}}

add_power_state SS_CPU -state OFF \
  -supply_expr {power == {OFF} && ground == `{FULL_ON, 0}}
```

Meaning:

| UPF State | Electrical Meaning |
| --- | --- |
| `TURBO` | CPU power rail is fully on at 0.95 V, ground is 0 V |
| `NOMINAL` | CPU power rail is fully on at 0.8 V, ground is 0 V |
| `LOW` | CPU power rail is fully on at 0.6 V, ground is 0 V |
| `OFF` | CPU power rail is off, ground is still valid |

So this expression:

```tcl
-supply_expr {power == `{FULL_ON, 0.6} && ground == `{FULL_ON, 0}}
```

means:

```text
This supply set is in the LOW state when its power function is fully on at
0.6 V and its ground function is fully on at 0 V.
```

In this project, the CPU DVFS states are represented as:

```text
TURBO   -> VDD_CPU = 0.95 V
NOMINAL -> VDD_CPU = 0.80 V
LOW     -> VDD_CPU = 0.60 V
OFF     -> VDD_CPU = off
```

## `set_domain_supply_net`

`set_domain_supply_net` binds a power domain to the actual primary supply nets
that power it.

Example:

```tcl
create_power_domain PD_CPU -elements {u_fetch u_decode u_regfile u_execute}

create_supply_set SS_CPU \
  -function {power VDD_CPU} \
  -function {ground VSS}

set_domain_supply_net PD_CPU \
  -primary_power_net VDD_CPU \
  -primary_ground_net VSS
```

This tells the UPF tool:

```text
PD_CPU contains the CPU logic.
VDD_CPU is the primary power rail for PD_CPU.
VSS is the primary ground rail for PD_CPU.
```

The difference between `create_supply_set` and `set_domain_supply_net` is:

```text
create_supply_set
  Creates an abstract named supply object:
  SS_CPU = power VDD_CPU + ground VSS

set_domain_supply_net
  Attaches the actual power domain PD_CPU to its primary power and ground nets.
```

This matters because the tool needs to know:

- what supply powers the cells in the domain,
- which rail is shut off by a power switch,
- where isolation may be needed,
- which voltage domain the logic belongs to,
- which supply state applies to that logic,
- how to check the power-state table.

## Power Switch Connection

The CPU domain is powered through a switch:

```tcl
create_power_switch SW_CPU \
  -domain PD_CPU \
  -input_supply_port {VIN VDD_AON} \
  -output_supply_port {VOUT VDD_CPU} \
  -control_port {CTRL cpu_power_gate_n} \
  -on_state {ON VIN {CTRL}} \
  -off_state {OFF {!CTRL}}
```

The supply path is:

```text
VDD_AON
  -> power switch SW_CPU
  -> VDD_CPU
  -> primary power net of PD_CPU
  -> CPU logic
```

So `set_domain_supply_net` is the command that tells UPF:

```text
PD_CPU runs from the switched rail VDD_CPU.
```

## How This Connects To The PST

After local supply states are defined, the power-state table combines them into
legal system-level states.

Example:

```tcl
create_pst PST_DVFS_RETENTION_DOMAINS -supplies {VDD_AON VDD_CPU VDD_MEM}

add_pst_state TURBO -pst PST_DVFS_RETENTION_DOMAINS -state {ON TURBO ON}
add_pst_state NOMINAL -pst PST_DVFS_RETENTION_DOMAINS -state {ON NOMINAL ON}
add_pst_state LOW_POWER -pst PST_DVFS_RETENTION_DOMAINS -state {ON LOW RET}
add_pst_state DEEP_SLEEP -pst PST_DVFS_RETENTION_DOMAINS -state {ON OFF OFF}
```

This means:

```text
TURBO:
  PD_AON = ON
  PD_CPU = TURBO
  PD_MEM = ON

LOW_POWER:
  PD_AON = ON
  PD_CPU = LOW
  PD_MEM = RET

DEEP_SLEEP:
  PD_AON = ON
  PD_CPU = OFF
  PD_MEM = OFF
```

## One-Line Summary

```text
create_supply_set defines the supply bundle.
add_power_state defines the electrical states of that bundle.
set_domain_supply_net connects a power domain to its actual primary rails.
```
