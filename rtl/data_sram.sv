module data_sram #(
  parameter int DEPTH_WORDS = 256
) (
  input  logic        clk,
  input  logic        reset_n,
  input  logic        enable,
  input  logic        req,
  input  logic        we,
  input  logic [31:0] addr,
  input  logic [31:0] wdata,
  output logic [31:0] rdata
);
  logic [31:0] mem [0:DEPTH_WORDS-1];
  logic [31:0] rdata_q;
  logic [$clog2(DEPTH_WORDS)-1:0] word_addr;

  assign word_addr = addr[$clog2(DEPTH_WORDS)+1:2];
  assign rdata     = rdata_q;

  always_ff @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
      rdata_q <= 32'h0000_0000;
    end else if (enable && req) begin
      if (we) begin
        mem[word_addr] <= wdata;
      end
      rdata_q <= mem[word_addr];
    end
  end
endmodule

