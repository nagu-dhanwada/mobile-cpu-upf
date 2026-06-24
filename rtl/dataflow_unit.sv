module dataflow_unit (
  input  logic        clk,
  input  logic        reset_n,
  input  logic        enable,
  input  logic        req,
  input  logic        we,
  input  logic [1:0]  addr,
  input  logic [31:0] wdata,
  output logic [31:0] rdata,
  output logic        busy,
  output logic        op_valid,
  output logic [31:0] result
);
  logic signed [15:0] operand_a_q;
  logic signed [15:0] operand_b_q;
  logic signed [31:0] acc_q;
  logic               busy_q;
  logic               op_valid_q;
  logic signed [31:0] product;

  assign product  = $signed(operand_a_q) * $signed(operand_b_q);
  assign busy     = busy_q;
  assign op_valid = op_valid_q;
  assign result   = acc_q;

  always_comb begin
    unique case (addr)
      2'd0: rdata = {{16{operand_a_q[15]}}, operand_a_q};
      2'd1: rdata = {{16{operand_b_q[15]}}, operand_b_q};
      2'd2: rdata = {30'h0, busy_q, op_valid_q};
      2'd3: rdata = acc_q;
      default: rdata = 32'h0000_0000;
    endcase
  end

  always_ff @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
      operand_a_q <= 16'sh0000;
      operand_b_q <= 16'sh0000;
      acc_q       <= 32'sh0000_0000;
      busy_q      <= 1'b0;
      op_valid_q  <= 1'b0;
    end else begin
      busy_q     <= 1'b0;
      op_valid_q <= 1'b0;

      if (enable && req && we) begin
        unique case (addr)
          2'd0: operand_a_q <= wdata[15:0];
          2'd1: operand_b_q <= wdata[15:0];
          2'd2: begin
            if (wdata[1]) begin
              acc_q <= 32'sh0000_0000;
            end
            if (wdata[0]) begin
              acc_q      <= (wdata[1] ? 32'sh0000_0000 : acc_q) + product;
              busy_q     <= 1'b1;
              op_valid_q <= 1'b1;
            end
          end
          default: begin
          end
        endcase
      end
    end
  end
endmodule
