(* blackbox *)
module data_sram #(
  parameter DEPTH_WORDS = 256
) (
  input         clk,
  input         reset_n,
  input         enable,
  input         req,
  input         we,
  input  [31:0] addr,
  input  [31:0] wdata,
  output [31:0] rdata
);
endmodule
