package mobile_cpu_pkg;
  typedef enum logic [3:0] {
    OP_NOP  = 4'h0,
    OP_ADD  = 4'h1,
    OP_SUB  = 4'h2,
    OP_AND  = 4'h3,
    OP_OR   = 4'h4,
    OP_ADDI = 4'h5,
    OP_LD   = 4'h6,
    OP_ST   = 4'h7,
    OP_BEQ  = 4'h8,
    OP_WFI  = 4'hf
  } opcode_e;

  typedef struct packed {
    opcode_e    opcode;
    logic [3:0] rd;
    logic [3:0] rs1;
    logic [3:0] rs2_imm;
  } decoded_instr_t;
endpackage

