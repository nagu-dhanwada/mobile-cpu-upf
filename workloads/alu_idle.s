# Default ALU/memory/idle workload.
ADDI r1, r0, 1
ADDI r2, r1, 2
ADD  r3, r2, r1
ST   r3, [r0 + 0]
LD   r4, [r0 + 0]
WFI

