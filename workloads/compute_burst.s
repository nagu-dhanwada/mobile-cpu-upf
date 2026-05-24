# ALU-heavy workload to increase core switching before WFI.
ADDI r1, r0, 1
ADDI r2, r0, 2
ADD  r3, r1, r2
SUB  r4, r3, r1
AND  r5, r3, r4
OR   r6, r5, r2
ADD  r7, r6, r3
SUB  r8, r7, r4
AND  r9, r8, r7
OR   r10, r9, r1
WFI

