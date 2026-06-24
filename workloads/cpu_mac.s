# CPU-only multiply-accumulate style workload using repeated ADDs.
# Computes 2*3 + 4*5 = 26 without the dataflow unit.
ADDI r1, r0, 2
ADDI r2, r0, 3
ADD  r3, r1, r1
ADD  r3, r3, r1
ADDI r4, r0, 4
ADDI r5, r0, 5
ADD  r6, r4, r4
ADD  r6, r6, r4
ADD  r6, r6, r4
ADD  r6, r6, r4
ADD  r7, r3, r6
ST   r7, [r0 + 0]
WFI
