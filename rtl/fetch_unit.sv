module fetch_unit (
  input  logic        clk,
  input  logic        reset_n,
  input  logic        enable,
  input  logic        stall,
  input  logic        branch_taken,
  input  logic [31:0] branch_target,
  input  logic [15:0] instr_rdata,
  output logic [31:0] instr_addr,
  output logic [15:0] instr
);
  logic [31:0] pc_q;

  always_ff @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
      pc_q <= 32'h0000_0000;
    end else if (enable && !stall) begin
      if (branch_taken) begin
        pc_q <= branch_target;
      end else begin
        pc_q <= pc_q + 32'd4;
      end
    end
  end

  assign instr_addr = pc_q;
  assign instr      = instr_rdata;
endmodule

