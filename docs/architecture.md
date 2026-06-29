# Architecture Notes

The RTL is a small single-issue CPU model intended for power intent exploration,
not benchmark performance. Its main purpose is to provide realistic hierarchy for
UPF experiments.

```mermaid
flowchart LR
    PC["power_controller"] --> CG0["u_core_clk_gate"]
    PC --> CG1["u_mem_clk_gate"]
    CG0 --> F["fetch_unit"]
    F --> I["instr_rom"]
    F --> D["decode_unit"]
    D --> R["regfile"]
    R --> X["execute_unit"]
    X --> M["data_sram"]
    X --> DF["dataflow_unit"]
    CG1 --> M
    CG1 --> DF
```

## RTL Instances

These top-level instance names are used by the power-scheme JSON files:

- `u_power_controller`
- `u_core_clk_gate`
- `u_mem_clk_gate`
- `u_fetch`
- `u_icache`
- `u_decode`
- `u_regfile`
- `u_execute`
- `u_dmem`
- `u_dataflow`

## Dataflow Unit

`u_dataflow` is a small memory-mapped multiply-accumulate unit used to explore
CPU versus dataflow offload efficiency. In this toy CPU it is still an MMIO
slave peripheral: the CPU reaches it through the ordinary load/store path, it
does not fetch operands from memory by itself, and it shares the existing CPU
power-domain behavior while being clocked through the memory-side clock gate.

The toy MMIO map uses byte offsets that fit the existing 4-bit immediate load
and store format:

| Offset | Access | Meaning |
| ---: | --- | --- |
| `4` | write/read | operand A |
| `5` | write/read | operand B |
| `6` | write/read | command/status |
| `7` | read/write | accumulated result on reads, repeat count on writes |

Command bit `0` starts MAC work. Command bit `1` clears the accumulator. A
command value of `3` clears first and then starts from zero in the same MMIO
access. Command writes are treated as pulses rather than sticky state, so
holding the same command value does not repeatedly launch new operations.

Status reads from offset `6` expose:

| Bit(s) | Meaning |
| ---: | --- |
| `0` | done |
| `1` | busy |
| `2` | repeat count is greater than one |
| `3` | one-cycle MAC-valid pulse |
| `15:8` | remaining repeat count |
| `23:16` | programmed repeat count |

The write side of offset `7` adds a small local repeat-count mode. Software can
write operands once, write a repeat count, and then issue one start command; the
dataflow block performs that many MAC cycles internally using the local operand
registers. This is still intentionally tiny, but it avoids the pure
"one CPU store per MAC" structure for simple repeated operations.

Commercial high-performance accelerators usually go further: the CPU writes
descriptors and status through MMIO, while the accelerator datapath acts as a
data-side bus master or coherent requester to fetch operand streams, perform
many operations locally, and write results back. This CPU does not yet have a
load/store queue, data fabric, cache-coherent port, DMA engine, interrupt path,
or memory protection model, so the current RTL does not pretend to implement
that behavior. A future version could add a requester interface next to
`data_sram` or a small scratchpad/FIFO path before introducing richer ISA
support.

## Power Intent Concepts Covered

- Single-domain always-on operation.
- Clock gating through RTL clock-enable control.
- Switched power domains.
- Isolation on switched-domain outputs.
- Retention for architectural state.
- Multiple supply states for DVFS.
- Level shifters between domains that can operate at different voltages.
