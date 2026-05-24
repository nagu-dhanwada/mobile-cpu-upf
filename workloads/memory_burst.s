# Store/load-heavy workload to create memory activity before WFI.
ADDI r1, r0, 1
ADDI r2, r0, 2
ADDI r3, r0, 3
ADDI r4, r0, 4
ST   r1, [r0 + 0]
ST   r2, [r0 + 1]
ST   r3, [r0 + 2]
ST   r4, [r0 + 3]
LD   r5, [r0 + 0]
LD   r6, [r0 + 1]
LD   r7, [r0 + 2]
LD   r8, [r0 + 3]
WFI

