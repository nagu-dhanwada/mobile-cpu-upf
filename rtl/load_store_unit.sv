module load_store_unit (
  input  logic        clk,
  input  logic        reset_n,
  input  logic        enable,

  input  logic        execute_mem_req,
  input  logic        execute_mem_we,
  input  logic [3:0]  execute_wb_addr,
  input  logic [31:0] execute_mem_addr,
  input  logic [31:0] execute_mem_wdata,

  output logic        stall,
  output logic        retired,
  output logic        load_wb_en,
  output logic [3:0]  load_wb_addr,
  output logic [31:0] load_wb_data,
  output logic        error_seen,

  output logic        bus_req_valid,
  input  logic        bus_req_ready,
  output logic        bus_req_we,
  output logic [31:0] bus_req_addr,
  output logic [31:0] bus_req_wdata,
  output logic [3:0]  bus_req_byte_en,
  input  logic        bus_resp_valid,
  input  logic [31:0] bus_resp_rdata,
  input  logic        bus_resp_error
);
  typedef enum logic [1:0] {
    LSU_IDLE,
    LSU_WAIT_ACCEPT,
    LSU_WAIT_RESP,
    LSU_DONE
  } state_e;

  state_e state_q;

  logic        req_we_q;
  logic [3:0]  req_wb_addr_q;
  logic [31:0] req_addr_q;
  logic [31:0] req_wdata_q;
  logic [31:0] resp_rdata_q;
  logic        resp_error_q;
  logic        launch_req;
  logic        request_accepted;

  assign launch_req = (state_q == LSU_IDLE) && execute_mem_req;

  assign bus_req_valid = (state_q == LSU_WAIT_ACCEPT) || launch_req;
  assign bus_req_we    = (state_q == LSU_WAIT_ACCEPT) ? req_we_q : execute_mem_we;
  assign bus_req_addr  = (state_q == LSU_WAIT_ACCEPT) ? req_addr_q : execute_mem_addr;
  assign bus_req_wdata = (state_q == LSU_WAIT_ACCEPT) ? req_wdata_q : execute_mem_wdata;
  assign bus_req_byte_en = 4'hf;

  assign request_accepted = bus_req_valid && bus_req_ready;

  // The current CPU is single-issue and single-outstanding. A load/store stalls
  // fetch/decode until the response phase reaches LSU_DONE. LSU_DONE releases
  // the stall for one cycle so the held instruction retires and the PC advances
  // without reissuing the same request.
  assign stall = enable && (launch_req || (state_q == LSU_WAIT_ACCEPT) || (state_q == LSU_WAIT_RESP));
  assign retired = enable && (state_q == LSU_DONE);

  assign load_wb_en   = retired && !req_we_q && !resp_error_q;
  assign load_wb_addr = req_wb_addr_q;
  assign load_wb_data = resp_rdata_q;
  assign error_seen   = resp_error_q;

  always_ff @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
      state_q       <= LSU_IDLE;
      req_we_q      <= 1'b0;
      req_wb_addr_q <= 4'h0;
      req_addr_q    <= 32'h0000_0000;
      req_wdata_q   <= 32'h0000_0000;
      resp_rdata_q  <= 32'h0000_0000;
      resp_error_q  <= 1'b0;
    end else if (!enable) begin
      state_q      <= LSU_IDLE;
      resp_error_q <= 1'b0;
    end else begin
      unique case (state_q)
        LSU_IDLE: begin
          if (execute_mem_req) begin
            req_we_q      <= execute_mem_we;
            req_wb_addr_q <= execute_wb_addr;
            req_addr_q    <= execute_mem_addr;
            req_wdata_q   <= execute_mem_wdata;
            resp_error_q  <= 1'b0;
            state_q       <= bus_req_ready ? LSU_WAIT_RESP : LSU_WAIT_ACCEPT;
          end
        end

        LSU_WAIT_ACCEPT: begin
          if (bus_req_ready) begin
            state_q <= LSU_WAIT_RESP;
          end
        end

        LSU_WAIT_RESP: begin
          if (bus_resp_valid) begin
            resp_rdata_q <= bus_resp_rdata;
            resp_error_q <= bus_resp_error;
            state_q      <= LSU_DONE;
          end
        end

        LSU_DONE: begin
          state_q <= LSU_IDLE;
        end

        default: begin
          state_q <= LSU_IDLE;
        end
      endcase
    end
  end
endmodule
