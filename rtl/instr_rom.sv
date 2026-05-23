module instr_rom (
  input  logic [31:0] addr,
  output logic [15:0] instr
);
  always_comb begin
    unique case (addr[7:2])
      6'd0: instr = 16'h5101; // ADDI r1, r0, 1
      6'd1: instr = 16'h5212; // ADDI r2, r1, 2
      6'd2: instr = 16'h1321; // ADD  r3, r2, r1
      6'd3: instr = 16'h7300; // ST   r3, [r0 + 0]
      6'd4: instr = 16'h6400; // LD   r4, [r0 + 0]
      6'd5: instr = 16'hf000; // WFI
      default: instr = 16'h0000;
    endcase
  end
endmodule

