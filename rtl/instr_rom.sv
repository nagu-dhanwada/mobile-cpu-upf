module instr_rom (
  input  logic [31:0] addr,
  output logic [15:0] instr
);
  localparam int DEPTH_WORDS = 64;

  logic [15:0] rom [0:DEPTH_WORDS-1];
  string program_path;
  integer idx;

  initial begin
    for (idx = 0; idx < DEPTH_WORDS; idx = idx + 1) begin
      rom[idx] = 16'h0000;
    end

    rom[0] = 16'h5101; // ADDI r1, r0, 1
    rom[1] = 16'h5212; // ADDI r2, r1, 2
    rom[2] = 16'h1321; // ADD  r3, r2, r1
    rom[3] = 16'h7300; // ST   r3, [r0 + 0]
    rom[4] = 16'h6400; // LD   r4, [r0 + 0]
    rom[5] = 16'hf000; // WFI

    if ($value$plusargs("program=%s", program_path)) begin
      $display("instr_rom: loading program %s", program_path);
      $readmemh(program_path, rom);
    end
  end

  always_comb begin
    instr = rom[addr[7:2]];
  end
endmodule
