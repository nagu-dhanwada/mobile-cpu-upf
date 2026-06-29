# Dataflow repeat-count workload.
# MMIO offsets: 4 operand A, 5 operand B, 6 command/status, 7 result/repeat.
# Offset 7 writes program repeat count; offset 7 reads accumulated result.
# This computes four local MAC cycles: acc = 4 * (2 * 3) = 24.
ADDI r1, r0, 2
ADDI r2, r0, 3
ADDI r3, r0, 4
ADDI r4, r0, 3
ST   r1, [r0 + 4]
ST   r2, [r0 + 5]
ST   r3, [r0 + 7]
ST   r4, [r0 + 6]
NOP
NOP
NOP
NOP
LD   r7, [r0 + 7]
ST   r7, [r0 + 0]
WFI
