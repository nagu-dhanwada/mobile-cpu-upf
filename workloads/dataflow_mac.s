# Dataflow-assisted multiply-accumulate workload.
# MMIO offsets: 4 operand A, 5 operand B, 6 command, 7 accumulated result.
# Command bit 0 starts one MAC; command bit 1 clears the accumulator.
ADDI r1, r0, 2
ADDI r2, r0, 3
ADDI r3, r0, 1
ADDI r4, r0, 4
ADDI r5, r0, 5
ADDI r6, r0, 2
ST   r6, [r0 + 6]
ST   r1, [r0 + 4]
ST   r2, [r0 + 5]
ST   r3, [r0 + 6]
ST   r4, [r0 + 4]
ST   r5, [r0 + 5]
ST   r3, [r0 + 6]
LD   r7, [r0 + 7]
ST   r7, [r0 + 0]
WFI
