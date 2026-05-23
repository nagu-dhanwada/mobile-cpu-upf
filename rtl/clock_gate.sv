module clock_gate (
  input  logic clk,
  input  logic reset_n,
  input  logic enable,
  input  logic scan_enable,
  output logic gated_clk
);
  logic latched_enable;

  always_latch begin
    if (!clk) begin
      latched_enable <= enable | scan_enable;
    end
  end

  assign gated_clk = clk & latched_enable;
endmodule

