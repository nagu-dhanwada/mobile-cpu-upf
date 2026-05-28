module decode_unit (
  input  logic [15:0]                  instr,
  output mobile_cpu_pkg::decoded_instr_t decoded
);
  always_comb begin
    decoded.opcode  = mobile_cpu_pkg::opcode_e'(instr[15:12]);
    decoded.rd      = instr[11:8];
    decoded.rs1     = instr[7:4];
    decoded.rs2_imm = instr[3:0];
  end
endmodule
