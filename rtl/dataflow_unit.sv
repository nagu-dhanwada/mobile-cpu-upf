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
  localparam logic [1:0] ADDR_OPERAND_A  = 2'd0;
  localparam logic [1:0] ADDR_OPERAND_B  = 2'd1;
  localparam logic [1:0] ADDR_CMD_STATUS = 2'd2;
  localparam logic [1:0] ADDR_RESULT     = 2'd3;

  localparam int REPEAT_COUNT_WIDTH = 8;
  localparam logic [REPEAT_COUNT_WIDTH-1:0] REPEAT_ONE = {{(REPEAT_COUNT_WIDTH-1){1'b0}}, 1'b1};

  logic signed [15:0] operand_a_q;
  logic signed [15:0] operand_b_q;
  logic signed [31:0] acc_q;
  logic [REPEAT_COUNT_WIDTH-1:0] repeat_count_q;
  logic [REPEAT_COUNT_WIDTH-1:0] remaining_q;
  logic               busy_q;
  logic               done_q;
  logic               op_valid_q;
  logic               command_write_q;
  logic               write_access;
  logic               command_write_access;
  logic               command_write_pulse;
  logic [REPEAT_COUNT_WIDTH-1:0] repeat_count_effective;
  logic signed [31:0] product;
  logic [31:0]        status_word;

  assign product  = $signed(operand_a_q) * $signed(operand_b_q);
  assign busy     = busy_q;
  assign op_valid = op_valid_q;
  assign result   = acc_q;
  assign write_access = enable && req && we;

  // The command register is write-one-to-act, not a sticky control register.
  // A held command bus cycle is accepted once so a constant command value does
  // not launch a new MAC every clock. A future valid/ready bus would make the
  // transaction boundary explicit.
  assign command_write_access = write_access && (addr == ADDR_CMD_STATUS);
  assign command_write_pulse  = command_write_access && !command_write_q;

  assign repeat_count_effective = (repeat_count_q == '0) ? REPEAT_ONE : repeat_count_q;

  // Status keeps the old low-bit shape useful while making the fields explicit:
  // bit 0 done, bit 1 busy, bit 2 repeat count is greater than one, bit 3
  // one-cycle MAC-valid pulse, bits 15:8 remaining count, bits 23:16 repeat.
  assign status_word = {
    8'h00,
    repeat_count_q,
    remaining_q,
    4'h0,
    op_valid_q,
    (repeat_count_effective != REPEAT_ONE),
    busy_q,
    done_q
  };

  always_comb begin
    unique case (addr)
      ADDR_OPERAND_A:  rdata = {{16{operand_a_q[15]}}, operand_a_q};
      ADDR_OPERAND_B:  rdata = {{16{operand_b_q[15]}}, operand_b_q};
      ADDR_CMD_STATUS: rdata = status_word;
      ADDR_RESULT:     rdata = acc_q;
      default: rdata = 32'h0000_0000;
    endcase
  end

  always_ff @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
      operand_a_q <= 16'sh0000;
      operand_b_q <= 16'sh0000;
      acc_q       <= 32'sh0000_0000;
      repeat_count_q <= REPEAT_ONE;
      remaining_q <= '0;
      busy_q      <= 1'b0;
      done_q      <= 1'b0;
      op_valid_q  <= 1'b0;
      command_write_q <= 1'b0;
    end else begin
      op_valid_q <= 1'b0;
      command_write_q <= command_write_access;

      if (!enable) begin
        command_write_q <= 1'b0;
      end else begin
        // This is an MMIO slave peripheral reached through the CPU load/store
        // path. Operand/register writes are ordinary MMIO state updates; command
        // writes below are pulses that kick the local datapath.
        if (write_access) begin
          unique case (addr)
            ADDR_OPERAND_A: operand_a_q <= wdata[15:0];
            ADDR_OPERAND_B: operand_b_q <= wdata[15:0];
            ADDR_RESULT: begin
              repeat_count_q <= (wdata[REPEAT_COUNT_WIDTH-1:0] == '0)
                                ? REPEAT_ONE
                                : wdata[REPEAT_COUNT_WIDTH-1:0];
            end
            default: begin
            end
          endcase
        end

        if (command_write_pulse && (wdata[1:0] != 2'b00)) begin
          busy_q      <= 1'b0;
          remaining_q <= '0;
          done_q      <= 1'b0;

          // Clear has priority. Command value 3 is therefore a deterministic
          // clear-then-start operation, so the first MAC accumulates from 0.
          if (wdata[1]) begin
            acc_q <= 32'sh0000_0000;
          end

          if (wdata[0]) begin
            acc_q      <= (wdata[1] ? 32'sh0000_0000 : acc_q) + product;
            op_valid_q <= 1'b1;
            if (repeat_count_effective > REPEAT_ONE) begin
              remaining_q <= repeat_count_effective - REPEAT_ONE;
              busy_q      <= 1'b1;
            end else begin
              done_q <= 1'b1;
            end
          end else begin
            done_q <= 1'b1;
          end
        end else if (busy_q) begin
          acc_q      <= acc_q + product;
          op_valid_q <= 1'b1;
          if (remaining_q <= REPEAT_ONE) begin
            remaining_q <= '0;
            busy_q      <= 1'b0;
            done_q      <= 1'b1;
          end else begin
            remaining_q <= remaining_q - REPEAT_ONE;
          end
        end
      end
    end
  end
endmodule
