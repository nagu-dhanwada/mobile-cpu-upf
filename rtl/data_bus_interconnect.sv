module data_bus_interconnect #(
  parameter int SRAM_RESPONSE_DELAY = 1
) (
  input  logic        clk,
  input  logic        reset_n,
  input  logic        enable,

  input  logic        req_valid,
  output logic        req_ready,
  input  logic        req_we,
  input  logic [31:0] req_addr,
  input  logic [31:0] req_wdata,
  input  logic [3:0]  req_byte_en,
  output logic        resp_valid,
  output logic [31:0] resp_rdata,
  output logic        resp_error,

  output logic        sram_req,
  output logic        sram_we,
  output logic [31:0] sram_addr,
  output logic [31:0] sram_wdata,
  input  logic [31:0] sram_rdata,

  output logic        dataflow_req_valid,
  input  logic        dataflow_req_ready,
  output logic        dataflow_req_we,
  output logic [1:0]  dataflow_req_addr,
  output logic [31:0] dataflow_req_wdata,
  input  logic        dataflow_resp_valid,
  input  logic [31:0] dataflow_resp_rdata,
  input  logic        dataflow_resp_error
);
  typedef enum logic [1:0] {
    TARGET_NONE,
    TARGET_SRAM,
    TARGET_DATAFLOW,
    TARGET_ERROR
  } target_e;

  target_e target_q;

  logic       busy_q;
  logic [7:0] delay_q;
  logic       resp_valid_q;
  logic [31:0] resp_rdata_q;
  logic       resp_error_q;
  logic       dataflow_sel;
  logic       sram_sel;
  logic       error_sel;
  logic       accept;

  function automatic [7:0] delay_reload(input int configured_delay);
    if (configured_delay <= 1) begin
      delay_reload = 8'd0;
    end else if (configured_delay > 256) begin
      delay_reload = 8'd255;
    end else begin
      delay_reload = configured_delay[7:0] - 8'd1;
    end
  endfunction

  assign dataflow_sel = (req_addr[3:2] == 2'b01);
  assign sram_sel     = !dataflow_sel && (req_addr[31:10] == 22'h0);
  assign error_sel    = !dataflow_sel && !sram_sel;

  assign req_ready = enable && !busy_q && (!dataflow_sel || dataflow_req_ready);
  assign accept    = req_valid && req_ready;

  assign sram_req   = accept && sram_sel;
  assign sram_we    = req_we;
  assign sram_addr  = req_addr;
  assign sram_wdata = req_wdata;

  assign dataflow_req_valid = accept && dataflow_sel;
  assign dataflow_req_we    = req_we;
  assign dataflow_req_addr  = req_addr[1:0];
  assign dataflow_req_wdata = req_wdata;

  assign resp_valid = resp_valid_q;
  assign resp_rdata = resp_rdata_q;
  assign resp_error = resp_error_q;

  always_ff @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
      target_q     <= TARGET_NONE;
      busy_q       <= 1'b0;
      delay_q      <= 8'd0;
      resp_valid_q <= 1'b0;
      resp_rdata_q <= 32'h0000_0000;
      resp_error_q <= 1'b0;
    end else if (!enable) begin
      target_q     <= TARGET_NONE;
      busy_q       <= 1'b0;
      delay_q      <= 8'd0;
      resp_valid_q <= 1'b0;
      resp_error_q <= 1'b0;
    end else begin
      resp_valid_q <= 1'b0;

      if (accept) begin
        if (sram_sel) begin
          target_q <= TARGET_SRAM;
          busy_q   <= 1'b1;
          delay_q  <= delay_reload(SRAM_RESPONSE_DELAY);
        end else if (dataflow_sel) begin
          target_q <= TARGET_DATAFLOW;
          busy_q   <= 1'b1;
          delay_q  <= 8'd0;
        end else begin
          target_q <= TARGET_ERROR;
          busy_q   <= 1'b1;
          delay_q  <= 8'd0;
        end
      end else if (busy_q) begin
        unique case (target_q)
          TARGET_SRAM: begin
            if (delay_q == 8'd0) begin
              resp_valid_q <= 1'b1;
              resp_rdata_q <= sram_rdata;
              resp_error_q <= 1'b0;
              busy_q       <= 1'b0;
              target_q     <= TARGET_NONE;
            end else begin
              delay_q <= delay_q - 8'd1;
            end
          end

          TARGET_DATAFLOW: begin
            if (dataflow_resp_valid) begin
              resp_valid_q <= 1'b1;
              resp_rdata_q <= dataflow_resp_rdata;
              resp_error_q <= dataflow_resp_error;
              busy_q       <= 1'b0;
              target_q     <= TARGET_NONE;
            end
          end

          TARGET_ERROR: begin
            resp_valid_q <= 1'b1;
            resp_rdata_q <= 32'hbad0_0001;
            resp_error_q <= 1'b1;
            busy_q       <= 1'b0;
            target_q     <= TARGET_NONE;
          end

          default: begin
            busy_q   <= 1'b0;
            target_q <= TARGET_NONE;
          end
        endcase
      end
    end
  end
endmodule
