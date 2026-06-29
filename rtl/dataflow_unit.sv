module dataflow_unit #(
  parameter int RESPONSE_DELAY = 1
) (
  input  logic        clk,
  input  logic        reset_n,
  input  logic        enable,
  input  logic        req_valid,
  output logic        req_ready,
  input  logic        req_we,
  input  logic [1:0]  req_addr,
  input  logic [31:0] req_wdata,
  output logic        resp_valid,
  output logic [31:0] resp_rdata,
  output logic        resp_error,
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
  logic               command_write_held_q;
  logic               access_fire;
  logic               command_write_access;
  logic               command_write_pulse;
  logic [REPEAT_COUNT_WIDTH-1:0] repeat_count_effective;
  logic               resp_pending_q;
  logic [7:0]         resp_delay_q;
  logic               resp_valid_q;
  logic [31:0]        resp_rdata_q;
  logic               resp_error_q;
  logic signed [31:0] product;
  logic [31:0]        status_word;
  logic [31:0]        read_data;

  function automatic [7:0] delay_reload(input int configured_delay);
    if (configured_delay <= 1) begin
      delay_reload = 8'd0;
    end else if (configured_delay > 256) begin
      delay_reload = 8'd255;
    end else begin
      delay_reload = configured_delay[7:0] - 8'd1;
    end
  endfunction

  assign product  = $signed(operand_a_q) * $signed(operand_b_q);
  assign req_ready = enable && !resp_pending_q;
  assign access_fire = req_valid && req_ready;
  assign busy     = busy_q;
  assign op_valid = op_valid_q;
  assign result   = acc_q;
  assign resp_valid = resp_valid_q;
  assign resp_rdata = resp_rdata_q;
  assign resp_error = resp_error_q;

  // The command register is write-one-to-act, not a sticky control register.
  // A held command request is accepted once so a constant command value does
  // not launch a new MAC every clock.
  assign command_write_access = access_fire && req_we && (req_addr == ADDR_CMD_STATUS);
  assign command_write_pulse  = command_write_access && !command_write_held_q;

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
    unique case (req_addr)
      ADDR_OPERAND_A:  read_data = {{16{operand_a_q[15]}}, operand_a_q};
      ADDR_OPERAND_B:  read_data = {{16{operand_b_q[15]}}, operand_b_q};
      ADDR_CMD_STATUS: read_data = status_word;
      ADDR_RESULT:     read_data = acc_q;
      default: read_data = 32'h0000_0000;
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
      command_write_held_q <= 1'b0;
      resp_pending_q <= 1'b0;
      resp_delay_q <= 8'd0;
      resp_valid_q <= 1'b0;
      resp_rdata_q <= 32'h0000_0000;
      resp_error_q <= 1'b0;
    end else begin
      op_valid_q <= 1'b0;
      resp_valid_q <= 1'b0;
      command_write_held_q <= req_valid && req_we && (req_addr == ADDR_CMD_STATUS);

      if (!enable) begin
        command_write_held_q <= 1'b0;
        resp_pending_q <= 1'b0;
        resp_valid_q <= 1'b0;
      end else begin
        // This is an MMIO slave peripheral reached through the CPU load/store
        // bus. Operand/register writes are ordinary MMIO state updates; command
        // writes below are pulses that kick the local datapath.
        if (access_fire) begin
          resp_pending_q <= 1'b1;
          resp_delay_q <= delay_reload(RESPONSE_DELAY);
          resp_rdata_q <= read_data;
          resp_error_q <= 1'b0;

          unique case (req_addr)
            ADDR_OPERAND_A: if (req_we) operand_a_q <= req_wdata[15:0];
            ADDR_OPERAND_B: if (req_we) operand_b_q <= req_wdata[15:0];
            ADDR_RESULT: begin
              if (req_we) begin
                repeat_count_q <= (req_wdata[REPEAT_COUNT_WIDTH-1:0] == '0)
                                  ? REPEAT_ONE
                                  : req_wdata[REPEAT_COUNT_WIDTH-1:0];
              end
            end
            default: begin
            end
          endcase
        end else if (resp_pending_q) begin
          if (resp_delay_q == 8'd0) begin
            resp_pending_q <= 1'b0;
            resp_valid_q <= 1'b1;
          end else begin
            resp_delay_q <= resp_delay_q - 8'd1;
          end
        end

        if (command_write_pulse && (req_wdata[1:0] != 2'b00)) begin
          busy_q      <= 1'b0;
          remaining_q <= '0;
          done_q      <= 1'b0;

          // Clear has priority. Command value 3 is therefore a deterministic
          // clear-then-start operation, so the first MAC accumulates from 0.
          if (req_wdata[1]) begin
            acc_q <= 32'sh0000_0000;
          end

          if (req_wdata[0]) begin
            acc_q      <= (req_wdata[1] ? 32'sh0000_0000 : acc_q) + product;
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
