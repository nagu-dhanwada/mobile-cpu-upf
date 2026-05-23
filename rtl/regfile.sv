module regfile (
  input  logic        clk,
  input  logic        reset_n,
  input  logic        retention_enable,
  input  logic        wr_en,
  input  logic [3:0]  wr_addr,
  input  logic [31:0] wr_data,
  input  logic [3:0]  rd_addr_a,
  input  logic [3:0]  rd_addr_b,
  output logic [31:0] rd_data_a,
  output logic [31:0] rd_data_b
);
  logic [31:0] regs [0:15];
  integer idx;

  always_ff @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
      for (idx = 0; idx < 16; idx = idx + 1) begin
        regs[idx] <= 32'h0000_0000;
      end
    end else if (!retention_enable) begin
      if (wr_en && (wr_addr != 4'd0)) begin
        regs[wr_addr] <= wr_data;
      end
    end
  end

  assign rd_data_a = (rd_addr_a == 4'd0) ? 32'h0000_0000 : regs[rd_addr_a];
  assign rd_data_b = (rd_addr_b == 4'd0) ? 32'h0000_0000 : regs[rd_addr_b];
endmodule

